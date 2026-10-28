"""In-app notifications (the bell in the header)."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Notification, Role, Submission, User


def notify_users(
    session: Session, user_ids: Iterable[str], kind: str, message: str, submission_id: str
) -> None:
    for user_id in set(user_ids):
        session.add(
            Notification(user_id=user_id, kind=kind, message=message, submission_id=submission_id)
        )


def notify_roles(
    session: Session,
    roles: Iterable[Role],
    kind: str,
    message: str,
    submission_id: str,
    exclude: str | None = None,
) -> None:
    workspace = select(Submission.workspace_id).where(Submission.id == submission_id)
    users = session.scalars(
        select(User.id).where(User.role.in_(list(roles)), User.workspace_id.in_(workspace))
    )
    notify_users(session, (u for u in users if u != exclude), kind, message, submission_id)
