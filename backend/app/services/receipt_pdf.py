"""Render a Clearance Certificate as an A4 PDF in the Proof Desk style.

The head is a boarding pass with a tear-off stub (QR code to the web certificate, hash,
audit status); the record follows below a perforation. The clearance stamp is drawn on
the canvas, rotated like a rubber stamp.
"""

import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.api.receipts import Receipt

INK = colors.HexColor("#1B2A4A")
GRAPHITE = colors.HexColor("#5B6573")
RULE = colors.HexColor("#E3DED2")
SHEET = colors.HexColor("#FFFDF8")
CLEARED = colors.HexColor("#1E8E5A")
AMBER = colors.HexColor("#D98E1F")
SIGNAL = colors.HexColor("#C8463D")

WIDTH = A4[0] - 32 * mm
STUB = 46 * mm


def _fmt(value: object) -> str:
    return value.strftime("%d %b %Y %H:%M UTC") if isinstance(value, datetime) else "—"


def _qr(url: str, size: float) -> Drawing:
    widget = QrCodeWidget(url, barLevel="M", barFillColor=INK, barStrokeColor=INK)
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
    drawing.add(widget)
    return drawing


def _stamp(
    canvas: Canvas, x: float, y: float, colour: colors.Color, title: str, lines: list[str]
) -> None:
    """A double-ruled rubber stamp, rotated -8 degrees, centred on (x, y)."""
    canvas.saveState()
    canvas.translate(x, y)
    canvas.rotate(8)  # reportlab rotates anticlockwise; the web stamp leans the same way
    width = max(canvas.stringWidth(title, "Courier-Bold", 11) + 10 * mm, 60 * mm)
    height = (9 + 4 * len(lines)) * mm
    canvas.setStrokeColor(colour)
    canvas.setFillColor(colour)
    canvas.setLineWidth(1.2)
    canvas.rect(-width / 2, -height / 2, width, height, fill=0)
    canvas.setLineWidth(0.5)
    canvas.rect(-width / 2 + 1.4, -height / 2 + 1.4, width - 2.8, height - 2.8, fill=0)
    canvas.setFont("Courier-Bold", 11)
    canvas.drawCentredString(0, height / 2 - 6.5 * mm, title)
    canvas.setFont("Courier", 7)
    for i, line in enumerate(lines):
        canvas.drawCentredString(0, height / 2 - (11 + 4 * i) * mm, line)
    canvas.restoreState()


class _Stamps(Flowable):  # type: ignore[misc]
    """A band below the boarding pass that carries the rubber stamps."""

    HEIGHT = 26 * mm

    def __init__(self, stamps: list[tuple[colors.Color, str, list[str]]]) -> None:
        super().__init__()
        self.stamps = stamps

    def wrap(self, _width: float, _height: float) -> tuple[float, float]:
        return WIDTH, self.HEIGHT

    def draw(self) -> None:
        for i, (colour, title, lines) in enumerate(self.stamps):
            _stamp(self.canv, WIDTH - 42 * mm - i * 78 * mm, self.HEIGHT / 2, colour, title, lines)


