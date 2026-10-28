"""Guideline Health: which rules writers and approvers push back on, and whether rewording
helped.

For every rule, over a window of days:
- raised: findings it produced, counted once per review (the same finding on revision 2 of
  a draft is not counted again), excluding low-confidence "needs a human look" findings;
- dispute, override and acceptance rates: disputes, approver overrides and accepted or edited
  suggestions, divided by raised.

ambiguity = 0.6 x dispute rate + 0.4 x override rate, shown only with at least `MIN_SAMPLE`
findings; at or above `FLAG_AT` the rule is on the Guideline Health board. Every metric is
also split by rule version (by the time each version was active), which is how "fewer
disputes after rewording" is measured.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Decision, Finding, Revision, Rule, Submission, utcnow

DISPUTE_WEIGHT = 0.6
OVERRIDE_WEIGHT = 0.4
MIN_SAMPLE = 4
FLAG_AT = 0.3
WINDOW_DAYS = 90

FORMULA = (
    f"ambiguity = {DISPUTE_WEIGHT} x dispute rate + {OVERRIDE_WEIGHT} x override rate "
    f"(shown from {MIN_SAMPLE} findings; flagged at {FLAG_AT:.0%} or more)"
)


@dataclass
class Counts:
    raised: int = 0
    disputed: int = 0
    overridden: int = 0
    accepted: int = 0
    reasons: list[str] = field(default_factory=list)

    def rates(self) -> dict[str, Any]:
        def rate(n: int) -> float | None:
            return round(n / self.raised, 3) if self.raised else None

        dispute, override = rate(self.disputed), rate(self.overridden)
        ambiguity = None
        if self.raised >= MIN_SAMPLE and dispute is not None and override is not None:
            ambiguity = round(DISPUTE_WEIGHT * dispute + OVERRIDE_WEIGHT * override, 3)
        return {
            "raised": self.raised,
            "disputed": self.disputed,
            "overridden": self.overridden,
            "accepted": self.accepted,
            "dispute_rate": dispute,
            "override_rate": override,
            "acceptance_rate": rate(self.accepted),
            "ambiguity": ambiguity,
        }


_WORD = re.compile(r"[a-z]{3,}")
_STOP = {
    "the",
    "this",
    "that",
    "and",
    "not",
    "for",
    "with",
    "our",
    "are",
    "was",
    "has",
    "here",
    "its",
    "it's",
    "you",
    "your",
    "any",
    "but",
    "use",
    "used",
    "line",
    "needed",
}


def _tokens(text: str) -> set[str]:
    """Content words, cut to a six-letter stem so "promotion" and "promotional" match."""
    return {w[:6] for w in _WORD.findall(text.lower()) if w not in _STOP}


def group_reasons(reasons: list[str], threshold: float = 0.34) -> list[dict[str, Any]]:
    """Cluster similar dispute reasons so the brand manager reads themes, not a list.

    Two reasons belong together when they share at least two content words and those make up
    a third of the shorter reason's words."""
    groups: list[dict[str, Any]] = []
    for reason in reasons:
        words = _tokens(reason)
        for group in groups:
            shared = words & group["words"]
            smaller = min(len(words), len(group["words"])) or 1
            if len(shared) >= 2 and len(shared) / smaller >= threshold:
                group["count"] += 1
                group["examples"].append(reason)
                group["words"] |= words
                break
        else:
            groups.append({"count": 1, "examples": [reason], "words": set(words)})
    groups.sort(key=lambda g: -g["count"])
    return [{"count": g["count"], "examples": list(g["examples"])[:3]} for g in groups]


def _version_at(versions: list[Rule], when: datetime) -> int:
    current = versions[0].version
    for rule in versions:
        if rule.created_at <= when:
            current = rule.version
    return current


