"""Compare compiled candidates with the rulebook, and apply the ones a brand manager accepts.

Matching (`match`): each candidate is new, a duplicate of something the rulebook already has,
or an update to it (more variants, more triggers, a different limit). Guidance rules are
compared with existing rules by meaning: embedding similarity of title and description
(rapidfuzz token overlap when no embedder is loaded).

Applying (`apply`) writes exactly what the engine checks: a term, a new rule version with the
extra pattern or limit, a new disclaimer rule, a palette colour, channel limits or the voice
profile. Every change is audit-logged with the compiled source and page.
"""

import math
import re
from typing import Any

import numpy as np
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.governance.voice import set_profile
from app.ml.embeddings import get_embedder
from app.models import (
    ChannelProfile,
    Rule,
    RuleStatus,
    Severity,
    Term,
    TermKind,
    User,
    Workspace,
)
from app.scoped import get_channel
from app.visual.brand import DEFAULT_PALETTE
from app.visual.colour import ciede2000, hex_to_rgb, rgb_to_lab

GUIDANCE_SIMILAR = 0.82
PREFIX = {
    "claims": "CLM",
    "terminology": "TRM",
    "tone": "TON",
    "disclaimer": "DSC",
    "channel": "CHN",
    "readability": "RDB",
    "visual": "VIS",
    "accessibility": "ACC",
}


def _active(session: Session, ws: str) -> dict[str, Rule]:
    return {
        r.code: r
        for r in session.scalars(
            select(Rule).where(Rule.workspace_id == ws, Rule.status == RuleStatus.active)
        )
    }


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower()).rstrip(".")


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class Matcher:
    """Matches candidates against one workspace's rulebook (loaded once per job)."""

    def __init__(self, session: Session, ws: str) -> None:
        self.session, self.ws = session, ws
        self.rules = _active(session, ws)
        self.terms = list(session.scalars(select(Term).where(Term.workspace_id == ws)))
        workspace = session.get_one(Workspace, ws)
        self.palette = workspace.settings.get("brand_palette") or DEFAULT_PALETTE
        self.voice = workspace.voice_profile.get("traits", {})
        self.embedder = get_embedder()
        self._rule_vectors: dict[str, list[float]] | None = None

    def match(self, kind: str, p: dict[str, Any]) -> tuple[str, str | None, str]:
        """(status, reference, note)."""
        return getattr(self, f"_{kind}")(p)  # type: ignore[no-any-return]

    def _term(self, p: dict[str, Any]) -> tuple[str, str | None, str]:
        for t in self.terms:
            if t.kind == TermKind.product_name and t.term == p["term"]:
                extra = sorted(set(p["variants"]) - set(t.variants))
                if extra:
                    return "update", "TRM-02", f"adds variants: {', '.join(extra)}"
                return "duplicate", "TRM-02", f"{t.term} is already a product name"
        return "new", None, "new product name"

    def _word(self, p: dict[str, Any]) -> tuple[str, str | None, str]:
        for t in self.terms:
            if t.kind != TermKind.product_name and t.term.lower() == p["term"].lower():
                same = t.kind.value == p["status"] and (t.replacement or None) == p["replacement"]
                return (
                    ("duplicate" if same else "update"),
                    "TRM-05",
                    f"already listed as {t.kind.value}",
                )
        return "new", None, f"new {p['status']} word"

    def _pattern(self, p: dict[str, Any]) -> tuple[str, str | None, str]:
        rule = self.rules.get(p["rule"])
        existing = {str(x).lower() for x in (rule.config.get("patterns", []) if rule else [])}
        if p["pattern"].lower() in existing:
            return "duplicate", p["rule"], f'"{p["pattern"]}" is already a {p["rule"]} pattern'
        return "update", p["rule"], f'adds "{p["pattern"]}" to {p["rule"]}'

    def _disclaimer(self, p: dict[str, Any]) -> tuple[str, str | None, str]:
        for rule in self.rules.values():
            if rule.category != "disclaimer":
                continue
            if _norm(str(rule.config.get("disclaimer", ""))) == _norm(p["disclaimer"]):
                have = {str(t).lower() for t in rule.config.get("triggers", [])}
                extra = sorted({t.lower() for t in p["triggers"]} - have)
                if extra:
                    return "update", rule.code, f"adds triggers: {', '.join(extra)}"
                return "duplicate", rule.code, f"{rule.code} already requires this text"
        return "new", None, "new disclaimer rule"

    def _colour(self, p: dict[str, Any]) -> tuple[str, str | None, str]:
        lab = rgb_to_lab(np.array([hex_to_rgb(p["hex"])], dtype=np.float64))
        for colour in self.palette:
            if (
                float(
                    ciede2000(
                        lab, rgb_to_lab(np.array([hex_to_rgb(colour["hex"])], dtype=np.float64))
                    )[0]
                )
                < 3
            ):
                return "duplicate", "VIS-01", f"{colour['name']} {colour['hex']} is in the palette"
        return "new", "VIS-01", "new palette colour"

    def _channel(self, p: dict[str, Any]) -> tuple[str, str | None, str]:
        row = get_channel(self.session, self.ws, p["channel"])
        if row is None:
            return "new", None, "new channel"
        changes = [
            f"{k} {getattr(row, k)} → {p[k]}"
            for k in ("max_chars", "max_hashtags", "subject_max_chars")
            if p[k] is not None and getattr(row, k) != p[k]
        ]
        return (
            ("update", row.id, "; ".join(changes))
            if changes
            else ("duplicate", row.id, "same limits")
        )

    def _threshold(self, p: dict[str, Any]) -> tuple[str, str | None, str]:
        rule = self.rules.get(p["rule"])
        current = rule.config.get(p["field"]) if rule else None
        if current is not None and float(current) == float(p["value"]):
            return "duplicate", p["rule"], f"{p['field']} is already {current}"
        return "update", p["rule"], f"{p['field']} {current} → {p['value']:g}"

    def _voice(self, p: dict[str, Any]) -> tuple[str, str | None, str]:
        if all(abs(self.voice.get(k, -1) - v) < 0.01 for k, v in p["traits"].items()):
            return "duplicate", "TON-01", "the voice profile already has these targets"
        return "update", "TON-01", "different voice targets"

    def _guidance(self, p: dict[str, Any]) -> tuple[str, str | None, str]:
        text = f"{p['title']}. {p['description']}"
        best, score = None, 0.0
        if self.embedder is not None:
            if self._rule_vectors is None:
                codes = list(self.rules)
                vectors = self.embedder.embed(
                    [f"{r.title}. {r.description}" for r in self.rules.values()]
                )
                self._rule_vectors = dict(zip(codes, vectors, strict=True))
            query = self.embedder.embed([text])[0]
            for code, vector in self._rule_vectors.items():
                similarity = _cosine(query, vector)
                if similarity > score:
                    best, score = code, similarity
        else:
            for code, rule in self.rules.items():
                similarity = fuzz.token_set_ratio(text, f"{rule.title}. {rule.description}") / 100
                if similarity > score:
                    best, score = code, similarity
        if best and score >= GUIDANCE_SIMILAR:
            return "duplicate", best, f"{score:.0%} similar to {best}"
        return "new", None, "new guidance rule (checked by reviewers, not automatically)"


