"""Evaluate the visual review on the 100 labelled assets in data/eval/visual.

    python -m app.eval.visual --export ../data/eval/visual_run.json

Each asset is labelled with the issues injected into it (see scripts/make_visual_data.py).
For every check we count asset-level true/false positives: an asset is predicted positive
for VIS-01 if the review raises at least one VIS-01 finding, and so on. Text rules found in
the image (CLM-01, CLM-04, TRM-02) are checked by running the deterministic text checkers on
the OCR text, exactly as a review does. OCR quality is the share of expected words read.
"""

import argparse
import asyncio
import json
import platform
import re
import statistics
import time
from pathlib import Path
from typing import Any

from PIL import Image

from app.config import get_settings
from app.engine.context import ReviewContext
from app.engine.pipeline import default_checkers, run_review
from app.visual.analyse import analyse
from app.visual.intake import _reduce

CHECKS = ["VIS-01", "VIS-02", "VIS-03", "ACC-01", "logo"]
TEXT_RULES = ["CLM-01", "CLM-04", "TRM-02"]


async def _ignore(_event: str, _data: dict[str, Any]) -> None:
    return None


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9#%']+", text.lower())


async def _review(path: Path, ctx: ReviewContext) -> tuple[set[str], str, float, bool]:
    image, scale = _reduce(Image.open(path))
    started = time.perf_counter()
    visual = await analyse([image], ctx, "image", [], _ignore, [scale])
    elapsed = time.perf_counter() - started
    # All text checkers, with the Claim Ledger in its deterministic mode (no NLI, no LLM).
    checkers = default_checkers(None, None).checkers
    result = await run_review(visual.doc, ctx, checkers, extra=visual.findings)
    rules = {f.rule.id for f in result.findings if not f.needs_review}
    logo_found = visual.report["pages"][0]["logo"] is not None
    return rules, visual.doc.text, elapsed, logo_found


def evaluate(ctx: ReviewContext, folder: Path | None = None) -> dict[str, Any]:
    folder = folder or get_settings().data_dir / "eval" / "visual"
    items = json.loads((folder / "labels.json").read_text(encoding="utf-8"))
    counts = {c: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for c in CHECKS + TEXT_RULES}
    latencies: list[float] = []
    word_hits = word_total = 0
    failures: list[dict[str, Any]] = []
    for item in items:
        rules, text, elapsed, logo_found = asyncio.run(_review(folder / item["file"], ctx))
        latencies.append(elapsed)
        predicted = {c: (c in rules) for c in CHECKS if c != "logo"} | {"logo": logo_found}
        predicted |= {r: r in rules for r in TEXT_RULES}
        expected = {c: bool(item.get(c)) for c in CHECKS}
        expected |= {r: r in item.get("text_rules", []) for r in TEXT_RULES}
        for check, truth in expected.items():
            guess = predicted[check]
            key = "tp" if guess and truth else "fp" if guess else "fn" if truth else "tn"
            counts[check][key] += 1
            if key in ("fp", "fn"):
                failures.append({"file": item["file"], "check": check, "error": key, "ocr": text})
        read = set(_words(text))
        for line in item.get("expected_text", []):
            for word in _words(line):
                word_total += 1
                word_hits += word in read
    per_check = {}
    for check, c in counts.items():
        precision = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else None
        recall = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else None
        per_check[check] = {**c, "precision": precision, "recall": recall}
    issue_checks = [c for c in counts if c != "logo"]
    tp = sum(counts[c]["tp"] for c in issue_checks)
    fp = sum(counts[c]["fp"] for c in issue_checks)
    fn = sum(counts[c]["fn"] for c in issue_checks)
    ordered = sorted(latencies)
    return {
        "n_items": len(items),
        "metrics": {
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "ocr_word_recall": word_hits / word_total if word_total else None,
            "per_check": per_check,
        },
        "latency_s": {
            "p50": statistics.median(ordered),
            "p95": ordered[int(0.95 * (len(ordered) - 1))],
            "max": ordered[-1],
        },
        "failures": failures[:60],
        "environment": {
            "machine": platform.machine(),
            "processor": platform.processor() or platform.machine(),
            "python": platform.python_version(),
            "ocr_threads": get_settings().ocr_threads,
        },
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main() -> None:
    from app.db import SessionLocal
    from app.engine.context import load_context
    from app.seed import WORKSPACE_ID

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--export", type=Path, help="write the result as JSON")
    args = parser.parse_args()
    with SessionLocal() as session:
        ctx = load_context(session, WORKSPACE_ID, "linkedin")
    result = evaluate(ctx)
    metrics = result["metrics"]
    print(
        f"{result['n_items']} assets  precision {metrics['precision']:.3f}  "
        f"recall {metrics['recall']:.3f}  OCR word recall {metrics['ocr_word_recall']:.3f}"
    )
    for check, m in metrics["per_check"].items():
        p = "-" if m["precision"] is None else f"{m['precision']:.2f}"
        r = "-" if m["recall"] is None else f"{m['recall']:.2f}"
        print(f"  {check:7} P {p}  R {r}  tp {m['tp']} fp {m['fp']} fn {m['fn']} tn {m['tn']}")
    print(f"  latency p50 {result['latency_s']['p50']:.2f}s p95 {result['latency_s']['p95']:.2f}s")
    if args.export:
        args.export.write_text(json.dumps(result, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