def compute(session: Session, workspace_id: str, days: int = WINDOW_DAYS) -> dict[str, Any]:
    since = utcnow() - timedelta(days=days)
    rules: dict[str, list[Rule]] = defaultdict(list)
    for rule in session.scalars(
        select(Rule).where(Rule.workspace_id == workspace_id).order_by(Rule.created_at)
    ):
        rules[rule.code].append(rule)

    subs = select(Submission.id).where(Submission.workspace_id == workspace_id)
    rows = session.execute(
        select(Finding, Revision.submission_id, Revision.created_at)
        .join(Revision, Revision.id == Finding.revision_id)
        .where(Revision.submission_id.in_(subs), Revision.created_at >= since)
        .order_by(Revision.created_at)
    ).all()
    overall: dict[str, Counts] = defaultdict(Counts)
    by_version: dict[tuple[str, int], Counts] = defaultdict(Counts)
    seen: set[tuple[str, str]] = set()
    for finding, submission_id, created_at in rows:
        if finding.needs_review or finding.rule_code not in rules:
            continue
        key = (submission_id, finding.rule_code)
        if key in seen:
            continue
        seen.add(key)
        version = _version_at(rules[finding.rule_code], created_at)
        overall[finding.rule_code].raised += 1
        by_version[(finding.rule_code, version)].raised += 1

    decided: set[tuple[str, str, str]] = set()
    decisions = session.scalars(
        select(Decision)
        .where(Decision.submission_id.in_(subs), Decision.created_at >= since)
        .order_by(Decision.created_at)
    )
    for decision in decisions:
        code = str((decision.payload or {}).get("rule") or "")
        kind = {"dispute": "disputed", "override": "overridden", "accept": "accepted"}.get(
            decision.kind, "accepted" if decision.kind == "edit" else ""
        )
        if not kind or code not in rules:
            continue
        decision_key = (decision.submission_id, code, kind)
        if decision_key in decided:
            continue
        decided.add(decision_key)
        version = _version_at(rules[code], decision.created_at)
        for counts in (overall[code], by_version[(code, version)]):
            setattr(counts, kind, getattr(counts, kind) + 1)
            if kind == "disputed" and decision.reason:
                counts.reasons.append(decision.reason)

    report: list[dict[str, Any]] = []
    for code, versions in sorted(rules.items()):
        active = next((r for r in reversed(versions) if r.status.value == "active"), versions[-1])
        history = []
        for rule in versions:
            counts = by_version.get((code, rule.version), Counts())
            history.append(
                {
                    "version": rule.version,
                    "title": rule.title,
                    "description": rule.description,
                    "since": rule.created_at,
                    "status": rule.status.value,
                    **counts.rates(),
                }
            )
        current = by_version.get((code, active.version), Counts())
        current_rates = current.rates()
        change = _dispute_change(history)
        report.append(
            {
                "code": code,
                "title": active.title,
                "description": active.description,
                "category": active.category,
                "severity": active.severity.value,
                "version": active.version,
                "source_ref": active.source_ref,
                "source_doc": active.source_doc,
                "source_page": active.source_page,
                "config": active.config,
                "overall": overall.get(code, Counts()).rates(),
                "current": current_rates,
                "flagged": (current_rates["ambiguity"] or 0) >= FLAG_AT,
                "reason_groups": group_reasons(current.reasons or overall[code].reasons),
                "versions": history,
                "dispute_change": change,
            }
        )
    report.sort(key=lambda item: -(item["current"]["ambiguity"] or -1))
    return {"window_days": days, "formula": FORMULA, "rules": report}


def _dispute_change(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Relative change in dispute rate from the previous version to the latest one, when both
    have findings: -0.3 means 30% fewer disputes per finding after the rewording."""
    measured = [v for v in history if v["raised"]]
    if len(history) < 2 or len(measured) < 2 or history[-1]["raised"] == 0:
        return None
    before, after = measured[-2], measured[-1]
    if not before["dispute_rate"]:
        return None
    return {
        "from_version": before["version"],
        "to_version": after["version"],
        "before": before["dispute_rate"],
        "after": after["dispute_rate"],
        "relative": round(
            (after["dispute_rate"] - before["dispute_rate"]) / before["dispute_rate"], 3
        ),
    }
