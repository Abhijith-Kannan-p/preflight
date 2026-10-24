"""ToneChecker (TON-01): score the five voice traits and flag those off the brand profile.

With an LLM, each trait gets a 0-1 score and a verbatim evidence quote. Without one (or if
the call fails), a transparent lexicon heuristic produces approximate scores at lower
confidence. Either way the comparison with the voice profile is deterministic.
"""

import re

from pydantic import BaseModel, Field, field_validator

from app.ai.session import AiSession
from app.engine.checkers.base import make_finding
from app.engine.context import ReviewContext
from app.engine.schema import Finding, NormalisedDoc
from app.engine.text import sentence_at, sentences, words

TRAITS = ("formal", "warm", "confident", "playful", "technical")
MAX_TONE_FINDINGS = 2
LLM_CONFIDENCE = 0.8
HEURISTIC_CONFIDENCE = 0.62

_HYPE = re.compile(
    r"#1\b|\b(best|leading|amazing|incredible|revolutionary|ultimate|unbeatable|guaranteed|"
    r"never|always|100%|completely|totally|fastest|cheapest)\b|100%",
    re.I,
)
_URGENCY = re.compile(r"\b(now|today|hurry|don't miss|limited time|act fast|right away)\b", re.I)
_SLANG = re.compile(r"\b(awesome|super|cool|gonna|wanna|lol|wow|hey|yay|epic|insane)\b", re.I)
_TECH = re.compile(
    r"\b(encryption|aes|pci|dss|kyc|mdr|upi|api|settle[sd]?|settlement|transactions?|"
    r"merchants?|iso|authentication|aggregator|uptime|net banking)\b",
    re.I,
)
_WARM = re.compile(r"\b(you|your|help|support|welcome|hello|thank|thanks|together|care|we)\b", re.I)
_EMOJI = re.compile("[\U0001f300-\U0001faff☀-➿]")
_CAPS = re.compile(r"\b[A-Z]{5,}\b")


class TraitScore(BaseModel):
    score: float = Field(ge=0, le=1)
    evidence: str = ""


class ToneScores(BaseModel):
    traits: dict[str, TraitScore]

    @field_validator("traits")
    @classmethod
    def all_traits(cls, v: dict[str, TraitScore]) -> dict[str, TraitScore]:
        missing = set(TRAITS) - set(v)
        if missing:
            raise ValueError(f"missing traits: {sorted(missing)}")
        return {t: v[t] for t in TRAITS}


class ToneProfile(BaseModel):
    source: str  # "llm" | "heuristic"
    scores: dict[str, float]
    targets: dict[str, float]
    evidence: dict[str, str]


def _clamp(x: float) -> float:
    return round(max(0.0, min(1.0, x)), 2)


def heuristic_scores(doc: NormalisedDoc) -> ToneScores:
    text = doc.text
    n_words = max(1, len(words(text)))
    n_sentences = max(1, sum(len(sentences(b.text)) for b in doc.blocks))
    exclaim = text.count("!") / n_sentences
    hype = (len(_HYPE.findall(text)) + len(_URGENCY.findall(text)) + text.count("!")) / n_sentences
    slang = len(_SLANG.findall(text)) / n_sentences
    emoji = len(_EMOJI.findall(text))
    caps = len(_CAPS.findall(text))
    second_person = len(re.findall(r"\b(you|your)\b", text, re.I)) / n_words
    scores = {
        "formal": _clamp(0.85 - 0.3 * hype - 0.15 * slang - 0.05 * emoji - 0.05 * caps),
        "warm": _clamp(0.4 + 2.0 * second_person + 0.05 * len(_WARM.findall(text))),
        "confident": _clamp(0.5 + 0.15 * len(_HYPE.findall(text))),
        "playful": _clamp(0.15 + 0.45 * exclaim + 0.2 * slang + 0.1 * emoji),
        "technical": _clamp(0.2 + 4.0 * len(_TECH.findall(text)) / n_words),
    }
    first = doc.blocks[0].text if doc.blocks else ""
    evidence = {t: _strongest_sentence(doc, t) or first for t in TRAITS}
    return ToneScores(traits={t: TraitScore(score=scores[t], evidence=evidence[t]) for t in TRAITS})


