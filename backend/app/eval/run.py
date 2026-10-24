"""Run the Claim Ledger on the labelled claim set and record an EvalRun.

Usage (from backend/): python -m app.eval.run [--no-save]
"""

import argparse
import asyncio
import json
import statistics
import time
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.engine.claims.ledger import ClaimLedger, ClaimRecord
from app.engine.context import ReviewContext, load_context
from app.engine.normalise import from_text
from app.eval.metrics import NOT_DETECTED, VERDICTS, compute
from app.ml.embeddings import Embedder, get_embedder
from app.ml.nli import NliModel, get_nli
from app.models import EvalRun
from app.seed import WORKSPACE_ID

# Fixed so results are reproducible: validity windows are evaluated on this date.
EVAL_DATE = date(2026, 10, 22)
_SEVERITY_ORDER = ["contradicted", "outdated", "unsupported", "needs_review", "supported"]


def load_items(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _predicted(records: list[ClaimRecord]) -> ClaimRecord | None:
    """One verdict per test claim: the most serious one if the claim was split."""
    if not records:
        return None
    return min(records, key=lambda r: _SEVERITY_ORDER.index(r.verdict))


def evaluate(
    items: list[dict[str, Any]],
    ctx: ReviewContext,
    nli: NliModel | None,
    embedder: Embedder | None,
) -> dict[str, Any]:
    pairs: list[tuple[str, str]] = []
    latencies: list[float] = []
    failures: list[dict[str, Any]] = []
    for item in items:
        ledger = ClaimLedger(nli, embedder)
        started = time.perf_counter()
        asyncio.run(ledger.run(from_text(item["claim"]), ctx))
        latencies.append((time.perf_counter() - started) * 1000)
        record = _predicted(ledger.records)
        predicted = record.verdict if record else NOT_DETECTED
        pairs.append((item["expected"], predicted))
        if predicted != item["expected"]:
            failures.append(
                {
                    "id": item["id"],
                    "claim": item["claim"],
                    "expected": item["expected"],
                    "predicted": predicted,
                    "expected_fact": item.get("fact_id"),
                    "predicted_fact": record.fact_id if record else None,
                    "scores": record.scores if record else {},
                    "note": item.get("note", ""),
                }
            )
    metrics, confusion = compute(pairs)
    ordered = sorted(latencies)
    return {
        "n_items": len(items),
        "metrics": metrics.model_dump(),
        "confusion": confusion,
        "failures": failures,
        "latency_ms_p50": round(statistics.median(ordered), 1),
        "latency_ms_p95": round(ordered[int(0.95 * (len(ordered) - 1))], 1),
        "config": {
            "nli_model": nli.name if nli else "lexical fallback",
            "embedding_model": embedder.name if embedder else None,
            "eval_date": EVAL_DATE.isoformat(),
            "dataset": "data/eval/claims.jsonl",
        },
    }


def save(session: Session, result: dict[str, Any]) -> EvalRun:
    run = EvalRun(**result)
    session.add(run)
    session.commit()
    return run


def _print(result: dict[str, Any]) -> None:
    m = result["metrics"]
    print(f"\nClaim Ledger evaluation: {result['n_items']} labelled claims "
          f"({result['config']['nli_model']})")  # fmt: skip
    print(f"{'verdict':14} {'prec':>6} {'recall':>6} {'f1':>6} {'n':>4}")
    for label in VERDICTS:
        lm = m["per_label"][label]
        print(f"{label:14} {lm['precision']:6.2f} {lm['recall']:6.2f} {lm['f1']:6.2f} "
              f"{lm['support']:4}")  # fmt: skip
    print(f"\naccuracy {m['accuracy']:.2f} | macro recall {m['macro_recall']:.2f} | "
          f"problem-claim recall {m['problem_recall']:.2f} | problem-claim precision "
          f"{m['problem_precision']:.2f} | detection {m['detection_rate']:.2f}")  # fmt: skip
    print(f"latency p50 {result['latency_ms_p50']} ms, p95 {result['latency_ms_p95']} ms")
    print(f"\n{len(result['failures'])} failures:")
    for f in result["failures"]:
        print(f"  {f['id']:4} expected {f['expected']:12} got {f['predicted']:12} {f['claim']}")


def main() -> None:
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-save", action="store_true", help="do not write an EvalRun")
    args = parser.parse_args()
    items = load_items(get_settings().data_dir / "eval" / "claims.jsonl")
    with SessionLocal() as session:
        ctx = load_context(session, WORKSPACE_ID, "blog", today=EVAL_DATE)
        result = evaluate(items, ctx, get_nli(), get_embedder())
        _print(result)
        if not args.no_save:
            run = save(session, result)
            print(f"\nSaved EvalRun {run.id}")


if __name__ == "__main__":
    main()
