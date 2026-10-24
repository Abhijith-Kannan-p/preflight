"""Generate the DOCX and PDF sample drafts in data/seed/files from data/seed/drafts.json.

Usage (from backend/): python -m scripts.build_samples
"""

import json
from pathlib import Path

from docx import Document
from docx.shared import Pt
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.config import get_settings


def build_docx(content: str, path: Path) -> None:
    document = Document()
    document.styles["Normal"].font.name = "Calibri"
    document.styles["Normal"].font.size = Pt(11)
    for paragraph in content.split("\n\n"):
        document.add_paragraph(paragraph)
    document.save(str(path))


def build_pdf(content: str, path: Path) -> None:
    styles = getSampleStyleSheet()
    paragraphs = content.split("\n\n")
    story = [Paragraph(paragraphs[0], styles["Title"]), Spacer(1, 12)]
    for paragraph in paragraphs[1:]:
        style = styles["Heading2"] if len(paragraph) < 30 else styles["BodyText"]
        story += [Paragraph(paragraph.replace("\n", "<br/>"), style), Spacer(1, 8)]
    SimpleDocTemplate(str(path), pagesize=A4, title="PayWise press release").build(story)


def main() -> None:
    seed_dir = get_settings().seed_dir
    out = seed_dir / "files"
    out.mkdir(exist_ok=True)
    for draft in json.loads((seed_dir / "drafts.json").read_text(encoding="utf-8")):
        if draft["format"] == "docx":
            build_docx(draft["content"], out / draft["filename"])
        elif draft["format"] == "pdf":
            build_pdf(draft["content"], out / draft["filename"])
        else:
            continue
        print("wrote", draft["filename"])


if __name__ == "__main__":
    main()
