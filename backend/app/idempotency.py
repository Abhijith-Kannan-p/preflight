"""`Idempotency-Key` support for every POST, PUT, PATCH and DELETE.

The first request with a key runs normally and, if it succeeds, its response is stored. A
repeat of the same key by the same caller gets the stored response (marked
`Idempotent-Replayed: true`) instead of running again, so a double-click, a retried network
call or two tabs can never create two reviews, two decisions or two approvals. A repeat that
arrives while the first is still running gets 409. Keys are kept for 24 hours.
"""

import hashlib
import inspect
import logging
from collections.abc import Awaitable, Callable, Generator
from datetime import timedelta
from typing import Any

import jwt
from fastapi import FastAPI, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.config import get_settings
from app.db import get_session
from app.models import IdempotencyKey, utcnow

log = logging.getLogger(__name__)

HEADER = "idempotency-key"
METHODS = {"POST", "PUT", "PATCH", "DELETE"}
KEEP_FOR = timedelta(hours=24)
MAX_STORED_BYTES = 256 * 1024


def _scope(request: Request) -> str:
    """Who the key belongs to: the signed-in user, the API key, or the client address."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            claims = jwt.decode(auth[7:], get_settings().jwt_secret, algorithms=["HS256"])
            return str(claims.get("sub"))[:64]
        except jwt.PyJWTError:
            pass
    api_key = request.headers.get("x-api-key")
    if api_key:
        return "key:" + hashlib.sha256(api_key.encode()).hexdigest()[:48]
    return "ip:" + (request.client.host if request.client else "unknown")


def _open_session(app: FastAPI) -> tuple[Session, Generator[Session, None, None] | None]:
    """A session from the app's own provider (tests override it with their database)."""
    provider = app.dependency_overrides.get(get_session, get_session)
    result = provider()
    if inspect.isgenerator(result):
        return next(result), result
    return result, None


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        key = request.headers.get(HEADER)
        if request.method not in METHODS or not key:
            return await call_next(request)
        if len(key) > 100:
            return JSONResponse({"detail": "Idempotency-Key must be 100 characters or fewer."}, 422)
        scope, path = _scope(request), request.url.path
        session, closer = _open_session(request.app)
        try:
            existing = session.scalar(
                select(IdempotencyKey).where(
                    IdempotencyKey.scope == scope, IdempotencyKey.key == key
                )
            )
            if existing is not None and utcnow() - existing.created_at > KEEP_FOR:
                session.delete(existing)
                session.commit()
                existing = None
            if existing is not None:
                return self._replay(existing, request.method, path)
            row = IdempotencyKey(scope=scope, key=key, method=request.method, path=path)
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                # Another request with the same key got there first.
                session.rollback()
                return JSONResponse(
                    {"detail": "This request is already being processed."}, status_code=409
                )
            response = await call_next(request)
            body = b"".join([chunk async for chunk in response.body_iterator])  # type: ignore[attr-defined]
            if not 200 <= response.status_code < 300 or len(body) > MAX_STORED_BYTES:
                # Only successes are replayed: after a refusal (say, a missing override reason)
                # the corrected request may reuse the key. Huge bodies are not stored.
                session.delete(row)
            else:
                row.status_code, row.body = response.status_code, body.decode("utf-8", "replace")
            session.commit()
            return Response(
                body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
        finally:
            if closer is not None:
                closer.close()

    @staticmethod
    def _replay(row: IdempotencyKey, method: str, path: str) -> Response:
        if row.method != method or row.path != path:
            return JSONResponse(
                {"detail": "This Idempotency-Key was already used for a different request."},
                status_code=422,
            )
        if row.status_code is None:
            return JSONResponse(
                {"detail": "This request is already being processed."}, status_code=409
            )
        return Response(
            row.body or "",
            status_code=row.status_code,
            media_type="application/json",
            headers={"Idempotent-Replayed": "true"},
        )


def purge_expired(session: Session) -> int:
    cutoff = utcnow() - KEEP_FOR
    result: Any = session.execute(delete(IdempotencyKey).where(IdempotencyKey.created_at < cutoff))
    session.commit()
    return int(result.rowcount or 0)
