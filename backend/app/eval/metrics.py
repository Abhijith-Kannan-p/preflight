"""Classification metrics for Claim Ledger verdicts."""

from collections import Counter

from pydantic import BaseModel

VERDICTS = ["supported", "outdated", "contradicted", "unsupported", "needs_review"]
NOT_DETECTED = "not_detected"


class LabelMetrics(BaseModel):
    precision: float
    recall: float
    f1: float
    support: int


class Metrics(BaseModel):
    per_label: dict[str, LabelMetrics]
    accuracy: float
    macro_recall: float
    problem_recall: float
    problem_precision: float
    detection_rate: float


def compute(pairs: list[tuple[str, str]]) -> tuple[Metrics, dict[str, dict[str, int]]]:
    """pairs = [(expected, predicted)]. Returns metrics and a confusion matrix
    confusion[expected][predicted]."""
    labels = [*VERDICTS, NOT_DETECTED]
    confusion = {e: dict.fromkeys(labels, 0) for e in VERDICTS}
    for expected, predicted in pairs:
        confusion[expected][predicted] += 1
    predicted_counts = Counter(p for _, p in pairs)
    per_label: dict[str, LabelMetrics] = {}
    for label in VERDICTS:
        tp = confusion[label][label]
        support = sum(confusion[label].values())
        precision = tp / predicted_counts[label] if predicted_counts[label] else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = LabelMetrics(
            precision=round(precision, 3), recall=round(recall, 3), f1=round(f1, 3),
            support=support,
        )  # fmt: skip

    # "Problem" claims are everything that must not be published unchanged.
    problems = [(e, p) for e, p in pairs if e != "supported"]
    flagged = [(e, p) for e, p in pairs if p not in ("supported", NOT_DETECTED)]
    problem_recall = (
        sum(p not in ("supported", NOT_DETECTED) for _, p in problems) / len(problems)
        if problems
        else 0.0
    )
    problem_precision = sum(e != "supported" for e, _ in flagged) / len(flagged) if flagged else 0.0
    total = len(pairs) or 1
    metrics = Metrics(
        per_label=per_label,
        accuracy=round(sum(e == p for e, p in pairs) / total, 3),
        macro_recall=round(sum(m.recall for m in per_label.values()) / len(VERDICTS), 3),
        problem_recall=round(problem_recall, 3),
        problem_precision=round(problem_precision, 3),
        detection_rate=round(sum(p != NOT_DETECTED for _, p in pairs) / total, 3),
    )
    return metrics, confusion
