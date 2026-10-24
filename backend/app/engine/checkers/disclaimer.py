"""DisclaimerChecker: trigger words require a disclaimer somewhere in the draft."""

from app.engine.checkers.base import make_finding
from app.engine.context import ReviewContext
from app.engine.schema import Finding, NormalisedDoc
from app.engine.text import compact, find_phrase, sentence_at


class DisclaimerChecker:
    name = "disclaimer"
    label = "Required disclaimers"

    async def run(self, doc: NormalisedDoc, ctx: ReviewContext) -> list[Finding]:
        findings: list[Finding] = []
        full = compact(doc.text)
        for rule in ctx.rules.values():
            if rule.category != "disclaimer":
                continue
            disclaimer: str = rule.config["disclaimer"]
            if compact(disclaimer) in full:
                continue
            hit = self._first_trigger(doc, rule.config["triggers"])
            if hit is None:
                continue
            block_id, start, trigger = hit
            block_text = doc.blocks[block_id].text
            sentence = sentence_at(block_text, start)
            findings.append(
                make_finding(
                    rule,
                    type="disclaimer",
                    block=block_id,
                    start=sentence.start,
                    end=sentence.end,
                    text=sentence.text,
                    explanation=(
                        f'This mentions "{trigger}", so {rule.code} requires the disclaimer '
                        f'"{disclaimer}" ({rule.source_ref}). It is missing from the draft.'
                    ),
                    confidence=0.95,
                    suggestion=f"{sentence.text.rstrip()} {disclaimer}",
                )
            )
        return findings

    @staticmethod
    def _first_trigger(doc: NormalisedDoc, triggers: list[str]) -> tuple[int, int, str] | None:
        best: tuple[int, int, str] | None = None
        for block in doc.blocks:
            for trigger in triggers:
                for match in find_phrase(block.text, trigger):
                    key = (block.id, match.start, match.text)
                    if best is None or key[:2] < best[:2]:
                        best = key
                    break
        return best
