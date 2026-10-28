"""Voice Fingerprint: the voice PayWise actually publishes, learned from approved content.

For every approved or published item (its latest completed revision):
- the five tone trait scores the review stored (LLM scores, or the offline heuristic's
  estimate; both are counted and shown);
- lexical features of the text: mean sentence length in words, exclamation marks, "you" and
  "your", and superlatives, each per 100 words.

The learned trait is the mean over items, with its standard error; the median is shown too.
(The median was tried first: technical scores are bimodal, plain posts near 0.2 and explainers
near 1.0, and a median of 0.2 kept flagging every explainer. On the demo history the replay
gave 18 of 36 drafts still flagged with medians against 9 with means.)
Confidence is high from 15 items with every standard error at most 0.05, medium from 8, low
below that.

Adopting the fingerprint creates a new voice-profile version (audit-logged; the old one is
kept in the history) and tone checks use it from the next review. The effect is measured as
the tone-dispute rate: TON-01 findings the writer disputed, divided by TON-01 findings raised
(once per submission, including "needs a human look" findings), split by the voice-profile
version in force when the draft was reviewed. A replay also re-compares the stored scores of
earlier drafts with the learned targets: a projection, labelled as one.
"""

import re
import statistics
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.engine.checkers.tone import TRAITS
from app.engine.text import sentences, words
from app.models import (
    Decision,
    Finding,
    Revision,
    Rule,
    RuleStatus,
    Submission,
    SubmissionState,
    User,
    Workspace,
    utcnow,
)

MIN_ITEMS = 5
MIN_RATE_SAMPLE = 4
_SUPERLATIVE = re.compile(
    r"#1\b|\b(best|leading|fastest|cheapest|largest|greatest|top-rated|most \w+|\w+est)\b", re.I
)
_NOT_SUPERLATIVE = {"interest", "test", "latest", "request", "rest", "honest", "invest", "guest"}


def lexical(text: str) -> dict[str, float]:
    n_words = max(1, len(words(text)))
    found = sentences(text)
    per_100 = 100 / n_words
    superlatives = [
        m.group(0)
        for m in _SUPERLATIVE.finditer(text)
        if m.group(0).lower() not in _NOT_SUPERLATIVE
    ]
    return {
        "sentence_words": round(n_words / max(1, len(found)), 1),
        "exclamations_per_100": round(text.count("!") * per_100, 2),
        "second_person_per_100": round(
            len(re.findall(r"\b(you|your|you're|yours)\b", text, re.I)) * per_100, 2
        ),
        "superlatives_per_100": round(len(superlatives) * per_100, 2),
    }


def _approved(session: Session, ws: str) -> list[tuple[Submission, Revision]]:
    subs = session.scalars(
        select(Submission).where(
            Submission.workspace_id == ws,
            Submission.state.in_((SubmissionState.approved, SubmissionState.published)),
        )
    ).all()
    items = []
    for sub in subs:
        latest = session.scalar(
            select(Revision)
            .where(Revision.submission_id == sub.id, Revision.review_status == "complete")
            .order_by(Revision.number.desc())
            .limit(1)
        )
        if latest is not None and (latest.report or {}).get("tone"):
            items.append((sub, latest))
    return items


def _confidence(n: int, errors: list[float]) -> str:
    if n >= 15 and max(errors, default=1) <= 0.05:
        return "high"
    return "medium" if n >= 8 else "low"


def fingerprint(session: Session, ws: str) -> dict[str, Any]:
    workspace = session.get_one(Workspace, ws)
    items = _approved(session, ws)
    sources: dict[str, int] = {}
    scores: dict[str, list[float]] = {t: [] for t in TRAITS}
    features: dict[str, list[float]] = {}
    for _, revision in items:
        tone = revision.report["tone"]
        sources[tone.get("source", "heuristic")] = (
            sources.get(tone.get("source", "heuristic"), 0) + 1
        )
        for trait in TRAITS:
            if trait in tone.get("scores", {}):
                scores[trait].append(float(tone["scores"][trait]))
        for name, value in lexical(revision.content).items():
            features.setdefault(name, []).append(value)

    learned: dict[str, dict[str, float]] = {}
    for trait, values in scores.items():
        if not values:
            continue
        spread = statistics.pstdev(values) if len(values) > 1 else 0.0
        learned[trait] = {
            "value": round(statistics.fmean(values), 2),
            "median": round(statistics.median(values), 2),
            "spread": round(spread, 3),
            "std_error": round(spread / len(values) ** 0.5, 3),
        }
    targets = dict(workspace.voice_profile.get("traits", {}))
    return {
        "items": len(items),
        "min_items": MIN_ITEMS,
        "ready": len(items) >= MIN_ITEMS and len(learned) == len(TRAITS),
        "confidence": _confidence(len(items), [v["std_error"] for v in learned.values()]),
        "score_sources": sources,
        "targets": targets,
        "learned": learned,
        "lexical": {
            name: {"median": round(statistics.median(v), 2), "mean": round(statistics.fmean(v), 2)}
            for name, v in features.items()
        },
        "profile": {
            "version": int(workspace.voice_profile.get("version", 1)),
            "source": workspace.voice_profile.get("source", "brand book (hand-set)"),
            "adopted_at": workspace.voice_profile.get("adopted_at"),
        },
        "history": [
            {k: v for k, v in h.items() if k in ("version", "traits", "source", "adopted_at")}
            for h in workspace.settings.get("voice_history", [])
        ],
        "dispute_rate": dispute_rate(session, ws),
        "replay": replay(session, ws, {t: v["value"] for t, v in learned.items()}),
    }