# --- applying an accepted candidate ---------------------------------------------------------


def _disclaimer_text(p: dict[str, Any]) -> str:
    return f'Mentions of {", ".join(p["triggers"])} require "{p["disclaimer"]}"'


def _next_code(session: Session, ws: str, category: str) -> str:
    prefix = PREFIX.get(category, "GEN")
    used = {
        int(code.split("-")[1])
        for code in session.scalars(select(Rule.code).where(Rule.workspace_id == ws))
        if code.startswith(prefix + "-") and code.split("-")[1].isdigit()
    }
    return f"{prefix}-{(max(used) if used else 0) + 1:02d}"


def _new_version(session: Session, rule: Rule, user: User, **changes: Any) -> Rule:
    rule.status = RuleStatus.retired
    values = {
        "workspace_id": rule.workspace_id,
        "code": rule.code,
        "category": rule.category,
        "title": rule.title,
        "description": rule.description,
        "severity": rule.severity,
        "config": dict(rule.config),
        "source_doc": rule.source_doc,
        "source_page": rule.source_page,
        **changes,
    }
    fresh = Rule(
        **values,
        version=rule.version + 1,
        status=RuleStatus.active,
        created_by=user.id,
        approved_by=user.id,
    )
    session.add(fresh)
    return fresh


def apply(
    session: Session, user: User, kind: str, p: dict[str, Any], source: str, page: int
) -> str:
    """Make an accepted candidate live. Returns what changed (a rule code or term)."""
    ws = user.workspace_id
    workspace = session.get_one(Workspace, ws)
    rules = _active(session, ws)
    ref: str
    if kind == "term":
        term = session.scalar(
            select(Term).where(
                Term.workspace_id == ws, Term.term == p["term"], Term.kind == TermKind.product_name
            )
        )
        if term:
            term.variants = sorted(set(term.variants) | set(p["variants"]))
        else:
            session.add(
                Term(
                    workspace_id=ws,
                    term=p["term"],
                    kind=TermKind.product_name,
                    variants=p["variants"],
                    replacement=None,
                    case_sensitive=True,
                    rule_code="TRM-02",
                    note=p.get("note", ""),
                )
            )
        workspace.rulebook_version += 1
        ref = f"TRM-02:{p['term']}"
    elif kind == "word":
        term = session.scalar(
            select(Term).where(
                Term.workspace_id == ws,
                Term.term.ilike(p["term"]),
                Term.kind != TermKind.product_name,
            )
        )
        if term is None:
            term = Term(
                workspace_id=ws,
                term=p["term"],
                variants=[],
                case_sensitive=False,
                rule_code="TRM-05",
                note="From the brand book",
            )
            session.add(term)
        term.kind, term.replacement = TermKind(p["status"]), p["replacement"]
        workspace.rulebook_version += 1
        ref = f"TRM-05:{p['term']}"
    elif kind == "pattern":
        rule = rules[p["rule"]]
        patterns = list(rule.config.get("patterns", []))
        if p["pattern"].lower() not in {x.lower() for x in patterns}:
            patterns.append(p["pattern"])
        _new_version(session, rule, user, config={**rule.config, "patterns": patterns})
        workspace.rulebook_version += 1
        ref = p["rule"]
    elif kind == "disclaimer":
        existing = next(
            (
                r
                for r in rules.values()
                if r.category == "disclaimer"
                and _norm(str(r.config.get("disclaimer", ""))) == _norm(p["disclaimer"])
            ),
            None,
        )
        if existing:
            triggers = sorted(
                {
                    *map(str.lower, existing.config.get("triggers", [])),
                    *map(str.lower, p["triggers"]),
                }
            )
            _new_version(session, existing, user, config={**existing.config, "triggers": triggers})
            ref = existing.code
        else:
            ref = _next_code(session, ws, "disclaimer")
            session.add(
                Rule(
                    workspace_id=ws,
                    code=ref,
                    category="disclaimer",
                    title=p["title"],
                    description=_disclaimer_text(p),
                    severity=Severity(p["severity"]),
                    config={"triggers": p["triggers"], "disclaimer": p["disclaimer"]},
                    source_doc=source,
                    source_page=page,
                    version=1,
                    status=RuleStatus.active,
                    created_by=user.id,
                    approved_by=user.id,
                )
            )
        workspace.rulebook_version += 1
    elif kind == "colour":
        palette = list(workspace.settings.get("brand_palette") or DEFAULT_PALETTE)
        if p["hex"] not in {c["hex"].upper() for c in palette}:
            palette.append({"name": p["name"], "hex": p["hex"]})
        workspace.settings = {**workspace.settings, "brand_palette": palette}
        workspace.rulebook_version += 1
        ref = "VIS-01"
    elif kind == "channel":
        row = get_channel(session, ws, p["channel"])
        if row is None:
            row = ChannelProfile(
                workspace_id=ws,
                id=p["channel"],
                name=p["channel"].title(),
                consumer=True,
                rule_code=None,
            )
            session.add(row)
        for key in ("max_chars", "max_hashtags", "subject_max_chars"):
            if p[key] is not None:
                setattr(row, key, p[key])
        workspace.rulebook_version += 1
        ref = f"channel:{p['channel']}"
    elif kind == "threshold":
        rule = rules[p["rule"]]
        value = int(p["value"]) if float(p["value"]).is_integer() else p["value"]
        _new_version(session, rule, user, config={**rule.config, p["field"]: value})
        workspace.rulebook_version += 1
        ref = p["rule"]
    elif kind == "voice":
        set_profile(session, workspace, user, p["traits"], f"{source}#p{page}")
        ref = "TON-01"
    else:  # guidance
        ref = _next_code(session, ws, p["category"])
        session.add(
            Rule(
                workspace_id=ws,
                code=ref,
                category=p["category"],
                title=p["title"],
                description=p["description"],
                severity=Severity(p["severity"]),
                config={"guidance_only": True},
                source_doc=source,
                source_page=page,
                version=1,
                status=RuleStatus.active,
                created_by=user.id,
                approved_by=user.id,
            )
        )
        workspace.rulebook_version += 1
    audit.record(
        session,
        "rulebook",
        ref,
        "compiled_rule_accepted",
        user.id,
        {"kind": kind, "payload": p, "source": f"{source}#p{page}"},
    )
    return ref
