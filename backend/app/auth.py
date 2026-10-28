"""Demo authentication and permissions.

Each seeded user gets a signed JWT; the role switcher in the header swaps tokens instantly.
Permissions follow the Round 1 plan's table and are enforced here, not only in the UI.
"""

import enum
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.models import SANDBOX_KIND, TEMPLATE_WORKSPACE_ID, Role, User, Workspace, utcnow

TOKEN_TTL = timedelta(days=7)
# A sandbox's activity clock is written at most this often, not on every request.
TOUCH_EVERY = timedelta(minutes=5)
_bearer = HTTPBearer(auto_error=False)


class Permission(str, enum.Enum):
    submit_content = "submit_content"
    comment = "comment"
    edit_rulebook = "edit_rulebook"
    approve = "approve"
    administer = "administer"
    view_insights = "view_insights"
    decide_findings = "decide_findings"
    escalate = "escalate"


PERMISSIONS: dict[Permission, set[Role]] = {
    Permission.submit_content: {Role.creator, Role.brand_manager},
    Permission.comment: {Role.creator, Role.reviewer, Role.brand_manager, Role.approver},
    Permission.edit_rulebook: {Role.brand_manager},
    Permission.approve: {Role.brand_manager, Role.approver},
    Permission.administer: {Role.admin},
    Permission.view_insights: {Role.reviewer, Role.brand_manager, Role.approver, Role.admin},
    # Accept / edit / dispute a finding: whoever writes the content.
    Permission.decide_findings: {Role.creator, Role.brand_manager},
    Permission.escalate: {Role.creator, Role.reviewer, Role.brand_manager},
}


def can(user: User, permission: Permission) -> bool:
    return user.role in PERMISSIONS[permission]


def permissions_for(role: Role) -> list[str]:
    return [p.value for p, roles in PERMISSIONS.items() if role in roles]


def issue_token(user: User) -> str:
    now = datetime.now(UTC)
    payload = {"sub": user.id, "role": user.role.value, "iat": now, "exp": now + TOKEN_TTL}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


def _touch(session: Session, workspace_id: str) -> None:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None or workspace.kind != SANDBOX_KIND:
        return
    now = utcnow()
    if workspace.last_active_at is None or now - workspace.last_active_at > TOUCH_EVERY:
        workspace.last_active_at = now
        session.commit()


def _user_from(credentials: HTTPAuthorizationCredentials, session: Session) -> User:
    try:
        payload = jwt.decode(
            credentials.credentials, get_settings().jwt_secret, algorithms=["HS256"]
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Session expired. Pick a demo user."
        ) from exc
    user = session.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Your demo workspace has expired. Reload the page to start a fresh one.",
        )
    _touch(session, user.workspace_id)
    return user


def user_from_query_token(token: str, session: Session) -> User:
    """For EventSource streams, which cannot send an Authorization header."""
    try:
        claims = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token.") from exc
    user = session.get(User, claims.get("sub"))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user.")
    return user


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in with a demo user first.")
    return _user_from(credentials, session)


def current_workspace_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> str:
    """The caller's workspace for read endpoints that also work signed out (the template)."""
    if credentials is None:
        return TEMPLATE_WORKSPACE_ID
    return _user_from(credentials, session).workspace_id


def require(permission: Permission):  # type: ignore[no-untyped-def]
    """FastAPI dependency factory: the current user must hold `permission`."""

    def dependency(user: User = Depends(current_user)) -> User:
        if not can(user, permission):
            role = user.role.value.replace("_", " ")
            action = permission.value.replace("_", " ")
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Your role ({role}) cannot {action}.")
        return user

    return dependency
