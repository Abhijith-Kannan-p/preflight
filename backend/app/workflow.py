"""Content state machine, approval gate and suggestion application.

Draft -> In review -> Changes requested -> In review -> Approved -> Published.
Illegal transitions raise TransitionError (HTTP 409). An approver cannot approve while a
critical finding is unresolved unless they override it with a written reason, which is
highlighted on the Review Receipt.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.auth import Permission
from app.models import Finding, SubmissionState

S = SubmissionState


@dataclass(frozen=True)
class Transition:
    sources: frozenset[SubmissionState]
    target: SubmissionState
    permission: Permission
    label: str


TRANSITIONS: dict[str, Transition] = {
    "submit": Transition(
        frozenset({S.draft, S.changes_requested}),
        S.in_review,
        Permission.submit_content,
        "Submitted for approval",
    ),
    "request_changes": Transition(
        frozenset({S.in_review}), S.changes_requested, Permission.approve, "Changes requested"
    ),
    "approve": Transition(frozenset({S.in_review}), S.approved, Permission.approve, "Approved"),
    "publish": Transition(
        frozenset({S.approved}), S.published, Permission.approve, "Marked as published"
    ),
}

# Statuses that still need attention. Disputed findings may be submitted (an approver
# decides on the dispute) but block approval unless overridden.
UNRESOLVED = {"open", "escalated", "disputed"}


class TransitionError(Exception):
    """An illegal state change. The API returns 409."""


class GateError(Exception):
    """The approval gate refused. The API returns 409 with the blocking findings."""

    def __init__(self, message: str, blocking: list[str]) -> None:
        super().__init__(message)
        self.blocking = blocking


def check_transition(state: SubmissionState, action: str) -> Transition:
    transition = TRANSITIONS.get(action)
    if transition is None:
        raise TransitionError(f"Unknown action '{action}'.")
    if state not in transition.sources:
        allowed = ", ".join(sorted(s.value.replace("_", " ") for s in transition.sources))
        raise TransitionError(
            f"Cannot '{action.replace('_', ' ')}' from '{state.value.replace('_', ' ')}'. "
            f"Allowed from: {allowed}."
        )
    return transition


def blocking_criticals(findings: Iterable[Finding], for_action: str) -> list[Finding]:
    statuses = UNRESOLVED if for_action == "approve" else {"open", "escalated"}
    return [
        f
        for f in findings
        if f.severity.value == "critical" and not f.needs_review and f.status in statuses
    ]


def apply_suggestions(blocks: list[str], findings: Iterable[Finding]) -> tuple[list[str], int]:
    """Apply accepted or edited text to each block, right to left so offsets stay valid.
    Overlapping edits keep the first one (highest-ranked) and skip the rest."""
    by_block: dict[int, list[Finding]] = {}
    for f in findings:
        if f.applied_text is not None and f.status in ("accepted", "edited"):
            by_block.setdefault(int(f.span["block"]), []).append(f)
    applied = 0
    result = list(blocks)
    for block_id, items in by_block.items():
        if block_id >= len(result):
            continue
        chosen: list[Finding] = []
        for f in sorted(items, key=lambda f: f.position):
            start, end = int(f.span["start"]), int(f.span["end"])
            if all(end <= int(c.span["start"]) or start >= int(c.span["end"]) for c in chosen):
                chosen.append(f)
        text = result[block_id]
        for f in sorted(chosen, key=lambda f: -int(f.span["start"])):
            start, end = int(f.span["start"]), int(f.span["end"])
            if text[start:end] != f.text:
                continue  # stale span; never guess
            replacement = f.applied_text or ""
            text = text[:start] + replacement + text[end:]
            applied += 1
        result[block_id] = _tidy(text)
    return result, applied


def _tidy(text: str) -> str:
    """Clean up after deletions: double spaces and spaces before punctuation."""
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r" +([.,!?;:])", r"\1", text).strip()
