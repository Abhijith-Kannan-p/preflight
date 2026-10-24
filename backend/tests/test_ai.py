import asyncio
import json

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.claims import llm_extractor
from app.ai.gateway import CallLog, CircuitBreaker, Completion, Gateway, ProviderError
from app.ai.masking import Masker
from app.ai.session import AiSession
from app.ai.suggest import add_suggestions
from app.engine.checkers.base import make_finding
from app.engine.checkers.tone import ToneChecker, heuristic_scores
from app.engine.normalise import from_text
from app.engine.pipeline import default_checkers, run_review
from tests.engine_helpers import LINKEDIN_SAMPLE, context


class FakeProvider:
    """Returns queued responses; an Exception in the queue is raised instead."""

    name, model = "fake", "fake-1"

    def __init__(self, *responses: str | Exception) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    async def complete(self, prompt: str, timeout: float) -> Completion:
        self.prompts.append(prompt)
        item = self.responses.pop(0) if self.responses else ProviderError("empty")
        if isinstance(item, Exception):
            raise item
        return Completion(item, 10, 5)


class Answer(BaseModel):
    answer: str


def _gateway(*responses: str | Exception) -> tuple[Gateway, FakeProvider]:
    provider = FakeProvider(*responses)
    return Gateway(provider, timeout=1), provider


# --- Masking ---------------------------------------------------------------------------


def test_mask_round_trip_hides_confidential_data() -> None:
    masker = Masker(("Project Falcon", "PayWise Gold"))
    text = (
        "Project Falcon and PayWise Gold launch at ₹499/month. Email ops@paywise.example "
        "or call +91 98765 43210. project falcon again."
    )
    masked = masker.mask(text)
    for secret in ("Project Falcon", "PayWise Gold", "₹499/month", "ops@paywise.example", "98765"):
        assert secret.lower() not in masked.lower()
    assert "[CONFIDENTIAL_1]" in masked and "[PRICE_1]" in masked
    assert masker.mask("Project Falcon") == "[CONFIDENTIAL_1]"  # same value, same token
    assert masker.unmask(masked) == text  # exact round trip, original casing kept


def test_masking_can_be_disabled() -> None:
    masker = Masker(("Project Falcon",), enabled=False)
    assert masker.mask("Project Falcon") == "Project Falcon"


# --- Gateway ---------------------------------------------------------------------------


def test_gateway_masks_prompt_and_unmasks_response() -> None:
    gateway, provider = _gateway(json.dumps({"answer": "About [CONFIDENTIAL_1]"}))
    masker, log = Masker(("Project Falcon",)), CallLog()
    result = asyncio.run(
        gateway.complete_json(
            "Tell me about Project Falcon", Answer, purpose="t", masker=masker, log_to=log
        )
    )
    assert "Project Falcon" not in provider.prompts[0]
    assert result and result.answer == "About Project Falcon"
    assert log.calls[0].ok and log.calls[0].masked_count == 1


def test_gateway_retries_once_then_returns_none() -> None:
    gateway, provider = _gateway("not json", ProviderError("down"))
    log = CallLog()
    result = asyncio.run(
        gateway.complete_json("x", Answer, purpose="t", masker=Masker(), log_to=log)
    )
    assert result is None
    assert len(provider.prompts) == 2
    assert not log.calls[0].ok


def test_gateway_rejects_responses_that_fail_the_schema() -> None:
    gateway, _ = _gateway(json.dumps({"wrong": 1}), json.dumps({"answer": "ok"}))
    result = asyncio.run(gateway.complete_json("x", Answer, purpose="t", masker=Masker()))
    assert result and result.answer == "ok"  # first response rejected, retry accepted


def test_circuit_breaker_opens_after_repeated_failures() -> None:
    breaker = CircuitBreaker(threshold=2, cooldown=60)
    gateway = Gateway(FakeProvider(*[ProviderError("x")] * 10), timeout=1, breaker=breaker)
    for _ in range(2):
        asyncio.run(gateway.complete_json("x", Answer, purpose="t", masker=Masker()))
    assert breaker.open
    assert gateway.mode == "degraded"
    assert asyncio.run(gateway.complete_json("x", Answer, purpose="t", masker=Masker())) is None


