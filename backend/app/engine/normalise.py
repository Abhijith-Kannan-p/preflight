"""Turn pasted text, Markdown, DOCX or PDF into a NormalisedDoc of text blocks with offsets."""

import io
import re

from app.engine.schema import Block, NormalisedDoc

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_CHARS = 20_000

SUPPORTED_EXTENSIONS = {".txt": "text", ".md": "markdown", ".docx": "docx", ".pdf": "pdf"}


class IntakeError(ValueError):
    """Raised with a user-facing message when content cannot be read."""


def _blocks_from_paragraphs(paragraphs: list[str], source_format: str) -> NormalisedDoc:
    cleaned = [p.strip() for p in paragraphs if p and p.strip()]
    if not cleaned:
        raise IntakeError("No readable text was found. Paste text or upload a text-based file.")
    total = sum(len(p) for p in cleaned) + 2 * (len(cleaned) - 1)
    if total > MAX_CHARS:
        raise IntakeError(f"Content is {total:,} characters; the limit is {MAX_CHARS:,}.")
    blocks: list[Block] = []
    offset = 0
    for i, paragraph in enumerate(cleaned):
        blocks.append(Block(id=i, text=paragraph, start_offset=offset))
        offset += len(paragraph) + 2
    return NormalisedDoc(blocks=blocks, source_format=source_format)


def _split_paragraphs(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.split(r"\n\s*\n", text)


_MD_RULES = [
    (re.compile(r"^\s{0,3}#{1,6}\s+", re.M), ""),
    (re.compile(r"^\s*[-*+]\s+", re.M), ""),
    (re.compile(r"!\[([^\]]*)\]\([^)]*\)"), r"\1"),
    (re.compile(r"\[([^\]]+)\]\([^)]*\)"), r"\1"),
    (re.compile(r"(\*\*|__)(.+?)\1"), r"\2"),
    (re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])"), r"\1"),
    (re.compile(r"`([^`]+)`"), r"\1"),
]


def strip_markdown(text: str) -> str:
    for pattern, replacement in _MD_RULES:
        text = pattern.sub(replacement, text)
    return text


def from_text(text: str, markdown: bool = False) -> NormalisedDoc:
    if markdown:
        text = strip_markdown(text)
    return _blocks_from_paragraphs(_split_paragraphs(text), "markdown" if markdown else "text")


def from_docx(data: bytes) -> NormalisedDoc:
    from docx import Document

    try:
        document = Document(io.BytesIO(data))
    except Exception as exc:
        raise IntakeError("This DOCX file could not be opened. Is it a valid Word file?") from exc
    paragraphs = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            paragraphs.append(" | ".join(cell.text.strip() for cell in row.cells))
    return _blocks_from_paragraphs(paragraphs, "docx")


def from_pdf(data: bytes) -> NormalisedDoc:
    import fitz

    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise IntakeError("This PDF could not be opened. Is it a valid PDF file?") from exc
    paragraphs: list[str] = []
    with document:
        if document.needs_pass:
            raise IntakeError("This PDF is password-protected.")
        for page in document:
            for block in page.get_text("blocks", sort=True):
                if block[6] == 0:  # text block, not image
                    paragraphs.append(" ".join(block[4].split()))
    if not any(p.strip() for p in paragraphs):
        raise IntakeError(
            "This PDF has no text layer (it may be scanned). Image and OCR review is planned "
            "for Round 3."
        )
    return _blocks_from_paragraphs(paragraphs, "pdf")


def from_upload(filename: str, data: bytes) -> NormalisedDoc:
    if len(data) > MAX_FILE_BYTES:
        raise IntakeError("Files must be 5 MB or smaller.")
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    kind = SUPPORTED_EXTENSIONS.get(extension)
    if kind is None:
        raise IntakeError("Unsupported file type. Upload DOCX, PDF, TXT or MD.")
    if kind == "docx":
        return from_docx(data)
    if kind == "pdf":
        return from_pdf(data)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IntakeError("Text files must be UTF-8 encoded.") from exc
    return from_text(text, markdown=kind == "markdown")
