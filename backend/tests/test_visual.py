"""Visual and accessibility review: intake, OCR clean-up and grouping, the four visual checks,
alt text, and a visual review end to end through the API."""

import asyncio
import io
import threading
from collections.abc import Iterator
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.config import get_settings
from app.engine.checkers.accessibility import AccessibilityChecker, alt_problem
from app.engine.context import ReviewContext, load_context
from app.engine.normalise import from_upload
from app.engine.schema import ImageRef, NormalisedDoc
from app.seed import WORKSPACE_ID
from app.services import runner
from app.visual.analyse import analyse
from app.visual.intake import VisualUpload
from app.visual.logo import find_logo
from app.visual.ocr import OcrLine, respace, to_blocks

FILES = get_settings().seed_dir / "files"
Headers = dict[str, str]


async def _ignore(_event: str, _data: dict[str, object]) -> None:
    return None


@pytest.fixture
def ctx(session: Session) -> ReviewContext:
    return load_context(session, WORKSPACE_ID, "linkedin")


def _visual(name: str) -> VisualUpload:
    upload = from_upload(name, (FILES / name).read_bytes())
    assert isinstance(upload, VisualUpload)
    return upload


def _review(name: str, ctx: ReviewContext) -> tuple[set[str], str]:
    upload = _visual(name)
    result = asyncio.run(
        analyse(upload.pages, ctx, upload.source_format, [], _ignore, upload.scales)
    )
    return {f.rule.id for f in result.findings}, result.doc.text


# --- OCR clean-up and layout --------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("Your money is 1oo% secure", "Your money is 100% secure"),
        ("Your money is 1o 0% secure", "Your money is 100% secure"),
        ("Save 15% now", "Save 15% now"),
        ("valid till31 December", "valid till 31 December"),
        ("in under 5seconds", "in under 5 seconds"),
        ("Questions?Visit us", "Questions? Visit us"),
        ("Get 10x faster", "Get 10x faster"),
    ],
)
def test_ocr_text_clean_up(raw: str, clean: str) -> None:
    assert respace(raw) == clean


def test_lines_group_into_paragraphs_with_boxes() -> None:
    lines = [
        OcrLine("India's #1 payments app", 80, 100, 700, 154, 0.99),
        OcrLine("100% secure payments", 80, 170, 600, 206, 0.99),
        OcrLine("this festive season", 80, 210, 560, 246, 0.99),
    ]
    blocks, layout = to_blocks([(lines, 1200, 630)])
    assert [b.text for b in blocks] == [
        "India's #1 payments app",
        "100% secure payments this festive season",
    ]
    second = [box for box in layout if box.block == 1]
    assert [(b.start, b.end) for b in second] == [(0, 20), (21, 40)]
    assert second[0].x == pytest.approx(80 / 1200)


# --- the four visual checks on the samples ------------------------------------------------


def test_festive_banner_shows_every_planted_issue(ctx: ReviewContext) -> None:
    rules, text = _review("paywise_festive_banner.png", ctx)
    assert {"VIS-01", "ACC-01"} <= rules
    assert "India's #1" in text and "100% secure" in text


def test_stretched_logo_and_crowded_clear_space(ctx: ReviewContext) -> None:
    rules, _ = _review("paywise_stretched_logo_post.png", ctx)
    assert {"VIS-02", "VIS-03"} <= rules


def test_clean_visual_has_no_visual_findings(ctx: ReviewContext) -> None:
    rules, text = _review("paywise_clean_visual.png", ctx)
    assert rules == set()
    assert "under 10 seconds" in text


def test_scanned_pdf_is_rasterised_and_read(ctx: ReviewContext) -> None:
    upload = _visual("paywise_scanned_flyer.pdf")
    assert upload.source_format == "scan" and len(upload.pages) == 1
    rules, text = _review("paywise_scanned_flyer.pdf", ctx)
    assert "under 5 seconds" in text
    assert rules == set(), "a clean scan: speckle is not a clear-space intrusion"


def test_logo_detection_measures_distortion() -> None:
    clean = find_logo(Image.open(FILES / "paywise_clean_visual.png"))
    stretched = find_logo(Image.open(FILES / "paywise_stretched_logo_post.png"))
    assert clean is not None and clean.distortion < 0.02
    assert stretched is not None and stretched.aspect == pytest.approx(1.4, abs=0.05)
    assert find_logo(Image.new("RGB", (800, 400), "#F4F7FA")) is None


# --- alt text, HTML email and intake -------------------------------------------------------


@pytest.mark.parametrize(
    ("alt", "problem"),
    [
        ("", "is empty"),
        ("image of team_photo_final.jpg", "file name"),
        ("Image of our team at the Bengaluru office", "image of"),
        ("banner", "too short"),
        ("PayWise banner: settle payments in under 10 seconds", None),
    ],
)
def test_alt_text_lint(alt: str, problem: str | None) -> None:
    found = alt_problem(alt)
    assert (found is None) if problem is None else (found is not None and problem in found)