def test_no_provider_means_deterministic_mode() -> None:
    gateway = Gateway(None, timeout=1)
    assert gateway.mode == "deterministic" and not gateway.available


# --- Tone ------------------------------------------------------------------------------


def test_heuristic_tone_flags_hype_and_passes_calm_copy(session: Session) -> None:
    ctx = context(session)
    hype = asyncio.run(ToneChecker(None).run(from_text(LINKEDIN_SAMPLE), ctx))
    assert [f.rule.id for f in hype] == ["TON-01"]
    assert hype[0].confidence < 0.7  # heuristic is marked less certain
    calm = (
        "PayWise settles merchant payments in under 10 seconds. You can start taking "
        "payments with digital KYC, and our support team is here to help you."
    )
    assert asyncio.run(ToneChecker(None).run(from_text(calm), ctx)) == []
    assert heuristic_scores(from_text(calm)).traits["formal"].score > 0.6


def test_llm_tone_scores_are_compared_with_profile(session: Session) -> None:
    traits = {
        t: {"score": 0.5, "evidence": "Download today"}
        for t in ("formal", "warm", "confident", "technical")
    }
    traits["playful"] = {"score": 0.95, "evidence": "never worry again"}
    gateway, _ = _gateway(json.dumps({"traits": traits}))
    checker = ToneChecker(AiSession(gateway, Masker()))
    findings = asyncio.run(checker.run(from_text(LINKEDIN_SAMPLE), context(session)))
    assert checker.profile and checker.profile.source == "llm"
    assert findings[0].text == "Download today and never worry again!"
    assert "more playful" in findings[0].explanation


# --- Claim extraction and suggestions --------------------------------------------------


def test_llm_claims_must_be_verbatim(session: Session) -> None:
    response = {
        "claims": [
            {"text": "settles in under 5 seconds", "claim_type": "numeric"},
            {"text": "invented claim not in text", "claim_type": "factual"},
        ]
    }
    gateway, _ = _gateway(json.dumps(response))
    extract = llm_extractor(AiSession(gateway, Masker()))
    claims = asyncio.run(extract(from_text(LINKEDIN_SAMPLE), context(session)))
    assert [c.span.text for c in claims] == ["settles in under 5 seconds"]
    assert claims[0].source == "llm"


def test_suggestions_prefer_rule_fallback_and_reject_invented_numbers(session: Session) -> None:
    ctx = context(session)
    doc = from_text("PayWise is 100% secure. PayWise has won 7 national awards.")
    absolute = make_finding(
        ctx.rules["CLM-04"],
        type="unsupported_claim",
        block=0,
        start=11,
        end=22,
        text="100% secure",
        explanation="e",
        confidence=0.95,
    )
    awards = make_finding(
        ctx.rules["CLM-05"],
        type="unsupported_claim",
        block=0,
        start=24,
        end=58,
        text="PayWise has won 7 national awards.",
        explanation="e",
        confidence=0.85,
    )
    gateway, provider = _gateway(
        json.dumps(
            {"rewrites": [{"id": awards.id, "replacement": "PayWise has won 9 national awards."}]}
        )
    )
    asyncio.run(add_suggestions(doc, [absolute, awards], ctx, AiSession(gateway, Masker())))
    assert absolute.suggestion and absolute.suggestion.text == "bank-grade encrypted"
    assert awards.suggestion is None  # "9" is not in the sentence or any approved fact
    assert awards.id in provider.prompts[0] and absolute.id not in provider.prompts[0]


def test_full_review_reports_ai_limited_when_llm_fails(session: Session) -> None:
    gateway, _ = _gateway(*[ProviderError("down")] * 10)
    ctx = context(session)
    ai = AiSession(gateway, Masker(ctx.confidential))
    plan = default_checkers(nli=None, embedder=None, ai=ai)
    result = asyncio.run(run_review(from_text(LINKEDIN_SAMPLE), ctx, plan.checkers, ai=ai))
    assert result.degraded
    assert "CLM-04" in {f.rule.id for f in result.findings}  # deterministic checks still ran
    assert plan.tone.profile and plan.tone.profile.source == "heuristic"
