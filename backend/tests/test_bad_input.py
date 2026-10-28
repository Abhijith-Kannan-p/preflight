"""Every kind of bad input gets a clear message, never a 500 or a stack trace."""

import io
import threading
from collections.abc import Iterator

import fitz
import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import create_app
from app.services import runner

Headers = dict[str, str]


@pytest.fixture
def api(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    connection = session.connection()
    monkeypatch.setattr(
        runner,
        "session_factory",
        lambda: Session(bind=connection, join_transaction_mode="create_savepoint"),
    )

    def run_and_wait(revision_id: str) -> None:
        worker = threading.Thread(target=runner.run_revision, args=(revision_id,))
        worker.start()
        worker.join()

    monkeypatch.setattr(runner, "start_review", run_and_wait)
    yield client


@pytest.fixture
def riya(api: TestClient) -> Headers:
    token = api.post("/api/auth/demo-login", json={"user_id": "usr_abhi1"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _encrypted_pdf() -> bytes:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "PayWise launch notes")
    buffer = io.BytesIO()
    doc.save(buffer, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
    return buffer.getvalue()


def _upload(api: TestClient, headers: Headers, name: str, data: bytes) -> tuple[int, str]:
    response = api.post(
        "/api/reviews",
        data={"channel": "linkedin"},
        files={"file": (name, data, "application/octet-stream")},
        headers=headers,
    )
    detail = response.json().get("detail")
    return response.status_code, detail if isinstance(detail, str) else str(detail)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "Paste some text"),
        ("   \n\t  ", "Paste some text"),
        ("PayWise " * 3000, "the limit is 20,000"),
    ],
    ids=["empty", "whitespace", "over-20k"],
)
def test_bad_text_gets_a_clear_message(
    api: TestClient, riya: Headers, content: str, message: str
) -> None:
    response = api.post(
        "/api/reviews", data={"channel": "linkedin", "content": content}, headers=riya
    )
    assert response.status_code == 422
    assert message in response.json()["detail"]


@pytest.mark.parametrize(
    ("name", "data", "message"),
    [
        ("empty.pdf", b"", "could not be opened"),
        ("binary.pdf", bytes(range(256)) * 40, "could not be opened"),
        ("locked.pdf", _encrypted_pdf(), "password-protected"),
        ("broken.docx", b"PK\x03\x04 not really a word file", "could not be opened"),
        ("empty.txt", b"", "No readable text"),
        ("latin1.txt", "Café crème".encode("latin-1"), "UTF-8"),
        ("slides.pptx", b"anything", "Unsupported file type"),
        ("huge.txt", b"a" * (5 * 1024 * 1024 + 10), "5 MB"),
    ],
    ids=[
        "zero-byte",
        "binary-as-pdf",
        "password-pdf",
        "corrupt-docx",
        "empty-txt",
        "not-utf8",
        "unsupported",
        "oversized",
    ],
)
def test_bad_files_get_a_clear_message(
    api: TestClient, riya: Headers, name: str, data: bytes, message: str
) -> None:
    status, detail = _upload(api, riya, name, data)
    assert status == 422, detail
    assert message in detail


def test_emoji_and_hindi_text_are_reviewed_normally(api: TestClient, riya: Headers) -> None:
    content = "PayWise से भुगतान करें 🚀 Settlements in under 10 seconds! 🙌"
    created = api.post(
        "/api/reviews", data={"channel": "linkedin", "content": content}, headers=riya
    )
    assert created.status_code == 201, created.text
    review = api.get(f"/api/reviews/{created.json()['id']}", headers=riya).json()
    assert review["revision"]["review_status"] == "complete"
    assert "भुगतान" in review["revision"]["content"]


def test_unknown_channel_sample_and_review_are_explained(api: TestClient, riya: Headers) -> None:
    channel = api.post("/api/reviews", data={"channel": "tiktok", "content": "Hi"}, headers=riya)
    assert channel.status_code == 422 and "Unknown channel" in channel.json()["detail"]
    sample = api.post(
        "/api/reviews", data={"channel": "linkedin", "sample_id": "nope"}, headers=riya
    )
    assert sample.status_code == 404 and sample.json()["detail"] == "Unknown sample."
    assert api.get("/api/reviews/sub_missing", headers=riya).json()["detail"] == "Review not found."


def test_an_unexpected_error_is_a_friendly_json_500() -> None:
    app = create_app()
    router = APIRouter()

    @router.get("/api/test-crash")
    def crash() -> None:
        raise RuntimeError("boom with internal details")

    app.include_router(router)
    response = TestClient(app, raise_server_exceptions=False).get("/api/test-crash")
    assert response.status_code == 500
    body = response.json()
    assert "boom" not in response.text and "Traceback" not in response.text
    assert body["detail"].startswith("Something went wrong on our side")
    assert body["request_id"]
