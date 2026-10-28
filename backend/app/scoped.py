"""Lookups of rows whose ids are only unique within a workspace (`F-087`, `linkedin`)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChannelProfile, Fact, SampleDraft


def get_fact(session: Session, workspace_id: str, fact_id: str) -> Fact | None:
    return session.scalar(select(Fact).where(Fact.workspace_id == workspace_id, Fact.id == fact_id))


def get_channel(session: Session, workspace_id: str, channel_id: str) -> ChannelProfile | None:
    return session.scalar(
        select(ChannelProfile).where(
            ChannelProfile.workspace_id == workspace_id, ChannelProfile.id == channel_id
        )
    )


def get_sample(session: Session, workspace_id: str, sample_id: str) -> SampleDraft | None:
    return session.scalar(
        select(SampleDraft).where(
            SampleDraft.workspace_id == workspace_id, SampleDraft.id == sample_id
        )
    )
