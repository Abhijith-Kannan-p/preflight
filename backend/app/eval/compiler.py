"""Evaluate the Rulebook Compiler on the sample brand book against hand-labelled rules.

    python -m app.eval.compiler --export ../data/eval/compiler_run.json

Two runs: structured extraction only (what you get when the LLM is down) and structured plus
LLM. For each run:

- recall: share of labelled rules that appear as a candidate
- precision: share of candidates that match a labelled rule
- page_correct: share of matched candidates citing the labelled page
- exact: share of matched candidates whose payload equals the label, i.e. a brand manager
  would accept it without edits (the target is 80% or more)

Guidance rules are free text, so they match on page, category and any keyword. A disclaimer
trigger that only narrows a labelled one ("paywise pay later" next to "pay later") needs no
edit: it never changes what the rule fires on. LLM output varies, so the LLM run is repeated
and every run is reported along with the mean.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from app.ai.masking import Masker
from app.compiler import llm
from app.compiler.extract import deterministic, read_pdf
from app.compiler.pipeline import merge
from app.compiler.schema import Candidate
from app.config import get_settings

COMPARED = {
    "term": ("term", "variants"),
    "word": ("term", "status", "replacement"),
    "pattern": ("rule", "pattern"),
    "disclaimer": ("triggers", "disclaimer"),
    "colour": ("name", "hex"),
    "channel": ("channel", "max_chars", "max_hashtags", "subject_max_chars"),
    "threshold": ("rule", "field", "value"),
    "voice": ("traits",),
}


def _same(value: Any, label: Any) -> bool:
    if isinstance(label, list):
        return {str(v).lower() for v in value or []} == {str(v).lower() for v in label}
    if isinstance(label, dict):
        return all(abs(float(value.get(k, -9)) - float(v)) < 0.01 for k, v in label.items())
    if isinstance(label, str):
        return str(value or "").strip().lower() == label.strip().lower()
    return bool(value == label)


def _field_ok(field: str, value: Any, label: Any) -> bool:
    if field != "triggers":
        return _same(value, label)
    want = {t.lower() for t in label}
    got = {str(t).lower() for t in value or []}
    return want <= got and all(any(w in t for w in want) for t in got)


def _identity(label: dict[str, Any], c: Candidate) -> bool:
    """Is this candidate about the labelled rule (whatever its details)?"""
    if c.kind != label["kind"]:
        return False
    p, want = c.payload, label["payload"]
    if c.kind == "guidance":
        text = f"{p['title']} {p['description']}".lower()
        return (
            c.source_page == label["page"]
            and p["category"] == want["category"]
            and any(k.lower() in text for k in label["keywords"])
        )
    first = COMPARED[c.kind][0]
    if c.kind == "disclaimer":
        return _same(p["disclaimer"], want["disclaimer"])
    if c.kind in ("pattern", "threshold"):
        return _same(p["rule"], want["rule"]) and _same(
            p[COMPARED[c.kind][1]], want[COMPARED[c.kind][1]]
        )
    if c.kind == "colour":
        return _same(p["hex"], want["hex"])
    return _same(p.get(first), want.get(first))


def score(labels: list[dict[str, Any]], candidates: list[Candidate]) -> dict[str, Any]:
    used: set[int] = set()
    found = exact = pages = 0
    misses: list[str] = []
    edits: list[str] = []
    for label in labels:
        hit = next(
            (i for i, c in enumerate(candidates) if i not in used and _identity(label, c)), None
        )
        name = label.get("label") or f"{label['kind']} {json.dumps(label['payload'])[:60]}"
        if hit is None:
            misses.append(f"p{label['page']} {name}")
            continue
        used.add(hit)
        found += 1
        c = candidates[hit]
        pages += c.source_page == label["page"]
        fields = COMPARED.get(c.kind, ())
        if all(_field_ok(f, c.payload.get(f), label["payload"][f]) for f in fields):
            exact += 1
        else:
            edits.append(f"p{label['page']} {name}")
    extra = [f"p{c.source_page} {c.key}" for i, c in enumerate(candidates) if i not in used]
    return {
        "labelled": len(labels),
        "candidates": len(candidates),
        "found": found,
        "recall": round(found / len(labels), 3) if labels else 0.0,
        "precision": round(len(used) / len(candidates), 3) if candidates else 0.0,
        "exact": exact,
        "page_correct": round(pages / found, 3) if found else 0.0,
        "accepted_without_edits": round(exact / found, 3) if found else 0.0,
        "missed": misses,
        "needs_edit": edits,
        "unlabelled": extra,
    }


async def evaluate(llm_runs: int) -> dict[str, Any]:
    settings = get_settings()
    labels = json.loads(
        (settings.data_dir / "eval" / "brand_book_expected.json").read_text("utf-8")
    )
    pages = read_pdf((settings.data_dir / "samples" / "paywise_brand_book.pdf").read_bytes())
    structured = deterministic(pages)
    runs: dict[str, Any] = {"structured_only": score(labels["rules"], structured)}
    trials = []
    for _ in range(llm_runs):
        started = time.perf_counter()
        gateway = llm.compiler_gateway()
        extracted, report = await llm.extract(pages, gateway, Masker((), enabled=False))
        trials.append(
            {
                **score(labels["rules"], merge(deterministic(pages), extracted)),
                "llm": report,
                "llm_seconds": round(time.perf_counter() - started, 1),
            }
        )
    if trials:
        mean = {
            k: round(sum(t[k] for t in trials) / len(trials), 3)
            for k in (
                "recall",
                "precision",
                "accepted_without_edits",
                "page_correct",
                "llm_seconds",
            )
        }
        runs["structured_and_llm"] = {
            **trials[-1],
            **mean,
            "model": settings.llm_model,
            "trials": [{k: t[k] for k in (*mean, "found", "exact", "llm")} for t in trials],
        }
    return {"source": labels["source"], "runs": runs}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path)
    parser.add_argument("--llm-runs", type=int, default=3, help="0 skips the LLM")
    args = parser.parse_args()
    result = asyncio.run(evaluate(args.llm_runs))
    result["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for name, run in result["runs"].items():
        print(
            f"{name}: recall {run['recall']:.0%}, precision {run['precision']:.0%}, "
            f"accepted without edits {run['accepted_without_edits']:.0%} "
            f"({run['exact']}/{run['found']})"
        )
        for trial in run.get("trials", []):
            print(f"  trial: recall {trial['recall']:.0%}, exact {trial['exact']}/{trial['found']}")
        for key in ("missed", "needs_edit", "unlabelled"):
            if run[key]:
                print(f"  {key}: {', '.join(run[key])}")
    if args.export:
        args.export.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", "utf-8")


if __name__ == "__main__":
    main()
