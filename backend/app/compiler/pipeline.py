"""Run the Rulebook Compiler on one document as a background job.

Stages, each streamed over SSE with its timing: read the document (pages with numbers),
structured extraction (tables, word lists, colours, limits), LLM extraction of prose rules,
schema check and merge, and comparison with the workspace's rulebook. The result is a review
queue of candidates: nothing becomes active until a brand manager accepts it.
"""

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.masking import Masker
from app.compiler import llm
from app.compiler.apply import Matcher
from app.compiler.extract import CompileInputError, deterministic, read_docx, read_pdf
from app.compiler.schema import Candidate
from app.db import SessionLocal
from app.models import CompileJob, ConfidentialTerm, RuleCandidate, Workspace
from app.services.events import TERMINAL, bus

log = logging.getLogger(__name__)

STAGES = [
    ("parse", "Read the document"),
    ("structured", "Tables, word lists, colours and limits"),
    ("llm", "Prose rules (LLM)"),
    ("validate", "Schema check and merge"),
    ("match", "Compare with your rulebook"),
]

# Tests point this at the test database.
session_factory: Callable[[], Session] = SessionLocal


def merge(structured: list[Candidate], extracted: list[Candidate]) -> list[Candidate]:
    """One candidate per key. Structured extraction wins; list fields (triggers, variants)
    take the union, so the LLM can add a trigger the pattern missed."""
    merged: dict[str, Candidate] = {}
    for candidate in [*structured, *extracted]:
        existing = merged.get(candidate.key)
        if existing is None:
            merged[candidate.key] = candidate
            continue
        for field in ("triggers", "variants"):
            if field in existing.payload and field in candidate.payload:
                union = list(dict.fromkeys([*existing.payload[field], *candidate.payload[field]]))
                existing.payload = {**existing.payload, field: union}
    return list(merged.values())


def start(job_id: str, data: bytes, filename: str) -> None:
    threading.Thread(
        target=run, args=(job_id, data, filename), daemon=True, name=f"compile-{job_id}"
    ).start()


def run(job_id: str, data: bytes, filename: str) -> None:
    timings: dict[str, int] = {}

    def stage(name: str, label: str, started: float, found: int | None = None) -> None:
        ms = int((time.perf_counter() - started) * 1000)
        timings[name] = ms
        bus.publish(job_id, "stage_done", {"stage": name, "label": label, "ms": ms, "found": found})

    with session_factory() as session:
        job = session.get_one(CompileJob, job_id)
        try:
            started = time.perf_counter()
            bus.publish(job_id, "stage_started", {"stage": "parse"})
            pages = read_docx(data) if filename.lower().endswith(".docx") else read_pdf(data)
            stage("parse", STAGES[0][1], started, len(pages))

            started = time.perf_counter()
            bus.publish(job_id, "stage_started", {"stage": "structured"})
            structured = deterministic(pages)
            stage("structured", STAGES[1][1], started, len(structured))

            started = time.perf_counter()
            bus.publish(job_id, "stage_started", {"stage": "llm"})
            workspace = session.get_one(Workspace, job.workspace_id)
            confidential = tuple(
                session.scalars(
                    select(ConfidentialTerm.term).where(
                        ConfidentialTerm.workspace_id == job.workspace_id
                    )
                )
            )
            masker = Masker(
                confidential, enabled=bool(workspace.settings.get("masking_enabled", True))
            )
            extracted, llm_report = asyncio.run(llm.extract(pages, llm.compiler_gateway(), masker))
            stage("llm", STAGES[2][1], started, len(extracted))

            started = time.perf_counter()
            candidates = merge(structured, extracted)
            stage("validate", STAGES[3][1], started, len(candidates))

            started = time.perf_counter()
            matcher = Matcher(session, job.workspace_id)
            counts: dict[str, int] = {}
            for c in sorted(candidates, key=lambda c: (c.source_page, c.kind)):
                status, ref, note = matcher.match(c.kind, c.payload)
                counts[status] = counts.get(status, 0) + 1
                session.add(
                    RuleCandidate(
                        job_id=job.id,
                        kind=c.kind,
                        key=c.key,
                        extracted=c.payload,
                        payload=c.payload,
                        source_page=c.source_page,
                        excerpt=c.excerpt,
                        origin=c.origin,
                        match_status=status,
                        match_ref=ref,
                        match_note=note,
                    )
                )
            stage("match", STAGES[4][1], started, len(candidates))
            job.status = "ready"
            job.report = {
                "pages": len(pages),
                "timings_ms": timings,
                "llm": llm_report,
                "structured": len(structured),
                "from_llm": len(extracted),
                "candidates": len(candidates),
                "by_status": counts,
            }
            session.commit()
            bus.publish(job_id, TERMINAL, {"ok": True, **job.report})
        except CompileInputError as exc:
            _fail(session, job, str(exc))
        except Exception:
            log.exception("compile job %s failed", job_id)
            _fail(session, job, "The compiler hit an unexpected problem with this document.")


def _fail(session: Session, job: CompileJob, message: str) -> None:
    session.rollback()
    job = session.get_one(CompileJob, job.id)
    job.status, job.report = "failed", {"error": message}
    session.commit()
    bus.publish(job.id, TERMINAL, {"ok": False, "error": message})


def summary(job: CompileJob, candidates: list[RuleCandidate]) -> dict[str, Any]:
    decided = [c for c in candidates if c.decision != "pending"]
    accepted = [c for c in decided if c.decision in ("accepted", "edited")]
    return {
        "decided": len(decided),
        "accepted": len(accepted),
        "accepted_without_edits": sum(c.decision == "accepted" for c in accepted),
        "rejected": sum(c.decision == "rejected" for c in decided),
    }