def test_html_email_images_alt_text_and_colours(ctx: ReviewContext) -> None:
    doc = from_upload("email.html", (FILES / "paywise_email_with_images.html").read_bytes())
    assert isinstance(doc, NormalisedDoc) and doc.source_format == "html"
    assert [i.alt for i in doc.images] == [
        "PayWise logo",
        None,
        "image of team_photo_final.jpg",
    ]
    assert "#E0115F" in doc.colours
    findings = asyncio.run(AccessibilityChecker().run(doc, ctx))
    assert sorted(f.rule.id for f in findings) == ["ACC-02", "ACC-03", "VIS-01"]


def test_uploaded_image_without_alt_text_is_flagged(ctx: ReviewContext) -> None:
    doc = NormalisedDoc(
        blocks=[], source_format="image", images=[ImageRef(name="x.png", alt="", source="upload")]
    )
    findings = asyncio.run(AccessibilityChecker().run(doc, ctx))
    assert [f.rule.id for f in findings] == ["ACC-03"]


@pytest.mark.parametrize(
    ("name", "data", "message"),
    [
        ("empty.png", b"", "empty"),
        ("fake.png", b"not an image at all" * 20, "could not be opened"),
        ("note.gif", b"GIF89a", "Unsupported file type"),
    ],
    ids=["empty", "corrupt", "unsupported"],
)
def test_bad_images_get_clear_messages(name: str, data: bytes, message: str) -> None:
    from app.engine.normalise import IntakeError

    with pytest.raises(IntakeError, match=message):
        from_upload(name, data)


def test_pdf_with_a_text_layer_is_not_treated_as_a_scan() -> None:
    doc = fitz.open()
    doc.new_page().insert_text(
        (72, 72), "PayWise settles merchant payments in under 10 seconds. " * 3
    )
    buffer = io.BytesIO()
    doc.save(buffer)
    assert isinstance(from_upload("text.pdf", buffer.getvalue()), NormalisedDoc)


# --- end to end ---------------------------------------------------------------------------


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


def test_visual_review_through_the_api(api: TestClient) -> None:
    token = api.post("/api/auth/demo-login", json={"user_id": "usr_abhi1"}).json()["token"]
    riya = {"Authorization": f"Bearer {token}"}
    created = api.post(
        "/api/reviews",
        data={"channel": "linkedin", "sample_id": "sample_festive_banner"},
        headers=riya,
    )
    assert created.status_code == 201, created.text
    review = api.get(f"/api/reviews/{created.json()['id']}", headers=riya).json()
    revision = review["revision"]
    assert revision["review_status"] == "complete"
    assert revision["source_format"] == "image"
    rules = {f["rule"]["id"] for f in review["findings"]}
    # Visual checks, plus text checks on what OCR read and alt-text lint of the sample's alt.
    assert {"VIS-01", "ACC-01", "CLM-01", "CLM-04", "ACC-03"} <= rules
    visual = revision["report"]["visual"]
    page = visual["pages"][0]
    assert any(e["off_palette"] for e in page["palette"])
    image = api.get(f"/api/assets/{page['asset_id']}")
    assert image.status_code == 200 and image.headers["content-type"] == "image/webp"
    by_rule = {f["rule"]["id"]: f for f in review["findings"]}
    assert by_rule["VIS-01"]["region"] and by_rule["ACC-01"]["region"]
    assert by_rule["CLM-04"]["region"], "text found by OCR is located on the image too"

    # A corrected design comes in as a new version.
    fixed = (FILES / "paywise_clean_visual.png").read_bytes()
    second = api.post(
        f"/api/reviews/{created.json()['id']}/revisions/upload",
        files={"file": ("banner_v2.png", fixed, "image/png")},
        data={"alt_text": "PayWise banner: settle payments in under 10 seconds."},
        headers=riya,
    )
    assert second.status_code == 201, second.text
    latest = api.get(f"/api/reviews/{created.json()['id']}", headers=riya).json()
    assert latest["revision"]["number"] == 2
    assert not {"VIS-01", "ACC-01", "CLM-04"} & {f["rule"]["id"] for f in latest["findings"]}


def test_sample_files_exist_and_are_small() -> None:
    for name in (
        "paywise_festive_banner.png",
        "paywise_scanned_flyer.pdf",
        "paywise_email_with_images.html",
        "paywise_stretched_logo_post.png",
        "paywise_clean_visual.png",
    ):
        path: Path = FILES / name
        assert path.exists() and path.stat().st_size < 5 * 1024 * 1024
