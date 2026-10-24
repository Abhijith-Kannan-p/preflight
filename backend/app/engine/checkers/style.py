"""StyleChecker (TON-03): exclamation-mark density and shouting in all caps."""

import math
import re

from app.engine.checkers.base import make_finding
from app.engine.context import ReviewContext
from app.engine.schema import Finding, NormalisedDoc
from app.engine.text import sentences

_CAPS_WORD = re.compile(r"\b[A-Z]{2,}\b")


class StyleChecker:
    name = "style"
    label = "Punctuation and capitals"

    async def run(self, doc: NormalisedDoc, ctx: ReviewContext) -> list[Finding]:
        rule = ctx.rule("TON-03")
        if rule is None:
            return []
        per_100 = float(rule.config.get("max_exclamations_per_100_words", 1))
        max_caps = int(rule.config.get("max_caps_word_length", 4))
        allowed = max(1, math.floor(per_100 * math.ceil(doc.word_count / 100)))
        product_names = {t.term.upper() for t in ctx.terms if t.kind == "product_name"}
        findings: list[Finding] = []

        seen = 0
        for block in doc.blocks:
            for sentence in sentences(block.text):
                count = sentence.text.count("!")
                if not count:
                    continue
                seen += count
                if seen > allowed:
                    findings.append(
                        make_finding(
                            rule,
                            type="tone",
                            block=block.id,
                            start=sentence.start,
                            end=sentence.end,
                            text=sentence.text,
                            explanation=(
                                f"{rule.code} allows at most {allowed} exclamation mark"
                                f"{'s' if allowed > 1 else ''} for a draft of this length "
                                f"({rule.source_ref}); this draft uses more."
                            ),
                            confidence=0.95,
                            suggestion=re.sub(r"!+", ".", sentence.text),
                        )
                    )

            for match in _CAPS_WORD.finditer(block.text):
                word = match.group(0)
                if len(word) <= max_caps or word in product_names:
                    continue
                findings.append(
                    make_finding(
                        rule,
                        type="tone",
                        block=block.id,
                        start=match.start(),
                        end=match.end(),
                        text=word,
                        explanation=(
                            f"All-caps words longer than {max_caps} letters read as shouting "
                            f"({rule.code}, {rule.source_ref})."
                        ),
                        confidence=0.9,
                        suggestion=word.capitalize(),
                    )
                )
        return findings
