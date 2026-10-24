"""LLM claim extraction. The LLM only proposes claims; verdicts come from retrieval + NLI.

Returned claims must be verbatim substrings of the draft, otherwise they are discarded.
"""

from pydantic import BaseModel, Field

from app.ai.session import AiSession
from app.engine.claims.detect import ClaimCandidate
from app.engine.claims.ledger import ClaimExtractor
from app.engine.context import ReviewContext
from app.engine.schema import NormalisedDoc
from app.engine.text import TextSpan

CLAIM_TYPES = {"numeric", "superlative", "absolute", "comparative", "offer", "guarantee", "factual"}


class ExtractedClaim(BaseModel):
    text: str = Field(min_length=3, max_length=400)
    claim_type: str = "factual"


class ExtractedClaims(BaseModel):
    claims: list[ExtractedClaim] = Field(default_factory=list, max_length=40)


def _prompt(doc: NormalisedDoc) -> str:
    return (
        "List every factual, checkable claim in the TEXT: numbers, durations, prices, fees, "
        "capabilities, certifications, superlatives, comparisons, guarantees and offers. "
        "Skip greetings, calls to action and opinions with no factual content. Copy each "
        "claim exactly as written in the TEXT (a clause, not a summary).\n"
        'Return JSON: {"claims": [{"text": "...", "claim_type": "numeric|superlative|'
        'absolute|comparative|offer|guarantee|factual"}]}\n'
        f"TEXT:\n<<<\n{doc.text}\n>>>"
    )


def llm_extractor(ai: AiSession) -> ClaimExtractor:
    async def extract(doc: NormalisedDoc, ctx: ReviewContext) -> list[ClaimCandidate]:
        if not ai.llm_available:
            return []
        result = await ai.gateway.complete_json(
            _prompt(doc),
            ExtractedClaims,
            purpose="claim_detection",
            masker=ai.masker,
            log_to=ai.log,
        )
        if result is None:
            return []
        candidates: list[ClaimCandidate] = []
        for claim in result.claims:
            text = claim.text.strip().rstrip(".")
            for block in doc.blocks:
                start = block.text.find(text)
                if start < 0:
                    continue
                span = TextSpan(start, start + len(text), text)
                claim_type = claim.claim_type if claim.claim_type in CLAIM_TYPES else "factual"
                candidates.append(ClaimCandidate(block.id, span, text, claim_type, source="llm"))
                break
        return candidates

    return extract
