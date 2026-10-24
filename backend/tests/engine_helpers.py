"""Helpers for engine tests: build a review context and run one checker on text."""

import asyncio
from datetime import date

from sqlalchemy.orm import Session

from app.engine.checkers.base import Checker
from app.engine.context import ReviewContext, load_context
from app.engine.normalise import from_text
from app.engine.schema import Finding
from app.seed import WORKSPACE_ID

TODAY = date(2026, 10, 22)

LINKEDIN_SAMPLE = (
    "Say hello to India's #1 and 100% secure payments app! Paywise now settles in under 5 "
    "seconds for every merchant. Download today and never worry again!"
)


def context(session: Session, channel: str = "linkedin") -> ReviewContext:
    return load_context(session, WORKSPACE_ID, channel, today=TODAY)


def check(checker: Checker, text: str, ctx: ReviewContext) -> list[Finding]:
    return asyncio.run(checker.run(from_text(text), ctx))
