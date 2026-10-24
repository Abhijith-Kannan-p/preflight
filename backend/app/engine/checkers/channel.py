"""ChannelChecker: length, hashtag and subject-line limits from the channel profile."""

import re

from app.engine.checkers.base import make_finding
from app.engine.context import ReviewContext
from app.engine.schema import Finding, NormalisedDoc

_HASHTAG = re.compile(r"(?<![\w#])#(?=\w*[A-Za-z])\w+")
_SUBJECT = re.compile(r"^subject:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


class ChannelChecker:
    name = "channel"
    label = "Channel limits"

    async def run(self, doc: NormalisedDoc, ctx: ReviewContext) -> list[Finding]:
        channel = ctx.channel
        if channel is None or channel.rule_code is None:
            return []
        rule = ctx.rule(channel.rule_code)
        if rule is None:
            return []
        findings: list[Finding] = []
        text = doc.text

        if channel.max_chars and len(text) > channel.max_chars:
            block = next(b for b in reversed(doc.blocks) if b.start_offset <= channel.max_chars)
            start = max(0, channel.max_chars - block.start_offset)
            findings.append(
                make_finding(
                    rule,
                    type="channel",
                    block=block.id,
                    start=start,
                    end=len(block.text),
                    text=block.text[start:],
                    explanation=(
                        f"{channel.name}s are limited to {channel.max_chars:,} characters "
                        f"({rule.code}, {rule.source_ref}). This draft has {len(text):,}."
                    ),
                    confidence=1.0,
                )
            )

        if channel.max_hashtags is not None:
            tags = [(b.id, m) for b in doc.blocks for m in _HASHTAG.finditer(b.text)]
            for block_id, match in tags[channel.max_hashtags :]:
                findings.append(
                    make_finding(
                        rule,
                        type="channel",
                        block=block_id,
                        start=match.start(),
                        end=match.end(),
                        text=match.group(0),
                        explanation=(
                            f"{channel.name}s allow at most {channel.max_hashtags} hashtags "
                            f"({rule.code}, {rule.source_ref}); this draft uses {len(tags)}."
                        ),
                        confidence=1.0,
                        suggestion="",
                    )
                )

        if channel.subject_max_chars:
            for block in doc.blocks:
                subject_match = _SUBJECT.search(block.text)
                if subject_match is None:
                    continue
                subject = subject_match.group(1).strip()
                if len(subject) > channel.subject_max_chars:
                    findings.append(
                        make_finding(
                            rule,
                            type="channel",
                            block=block.id,
                            start=subject_match.start(1),
                            end=subject_match.start(1) + len(subject),
                            text=subject,
                            explanation=(
                                f"Email subject lines are limited to {channel.subject_max_chars} "
                                f"characters ({rule.code}, {rule.source_ref}); this one has "
                                f"{len(subject)}."
                            ),
                            confidence=1.0,
                        )
                    )
                break
        return findings