def set_profile(
    session: Session,
    workspace: Workspace,
    user: User,
    traits: dict[str, float],
    source: str,
    detail: dict[str, Any] | None = None,
) -> int:
    """Make `traits` the voice profile as a new version; the old one moves to the history."""
    old = workspace.voice_profile
    version = int(old.get("version", 1)) + 1
    history = [*workspace.settings.get("voice_history", []), {"version": 1, **old}]
    workspace.voice_profile = {
        **old,
        "traits": {t: round(float(traits[t]), 2) for t in TRAITS if t in traits},
        "version": version,
        "source": source,
        "adopted_at": utcnow().isoformat(),
    }
    workspace.settings = {**workspace.settings, "voice_history": history}
    workspace.rulebook_version += 1
    audit.record(
        session,
        "workspace",
        workspace.id,
        "voice_profile_adopted",
        user.id,
        {
            "version": version,
            "source": source,
            "from": old.get("traits"),
            "to": traits,
            **(detail or {}),
        },
    )
    return version


def adopt(session: Session, user: User) -> dict[str, Any]:
    workspace = session.get_one(Workspace, user.workspace_id)
    fp = fingerprint(session, workspace.id)
    if not fp["ready"]:
        raise ValueError(
            f"The fingerprint needs at least {MIN_ITEMS} approved items with tone scores."
        )
    version = set_profile(
        session,
        workspace,
        user,
        {t: v["value"] for t, v in fp["learned"].items()},
        f"learned from {fp['items']} approved items",
        {"items": fp["items"], "confidence": fp["confidence"]},
    )
    return {"version": version}


def _boundaries(workspace: Workspace) -> list[tuple[int, datetime | None]]:
    """(voice-profile version, adopted at) from oldest to current."""
    out: list[tuple[int, datetime | None]] = []
    for entry in [*workspace.settings.get("voice_history", []), workspace.voice_profile]:
        at = entry.get("adopted_at")
        out.append((int(entry.get("version", 1)), datetime.fromisoformat(at) if at else None))
    return out


def _version_at(bounds: list[tuple[int, datetime | None]], when: datetime) -> int:
    version = bounds[0][0]
    for v, at in bounds:
        if at is None or at <= when:
            version = v
    return version


def dispute_rate(session: Session, ws: str) -> dict[str, Any]:
    workspace = session.get_one(Workspace, ws)
    bounds = _boundaries(workspace)
    subs = select(Submission.id).where(Submission.workspace_id == ws)
    raised: dict[int, set[str]] = {}
    for submission_id, created in session.execute(
        select(Revision.submission_id, Revision.created_at)
        .join(Finding, Finding.revision_id == Revision.id)
        .where(Revision.submission_id.in_(subs), Finding.rule_code == "TON-01")
    ):
        raised.setdefault(_version_at(bounds, created), set()).add(submission_id)
    disputed: dict[int, set[str]] = {}
    for decision in session.scalars(
        select(Decision).where(Decision.submission_id.in_(subs), Decision.kind == "dispute")
    ):
        if (decision.payload or {}).get("rule") == "TON-01":
            version = _version_at(bounds, decision.created_at)
            disputed.setdefault(version, set()).add(decision.submission_id)
    rows = []
    for version, _ in bounds:
        n = len(raised.get(version, set()))
        d = len(disputed.get(version, set()) & raised.get(version, set()))
        rows.append(
            {
                "version": version,
                "raised": n,
                "disputed": d,
                "rate": round(d / n, 3) if n >= MIN_RATE_SAMPLE else None,
            }
        )
    before, after = (rows[-2], rows[-1]) if len(rows) > 1 else (rows[-1], None)
    return {"by_version": rows, "before": before, "after": after, "min_sample": MIN_RATE_SAMPLE}


def _off(scores: dict[str, float], targets: dict[str, Any], threshold: float) -> bool:
    """Would TON-01 flag these scores against these targets?"""
    return any(
        abs(float(scores[t]) - float(targets[t])) > threshold
        for t in TRAITS
        if t in targets and t in scores
    )


def replay(session: Session, ws: str, learned: dict[str, float]) -> dict[str, Any] | None:
    """Re-compare the stored scores of every reviewed first draft with the learned targets."""
    if len(learned) < len(TRAITS):
        return None
    rule = session.scalar(
        select(Rule).where(
            Rule.workspace_id == ws, Rule.code == "TON-01", Rule.status == RuleStatus.active
        )
    )
    threshold = float(rule.config.get("threshold", 0.3)) if rule else 0.3
    workspace = session.get_one(Workspace, ws)
    current = workspace.voice_profile.get("traits", {})
    subs = select(Submission.id).where(Submission.workspace_id == ws)
    disputed = {
        d.submission_id
        for d in session.scalars(
            select(Decision).where(Decision.submission_id.in_(subs), Decision.kind == "dispute")
        )
        if (d.payload or {}).get("rule") == "TON-01"
    }
    drafts = flagged_now = flagged_learned = disputed_cleared = disputed_total = 0
    for submission_id, report in session.execute(
        select(Revision.submission_id, Revision.report).where(
            Revision.submission_id.in_(subs), Revision.number == 1
        )
    ):
        scores = ((report or {}).get("tone") or {}).get("scores")
        if not scores:
            continue
        drafts += 1
        now, later = _off(scores, current, threshold), _off(scores, learned, threshold)
        flagged_now += now
        flagged_learned += later
        if submission_id in disputed:
            disputed_total += 1
            disputed_cleared += now and not later
    return {
        "drafts": drafts,
        "threshold": threshold,
        "flagged_with_current": flagged_now,
        "flagged_with_learned": flagged_learned,
        "disputed": disputed_total,
        "disputed_no_longer_flagged": disputed_cleared,
    }
