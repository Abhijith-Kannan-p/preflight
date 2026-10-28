"""Evaluate whole reviews on the 20 labelled full drafts in data/eval/full_drafts.json.

    python -m app.eval.drafts --export ../data/eval/drafts_run.json

Each draft is reviewed exactly as in the app (all text checkers, the Claim Ledger with the
local NLI and embedding models, no LLM) against the seeded rulebook on the evaluation date.
A rule counts as raised when the review has at least one confident finding for it ("needs a
human look" findings cost no points and are reported separately). Document-level scores are
over (draft, rule) pairs:

- precision: raised pairs that were labelled
- recall: labelled pairs that were raised
- clean drafts: drafts labelled with no issues that came back with none
"""

import argparse
import asyncio
import json
import platform
import statistics
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.engine.context import ReviewContext, load_context
from app.engine.normalise import from_text
from app.engine.pipeline import default_checkers, run_review
from app.ml.embeddings import Embedder, get_embedder
from app.ml.nli import NliModel, get_nli
from app.seed import WORKSPACE_ID


async def _review(
    content: str, ctx: ReviewContext, nli: NliModel | None, embedder: Embedder | None
) -> tuple[set[str], set[str]]:
    plan = default_checkers(nli, embedder)
    result = await run_review(from_text(content), ctx, plan.checkers, embedder=embedder)
    confident = {f.rule.id for f in result.findings if not f.needs_review}
    human = {f.rule.id for f in result.findings if f.needs_review} - confident
    return confident, human


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 3) if b else None


def evaluate(
    drafts: list[dict[str, Any]],
    contexts: dict[str, ReviewContext],
    nli: NliModel | None,
    embedder: Embedder | None,
) -> dict[str, Any]:
    tp: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    fn: Counter[str] = Counter()
    rows, latencies = [], []
    for draft in drafts:
        started = time.perf_counter()
        raised, human = asyncio.run(
            _review(draft["content"], contexts[draft["channel"]], nli, embedder)
        )
        latencies.append(time.perf_counter() - started)
        expected = set(draft["expected"])
        for code in raised & expected:
            tp[code] += 1
        for code in raised - expected:
            fp[code] += 1
        for code in expected - raised:
            fn[code] += 1
        rows.append(
            {
                "id": draft["id"],
                "title": draft["title"],
                "channel": draft["channel"],
                "expected": sorted(expected),
                "raised": sorted(raised),
                "needs_human_look": sorted(human),
                "missed": sorted(expected - raised),
                "extra": sorted(raised - expected),
                "note": draft.get("note", ""),
            }
        )
    codes = sorted(set(tp) | set(fp) | set(fn))
    clean = [r for r in rows if not r["expected"]]
    n_tp, n_fp, n_fn = sum(tp.values()), sum(fp.values()), sum(fn.values())
    return {
        "n_drafts": len(drafts),
        "labelled_issues": n_tp + n_fn,
        "precision": _ratio(n_tp, n_tp + n_fp),
        "recall": _ratio(n_tp, n_tp + n_fn),
        "exact_drafts": sum(not r["missed"] and not r["extra"] for r in rows),
        "clean_drafts": len(clean),
        "clean_drafts_passed": sum(not r["raised"] for r in clean),
        "per_rule": {
            c: {
                "tp": tp[c],
                "fp": fp[c],
                "fn": fn[c],
                "precision": _ratio(tp[c], tp[c] + fp[c]),
                "recall": _ratio(tp[c], tp[c] + fn[c]),
            }
            for c in codes
        },
        "drafts": rows,
        "latency_s": {
            "p50": round(statistics.median(latencies), 2),
            "max": round(max(latencies), 2),
        },
    }


def main() -> None:
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path)
    args = parser.parse_args()
    data = json.loads(
        (get_settings().data_dir / "eval" / "full_drafts.json").read_text(encoding="utf-8")
    )
    on = date.fromisoformat(data["eval_date"])
    nli, embedder = get_nli(), get_embedder()
    with SessionLocal() as session:
        contexts = {
            channel: load_context(session, WORKSPACE_ID, channel, today=on)
            for channel in {d["channel"] for d in data["drafts"]}
        }
    result = evaluate(data["drafts"], contexts, nli, embedder)
    result["config"] = {
        "mode": "deterministic (local NLI and embeddings, no LLM)",
        "nli_model": nli.name if nli else "lexical fallback",
        "embedding_model": embedder.name if embedder else None,
        "eval_date": data["eval_date"],
        "dataset": "data/eval/full_drafts.json",
        "processor": platform.processor() or platform.machine(),
        "python": sys.version.split()[0],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    print(
        f"{result['n_drafts']} drafts, {result['labelled_issues']} labelled issues: "
        f"precision {result['precision']}, recall {result['recall']}, "
        f"{result['exact_drafts']} drafts exactly right, clean drafts "
        f"{result['clean_drafts_passed']}/{result['clean_drafts']}"
    )
    for row in result["drafts"]:
        if row["missed"] or row["extra"]:
            print(f"  {row['id']} missed {row['missed']} extra {row['extra']}")
    if args.export:
        args.export.write_text(
            json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