def _strongest_sentence(doc: NormalisedDoc, trait: str) -> str | None:
    pattern = {"formal": _HYPE, "confident": _HYPE, "playful": re.compile("!"),
               "warm": _WARM, "technical": _TECH}[trait]  # fmt: skip
    best = max(
        (s.text for b in doc.blocks for s in sentences(b.text)),
        key=lambda s: len(pattern.findall(s)),
        default=None,
    )
    return best


def _prompt(doc: NormalisedDoc, ctx: ReviewContext) -> str:
    return (
        "You score marketing copy against a brand voice. Score the TEXT from 0 to 1 on each "
        "trait: formal, warm, confident, playful, technical. For each trait also give "
        '"evidence": an exact quote of at most 15 words copied verbatim from the TEXT that '
        "most influenced the score.\n"
        f"Brand voice: {ctx.voice.get('description', '')}\n"
        'Return JSON: {"traits": {"formal": {"score": 0.0, "evidence": "..."}, '
        '"warm": {...}, "confident": {...}, "playful": {...}, "technical": {...}}}\n'
        f"TEXT:\n<<<\n{doc.text}\n>>>"
    )


class ToneChecker:
    name = "tone"
    label = "Tone of voice"

    def __init__(self, ai: AiSession | None) -> None:
        self.ai = ai
        self.profile: ToneProfile | None = None

    async def run(self, doc: NormalisedDoc, ctx: ReviewContext) -> list[Finding]:
        rule = ctx.rule("TON-01")
        targets: dict[str, float] = ctx.voice.get("traits", {})
        if rule is None or not targets:
            return []
        scores: ToneScores | None = None
        if self.ai is not None and self.ai.llm_available:
            scores = await self.ai.gateway.complete_json(
                _prompt(doc, ctx), ToneScores, purpose="tone", masker=self.ai.masker,
                log_to=self.ai.log,
            )  # fmt: skip
        source = "llm" if scores else "heuristic"
        scores = scores or heuristic_scores(doc)
        self.profile = ToneProfile(
            source=source,
            scores={t: s.score for t, s in scores.traits.items()},
            targets=targets,
            evidence={t: s.evidence for t, s in scores.traits.items()},
        )
        threshold = float(rule.config.get("threshold", 0.3))
        deviations = sorted(
            ((t, round(scores.traits[t].score - targets[t], 2)) for t in TRAITS if t in targets),
            key=lambda td: -abs(td[1]),
        )
        findings: list[Finding] = []
        for trait, delta in deviations[:MAX_TONE_FINDINGS]:
            if abs(delta) <= threshold:
                continue
            block_id, start, end, quote = _locate(doc, scores.traits[trait].evidence)
            direction = "more" if delta > 0 else "less"
            score, target = scores.traits[trait].score, targets[trait]
            findings.append(
                make_finding(
                    rule,
                    type="tone",
                    block=block_id,
                    start=start,
                    end=end,
                    text=quote,
                    explanation=(
                        f"This reads {direction} {trait} than the PayWise voice: "
                        f"{score:.2f} against a target of {target:.2f}. "
                        f"{rule.code} allows a deviation of {threshold:.1f} ({rule.source_ref}). "
                        f"Voice: {ctx.voice.get('description', '')}"
                        + ("" if source == "llm" else " (Estimated by the offline heuristic.)")
                    ),
                    confidence=LLM_CONFIDENCE if source == "llm" else HEURISTIC_CONFIDENCE,
                    detector="llm" if source == "llm" else "rules",
                )
            )
        return findings


def _locate(doc: NormalisedDoc, evidence: str) -> tuple[int, int, int, str]:
    """Find the sentence holding the evidence quote; fall back to the first sentence."""
    needle = evidence.strip().strip('"').lower()
    for block in doc.blocks:
        index = block.text.lower().find(needle) if needle else -1
        if index >= 0:
            sentence = sentence_at(block.text, index)
            return block.id, sentence.start, sentence.end, sentence.text
    first = doc.blocks[0]
    first_sentences = sentences(first.text)
    if not first_sentences:
        return first.id, 0, len(first.text), first.text
    opening = first_sentences[0]
    return first.id, opening.start, opening.end, opening.text
