"""Render a Review Receipt as a one-page PDF with reportlab."""

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.api.receipts import Receipt

NAVY = colors.HexColor("#1B2A4A")
TEAL = colors.HexColor("#0F8B7E")
RED = colors.HexColor("#C8463D")
PAPER = colors.HexColor("#F6F1E3")


def _fmt(value: object) -> str:
    return value.strftime("%d %b %Y %H:%M UTC") if hasattr(value, "strftime") else "—"


def render_receipt_pdf(receipt: Receipt) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Review Receipt · {receipt.title}",
        author="Preflight",
    )
    base = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=base["BodyText"], fontSize=9, leading=12, textColor=NAVY)
    small = ParagraphStyle("small", parent=body, fontSize=7.5, leading=10)
    label = ParagraphStyle("label", parent=body, fontSize=7, textColor=colors.HexColor("#4A5A7C"))
    title = ParagraphStyle("title", parent=base["Title"], fontSize=17, alignment=0, textColor=NAVY)

    def p(text: str, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(text, style)

    status = "Audit chain verified" if receipt.audit_intact else "AUDIT CHAIN BROKEN"
    status_color = "#0F8B7E" if receipt.audit_intact else "#C8463D"
    story: list[object] = [
        p('<font color="#0F8B7E"><b>PREFLIGHT · REVIEW RECEIPT</b></font>', label),
        p(escape(receipt.title), title),
        p(
            f"Receipt {receipt.id} · channel {escape(receipt.channel)} · "
            f'<font color="{status_color}"><b>{status}</b></font>',
            small,
        ),
        Spacer(1, 6),
    ]
    facts = Table(
        [
            [
                p("AUTHOR", label),
                p("APPROVED BY", label),
                p("APPROVED", label),
                p("BRAND SCORE", label),
            ],
            [
                p(escape(receipt.author.name)),
                p(escape(receipt.approver.name if receipt.approver else "—")),
                p(_fmt(receipt.approved_at)),
                p(f"{receipt.first_score} → <b>{receipt.final_score}</b>"),
            ],
        ],
        colWidths=[44 * mm] * 4,
    )
    facts.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PAPER),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#ECE4CF")),
            ]
        )
    )
    story += [facts, Spacer(1, 8)]

    if receipt.overrides:
        rows = [
            [
                p(
                    f"<b>{escape(o.rule or '')}</b> · {escape(o.actor.name)}: {escape(o.reason)}",
                    small,
                )
            ]
            for o in receipt.overrides
        ]
        table = Table(
            [[p("<b>CRITICAL FINDINGS OVERRIDDEN BY THE APPROVER</b>", small)], *rows],
            colWidths=[176 * mm],
        )
        table.setStyle(
            TableStyle([("BOX", (0, 0), (-1, -1), 1.2, RED), ("TEXTCOLOR", (0, 0), (-1, 0), RED)])
        )
        story += [table, Spacer(1, 8)]

    story += [
        p(f"APPROVED TEXT (REVISION {receipt.revisions})", label),
        p(escape(receipt.final_text).replace("\n", "<br/>")),
        Spacer(1, 8),
    ]

    checks = ", ".join(f"{c['label']} ({c['findings']})" for c in receipt.checks)
    claims = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in receipt.claims.items()) or "none"
    first = " · ".join(
        f"{receipt.findings_first.get(s, 0)} {s}" for s in ("critical", "major", "minor")
    )
    story += [
        p("CHECKS RUN", label),
        p(escape(checks), small),
        Spacer(1, 4),
        p("CLAIM LEDGER (FINAL)", label),
        p(escape(claims), small),
        Spacer(1, 4),
        p("FINDINGS IN FIRST DRAFT", label),
        p(first, small),
        Spacer(1, 6),
    ]
    if receipt.findings_final:
        story.append(p("FINDINGS REMAINING AT APPROVAL", label))
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
    for d in receipt.timeline:
        reason = f" · “{escape(d.reason)}”" if d.reason else ""
        rule = f" {escape(d.rule)}" if d.rule else ""
        story.append(
            p(
                f"{_fmt(d.created_at)} · <b>{escape(d.actor.name)}</b> "
                f"{escape(d.kind.replace('_', ' '))}{rule}{reason}",
                small,
            )
        )

    ai = receipt.ai
    purposes = ", ".join(str(x).replace("_", " ") for x in ai.get("purposes", []))
    hosted = (
        f"{purposes} via {ai.get('provider')}/{ai.get('model')}. "
        if purposes
        else ("No hosted LLM (deterministic mode). ")
    )
    story += [
        Spacer(1, 8),
        p("AI USED IN THIS REVIEW", label),
        p(
            escape(
                f"{hosted}Verification by local NLI model {ai.get('nli_model') or '(fallback)'}. "
                f"Confidential values masked before external calls: {ai.get('masked_count', 0)}. "
                "The AI suggested; people decided."
            ),
            small,
        ),
        Spacer(1, 6),
        p(escape(f"{receipt.audit_message} Receipt hash {receipt.receipt_hash}"), small),
        p("Demo data is fictional. PayWise is not a real company.", small),
    ]
    doc.build(story)
    return buffer.getvalue()