def render_receipt_pdf(receipt: Receipt, certificate_url: str | None = None) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Clearance Certificate · {receipt.title}",
        author="Preflight",
    )
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=12.5, textColor=INK)
    small = ParagraphStyle("small", parent=body, fontSize=7.5, leading=10.5)
    muted = ParagraphStyle("muted", parent=small, textColor=GRAPHITE)
    label = ParagraphStyle(
        "label", parent=body, fontName="Courier", fontSize=7, leading=9, textColor=GRAPHITE
    )
    mono = ParagraphStyle("mono", parent=body, fontName="Courier", fontSize=8.5, leading=11)
    big = ParagraphStyle("big", parent=body, fontName="Courier", fontSize=17, leading=20)
    title = ParagraphStyle("title", parent=body, fontName="Times-Roman", fontSize=21, leading=25)
    serif = ParagraphStyle("serif", parent=body, fontName="Times-Roman", fontSize=11, leading=15.5)

    def p(text: str, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(text, style)

    def pad(n: int | None) -> str:
        return "--" if n is None else f"{n:02d}"

    destination = "PUBLISHED" if receipt.state == "published" else "CLEARED"
    route = Table(
        [
            [p("FROM", label), "", p("TO", label)],
            [
                p("DRAFT", big),
                p(f"- - - {receipt.revisions} revision(s) - - -", label),
                p(f'<font color="#1E8E5A">{destination}</font>', big),
            ],
            [
                p(f"score {pad(receipt.first_score)}", label),
                "",
                p(f"score {pad(receipt.final_score)}", label),
            ],
        ],
        colWidths=[36 * mm, None, 40 * mm],
    )
    route.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 0.5, RULE),
                ("LINEBELOW", (0, -1), (-1, -1), 0.5, RULE),
                ("ALIGN", (1, 1), (1, 1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    fields = Table(
        [
            [p("CHANNEL", label), p("AUTHOR", label), p("APPROVER", label), p("CLEARED", label)],
            [
                p(escape(receipt.channel)),
                p(escape(receipt.author.name)),
                p(escape(receipt.approver.name if receipt.approver else "—")),
                p(_fmt(receipt.approved_at), small),
            ],
        ],
    )
    fields.setStyle(
        TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "TOP")])
    )
    pass_cell = [
        p("PREFLIGHT · CLEARANCE CERTIFICATE", label),
        Spacer(1, 4),
        p(escape(receipt.title), title),
        Spacer(1, 6),
        route,
        Spacer(1, 6),
        fields,
    ]

    status = "Audit chain verified" if receipt.audit_intact else "AUDIT CHAIN BROKEN"
    status_colour = "#1E8E5A" if receipt.audit_intact else "#C8463D"
    stub_cell: list[object] = []
    if certificate_url:
        stub_cell += [_qr(certificate_url, 30 * mm), Spacer(1, 4)]
    stub_cell += [
        p("CERTIFICATE", label),
        p(escape(receipt.id), mono),
        Spacer(1, 3),
        p("HASH", label),
        p(f"{(receipt.receipt_hash or '—')[:8]}…", mono),
        Spacer(1, 3),
        p(f'<font color="{status_colour}"><b>{status}</b></font>', small),
        p(f"{receipt.audit_events} events", muted),
    ]

    head = Table([[pass_cell, stub_cell]], colWidths=[WIDTH - STUB, STUB])
    head.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SHEET),
                ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                ("LINEBEFORE", (1, 0), (1, 0), 1, RULE, None, (3, 3)),
                ("LINEBELOW", (0, 0), (-1, 0), 1, RULE, None, (3, 3)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8 * mm),
                ("RIGHTPADDING", (0, 0), (0, 0), 8 * mm),
                ("LEFTPADDING", (1, 0), (1, 0), 6 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 7 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7 * mm),
            ]
        )
    )
    stamps: list[tuple[colors.Color, str, list[str]]] = []
    if receipt.approver and receipt.approved_at:
        when = receipt.approved_at.strftime("%d %b %Y %H:%M UTC").upper()
        stamps.append(
            (
                CLEARED,
                "CLEARED FOR PUBLICATION",
                [
                    f"BY {receipt.approver.name.upper()} · {when}",
                    f"HASH {(receipt.receipt_hash or '')[:8]}",
                ],
            )
        )
    if receipt.overrides:
        count = len(receipt.overrides)
        stamps.append((AMBER, "OVERRIDE NOTED", [f"{count} CRITICAL FINDING(S)"]))
    story: list[object] = [head, _Stamps(stamps) if stamps else Spacer(1, 9 * mm)]

    if receipt.overrides:
        story.append(p('<font color="#D98E1F"><b>OVERRIDE NOTED</b></font>', label))
        for o in receipt.overrides:
            story.append(
                p(
                    f"<b>{escape(o.rule or '')}</b> · {escape(o.actor.name)}: “{escape(o.reason)}”",
                    small,
                )
            )
        story.append(Spacer(1, 6))

    text = Table([[p(escape(receipt.final_text).replace("\n", "<br/>"), serif)]], colWidths=[WIDTH])
    text.setStyle(
        TableStyle(
            [("LINEBEFORE", (0, 0), (0, -1), 1.5, INK), ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm)]
        )
    )
    story += [
        p(f"CLEARED TEXT · REVISION {receipt.revisions}", label),
        Spacer(1, 2),
        text,
        Spacer(1, 7),
    ]

    def ruled(rows: list[list[str]], widths: list[float]) -> Table:
        table = Table([[p(cell, small) for cell in row] for row in rows], colWidths=widths)
        table.setStyle(
            TableStyle(
                [
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
                    ("LINEABOVE", (0, 0), (-1, 0), 0.4, RULE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        return table

    half = (WIDTH - 8 * mm) / 2
    checks = ruled(
        [
            [escape(c["label"]) + ("" if c["ok"] else " (fallback)"), f"{c['findings']} found"]
            for c in receipt.checks
        ],
        [half - 20 * mm, 20 * mm],
    )
    claims_rows = [
        [escape(k.replace("_", " ").capitalize()), str(v)] for k, v in receipt.claims.items()
    ]
    claims = ruled(claims_rows or [["No factual claims", ""]], [half - 20 * mm, 20 * mm])
    first = " · ".join(
        f"{receipt.findings_first.get(s, 0)} {s}" for s in ("critical", "major", "minor")
    )
    columns = Table(
        [
            [p("CHECKS RUN", label), "", p("CLAIM LEDGER · FINAL REVISION", label)],
            [
                checks,
                "",
                [claims, Spacer(1, 4), p("FINDINGS IN THE FIRST DRAFT", label), p(first, mono)],
            ],
        ],
        colWidths=[half, 8 * mm, half],
    )
    columns.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)])
    )
    story += [columns, Spacer(1, 7)]

    if receipt.findings_final:
        story.append(p("FINDINGS REMAINING AT CLEARANCE", label))
        for f in receipt.findings_final:
            story.append(
                p(
                    f"<b>{f.severity.upper()}</b> {escape(f.rule_id)} “{escape(f.text)}” · "
                    f"{'needs a human look (not scored)' if f.needs_review else escape(f.status)}",
                    small,
                )
            )
        story.append(Spacer(1, 6))

    story.append(p("DECISIONS", label))
    story.append(
        ruled(
            [
                [
                    _fmt(d.created_at),
                    f"<b>{escape(d.actor.name)}</b> {escape(d.kind.replace('_', ' '))}"
                    + (f" {escape(d.rule)}" if d.rule else "")
                    + (f" · “{escape(d.reason)}”" if d.reason else ""),
                ]
                for d in receipt.timeline
            ]
            or [["—", "No decisions recorded"]],
            [38 * mm, WIDTH - 38 * mm],
        )
    )

    ai = receipt.ai
    purposes = ", ".join(str(x).replace("_", " ") for x in ai.get("purposes", []))
    hosted = (
        f"{purposes} via {ai.get('provider')}/{ai.get('model')}. "
        if purposes
        else "No hosted LLM (deterministic mode). "
    )
    story += [
        Spacer(1, 7),
        p("AI USED IN THIS REVIEW", label),
        p(
            escape(
                f"{hosted}Verification by local NLI model {ai.get('nli_model') or '(fallback)'}. "
                f"Confidential values masked before external calls: {ai.get('masked_count', 0)}. "
                "The AI suggested; people decided."
            ),
            muted,
        ),
        Spacer(1, 4),
        p(escape(f"{receipt.audit_message} Certificate hash {receipt.receipt_hash}"), label),
        p("Demo data is fictional. PayWise is not a real company.", label),
    ]

    doc.build(story)
    return buffer.getvalue()
