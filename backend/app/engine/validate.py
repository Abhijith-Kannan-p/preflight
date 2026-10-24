"""Reject findings that do not hold up: unknown rule or fact IDs, or spans that do not match.

This is the guard that keeps every output traceable to a real rule or approved fact, whatever
produced it (rules, NLI or an LLM).
"""

import logging

from app.engine.context import ReviewContext
from app.engine.schema import Finding, NormalisedDoc

log = logging.getLogger(__name__)


class FindingRejected(ValueError):
    pass


def check_finding(finding: Finding, doc: NormalisedDoc, ctx: ReviewContext) -> None:
    if finding.rule.id not in ctx.rules:
        raise FindingRejected(f"unknown rule {finding.rule.id}")
    for evidence in finding.evidence:
        if evidence.fact_id not in ctx.facts:
            raise FindingRejected(f"unknown fact {evidence.fact_id}")
    if finding.span.block >= len(doc.blocks):
        raise FindingRejected(f"block {finding.span.block} out of range")
    block_text = doc.blocks[finding.span.block].text
    if not (0 <= finding.span.start <= finding.span.end <= len(block_text)):
        raise FindingRejected("span out of range")
    if block_text[finding.span.start : finding.span.end] != finding.text:
        raise FindingRejected("span text does not match the document")


def valid_findings(
    findings: list[Finding], doc: NormalisedDoc, ctx: ReviewContext
) -> list[Finding]:
    kept: list[Finding] = []
    for finding in findings:
        try:
            check_finding(finding, doc, ctx)
        except FindingRejected as exc:
            log.warning("finding rejected (%s): %s", exc, finding.model_dump_json())
            continue
        kept.append(finding)
    return kept
