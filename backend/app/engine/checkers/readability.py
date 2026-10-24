"""ReadabilityChecker: Flesch Reading Ease for consumer channels, plus over-long sentences."""

import textstat

from app.engine.checkers.base import make_finding
from app.engine.context import ReviewContext
from app.engine.schema import Finding, NormalisedDoc
from app.engine.text import sentences, words

# Flesch is unstable on very short copy, so the overall score needs a minimum length.
MIN_WORDS_FOR_FLESCH = 40


class ReadabilityChecker:
    name = "readability"
    label = "Readability"

    async def run(self, doc: NormalisedDoc, ctx: ReviewContext) -> list[Finding]:
        rule = ctx.rule("RDB-01")
        if rule is None or ctx.channel is None or not ctx.channel.consumer:
            return []
        min_flesch = float(rule.config.get("min_flesch", 50))
        max_words = int(rule.config.get("max_sentence_words", 30))
        findings: list[Finding] = []

        all_sentences = [(b.id, s) for b in doc.blocks for s in sentences(b.text)]
        for block_id, sentence in all_sentences:
            count = len(words(sentence.text))
            if count > max_words:
                findings.append(
                    make_finding(
                        rule,
                        type="readability",
                        block=block_id,
                        start=sentence.start,
                        end=sentence.end,
                        text=sentence.text,
                        explanation=(
                            f"This sentence has {count} words; consumer copy should keep "
                            f"sentences under {max_words} ({rule.code}, {rule.source_ref}). "
                            "Consider splitting it."
                        ),
                        confidence=0.85,
                    )
                )

        if doc.word_count >= MIN_WORDS_FOR_FLESCH and all_sentences:
            score = float(textstat.flesch_reading_ease(doc.text))
            if score < min_flesch:
                block_id, hardest = min(
                    all_sentences, key=lambda bs: float(textstat.flesch_reading_ease(bs[1].text))
                )
                findings.append(
                    make_finding(
                        rule,
                        type="readability",
                        block=block_id,
                        start=hardest.start,
                        end=hardest.end,
                        text=hardest.text,
                        explanation=(
                            f"The draft's Flesch Reading Ease is {score:.0f}; {rule.code} asks for "
                            f"{min_flesch:.0f} or higher on consumer channels ({rule.source_ref}). "
                            "This is the hardest sentence to read."
                        ),
                        confidence=0.75,
                    )
                )
        return findings
