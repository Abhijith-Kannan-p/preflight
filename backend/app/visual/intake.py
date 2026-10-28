"""Read visual uploads: PNG, JPG and WebP images, and PDFs that are scans (pages with little or
no text layer are rasterised with PyMuPDF at 150 dpi, at most five pages).

Pages are reduced to at most `MAX_SIDE` pixels for analysis and stored as WebP with the
revision, so the review page can draw them with their overlay boxes.
"""

import io
from dataclasses import dataclass
from typing import Any, Literal

from PIL import Image, UnidentifiedImageError

MAX_SIDE = 1400
MAX_PIXELS = 40_000_000
MAX_PDF_PAGES = 5
PDF_DPI = 150
# Fewer text-layer characters than this per page on average: treat the PDF as a scan.
SCAN_CHARS_PER_PAGE = 40

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class VisualIntakeError(ValueError):
    """User-facing message; the API returns it as a 422."""


@dataclass
class VisualUpload:
    pages: list[Image.Image]
    # Analysed size divided by original size, per page (1.0 when not reduced).
    scales: list[float]
    source_format: Literal["image", "scan"]
    name: str


def _reduce(image: Image.Image) -> tuple[Image.Image, float]:
    image = image.convert("RGBA")
    flat = Image.new("RGB", image.size, "#FFFFFF")
    flat.paste(image, mask=image.split()[3])
    scale = min(1.0, MAX_SIDE / max(flat.size))
    if scale < 1.0:
        flat = flat.resize(
            (round(flat.width * scale), round(flat.height * scale)), Image.Resampling.LANCZOS
        )
    return flat, scale


def load_image(name: str, data: bytes) -> VisualUpload:
    if not data:
        raise VisualIntakeError("This image file is empty.")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        image = Image.open(io.BytesIO(data))
        image.load()  # type: ignore[no-untyped-call]
    except Image.DecompressionBombError as exc:
        raise VisualIntakeError(
            "This image is too large to review (over 40 megapixels). Export a smaller version."
        ) from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise VisualIntakeError(
            "This image could not be opened. Upload a PNG, JPG or WebP file."
        ) from exc
    if image.format not in ("PNG", "JPEG", "WEBP", "MPO"):
        raise VisualIntakeError("Upload a PNG, JPG or WebP image.")
    page, scale = _reduce(image)
    return VisualUpload([page], [scale], "image", name)


def is_scanned(document: Any) -> bool:
    """True when the PDF's pages carry (almost) no text layer."""
    pages = list(document)
    if not pages:
        return False
    chars = sum(len(page.get_text("text").strip()) for page in pages)
    return chars / len(pages) < SCAN_CHARS_PER_PAGE


def rasterise_pdf(document: Any, name: str) -> VisualUpload:
    pages: list[Image.Image] = []
    scales: list[float] = []
    for index, page in enumerate(document):
        if index >= MAX_PDF_PAGES:
            break
        pixmap = page.get_pixmap(dpi=PDF_DPI)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        reduced, scale = _reduce(image)
        pages.append(reduced)
        scales.append(scale)
    if not pages:
        raise VisualIntakeError("This PDF has no pages.")
    return VisualUpload(pages, scales, "scan", name)


def encode_page(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=88, method=4)
    return buffer.getvalue()


def decode_page(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")
