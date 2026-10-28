"""In-app notifications (the bell in the header).

New notifications are pushed to each recipient's live stream (`user:<id>` on the event bus)
once the transaction that created them commits, wherever they were created; the header falls
back to polling when the stream is down.
"""

from collections.abc import Iterable

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models import Notification, Role, Submission, User
from app.services.events import bus

NOTIFICATION_EVENT = "notification"
_PENDING = "pending_notifications"


def stream_key(user_id: str) -> str:
    return f"user:{user_id}"


@event.listens_for(Session, "after_flush")
def _collect(session: Session, _context: object) -> None:
    for obj in session.new:
        if isinstance(obj, Notification):
            session.info.setdefault(_PENDING, []).append(
                {"id": obj.id, "user_id": obj.user_id, "kind": obj.kind}
            )


@event.listens_for(Session, "after_commit")
def _push(session: Session) -> None:
    for item in session.info.pop(_PENDING, []):
        bus.publish(stream_key(item["user_id"]), NOTIFICATION_EVENT, item, keep=False)


@event.listens_for(Session, "after_rollback")
def _drop(session: Session) -> None:
    session.info.pop(_PENDING, None)


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
