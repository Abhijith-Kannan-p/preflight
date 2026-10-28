"""Per-visitor demo sandboxes.

`POST /api/sandbox/session` is the web app's entry point: it resumes the visitor's sandbox
from the httpOnly `pf_sandbox` cookie, or clones a fresh one from the PayWise template, and
signs in as a demo persona. The frontend calls it through its own origin (a Next.js rewrite),
so the cookie is first-party and survives strict third-party cookie blocking.
"""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.session import SessionOut, session_out
from app.config import get_settings
from app.db import get_session
from app.models import utcnow
from app.services import sandbox

router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])

COOKIE = "pf_sandbox"


class SandboxSessionIn(BaseModel):
    user_id: str | None = None


class SandboxSessionOut(SessionOut):
    created: bool
    expires_after_idle_hours: int


def _set_cookie(response: Response, workspace_id: str) -> None:
    response.set_cookie(
        COOKIE,
        workspace_id,
        max_age=7 * 24 * 3600,
        httponly=True,
        secure=get_settings().sandbox_cookie_secure,
        samesite="lax",
        path="/",
    )


def _out(user: object, created: bool) -> SandboxSessionOut:
    base = session_out(user)  # type: ignore[arg-type]
    return SandboxSessionOut(
        **base.model_dump(),
        created=created,
        expires_after_idle_hours=int(sandbox.IDLE_LIMIT.total_seconds() // 3600),
    )


@router.post("/session", response_model=SandboxSessionOut)
def sandbox_session(
    body: SandboxSessionIn,
    response: Response,
    pf_sandbox: str | None = Cookie(None),
    session: Session = Depends(get_session),
) -> SandboxSessionOut:
    """Resume or create this visitor's sandbox and sign in as `user_id` (a persona such as
    `usr_abhi1`, or a member id from `/api/users`). Default: abhi1, the Creator."""
    workspace = sandbox.live_sandbox(session, pf_sandbox)
    created = workspace is None
    if workspace is None:
        workspace = sandbox.create_sandbox(session)
    else:
        workspace.last_active_at = utcnow()
        session.commit()
    user = sandbox.find_user(session, workspace.id, body.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown demo user.")
    _set_cookie(response, workspace.id)
    return _out(user, created)


@router.post("/reset", response_model=SandboxSessionOut)
def reset(
    body: SandboxSessionIn,
    response: Response,
    pf_sandbox: str | None = Cookie(None),
    session: Session = Depends(get_session),
) -> SandboxSessionOut:
    """Reset this visitor's sandbox to the starting PayWise data. Nobody else is affected."""
    workspace = sandbox.live_sandbox(session, pf_sandbox)
    if workspace is None:
        workspace = sandbox.create_sandbox(session)
        created = True
    else:
        sandbox.reset_sandbox(session, workspace.id)
        created = False
    user = sandbox.find_user(session, workspace.id, body.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown demo user.")
    _set_cookie(response, workspace.id)
    return _out(user, created)
