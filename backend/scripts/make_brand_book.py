"""Write the fictional "PayWise Brand Book" PDF the Rulebook Compiler is demonstrated on.

    python scripts/make_brand_book.py

Output: data/samples/paywise_brand_book.pdf (20 pages). Page numbers match the citations in
data/seed/rules.csv (for example CLM-04 cites p14), so the compiler's page references can be
checked against the existing rulebook. It also contains a few rules the seeded rulebook does
not have yet (new banned words, new claim patterns, a new disclaimer, a new product name), so a
brand manager has something real to accept.
"""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle

OUT = Path(__file__).resolve().parents[2] / "data" / "samples" / "paywise_brand_book.pdf"
NAVY = colors.HexColor("#13294B")

H1 = ParagraphStyle(
    "h1", fontName="Times-Bold", fontSize=22, leading=27, textColor=NAVY, spaceAfter=10
)
BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=10.5, leading=15, spaceAfter=7)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=9, leading=12)


def table(rows: list[list[str]], widths: list[float]) -> Table:
    t = Table(
        [[Paragraph(escape(c), SMALL) for c in row] for row in rows],
        colWidths=[w * mm for w in widths],
    )
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#9AA3AE")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EDF3")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return t


def page(title: str, *items: object) -> list[object]:
    out: list[object] = [Paragraph(escape(title), H1)]
    for item in items:
        out.append(Paragraph(escape(item), BODY) if isinstance(item, str) else item)
    out.append(PageBreak())
    return out


PAGES: list[list[object]] = [
    page(
        "PayWise Brand Book",
        "Edition 2026. How PayWise writes, what it may claim, and how it looks.",
        "PayWise is a fictional payments company created for the Preflight demo. Nothing in this "
        "book describes a real business.",
    ),
    page(
        "Contents",
        "Voice (4) · Punctuation and capitals (5) · Readability (6) · Channels (7) · Product "
        "names (8) · Words we avoid (9) · Claims (11 to 16) · Colour (17) · Logo (18) · "
        "Accessibility (19) · Disclaimers (20)",
    ),
    page(
        "Who we are",
        "PayWise helps small businesses in India get paid. We write for shop owners who are busy, "
        "practical and wary of hype.",
    ),
    page(
        "Voice",
        "Our voice is clear, warm and trustworthy: confident without hype. We sound like a "
        "helpful expert, never like an advertisement.",
        table(
            [
                ["Trait", "Target (0 to 1)", "What it means"],
                ["Formal", "0.6", "Professional, complete sentences, no slang."],
                ["Warm", "0.75", "Talk to the reader as 'you'; acknowledge their day."],
                ["Confident", "0.7", "State what we do plainly; no hedging, no boasting."],
                ["Playful", "0.3", "A light touch at most; never jokes about money."],
                ["Technical", "0.5", "Explain terms like UPI or MDR when they matter."],
            ],
            [30, 30, 110],
        ),
        "A draft that moves more than 0.3 away from any target should be revised.",
    ),
    page(
        "Punctuation and capitals",
        "Use at most one exclamation mark per 100 words.",
        "Do not write words in capitals longer than 4 letters. Acronyms such as UPI are fine.",
    ),
    page(
        "Readability",
        "Consumer copy must have a Flesch Reading Ease score of 50 or higher.",
        "Keep sentences to 30 words or fewer.",
    ),
    page(
        "Channels",
        table(
            [
                ["Channel", "Maximum characters", "Maximum hashtags", "Subject line"],
                ["LinkedIn", "3000", "5", "-"],
                ["X", "280", "2", "-"],
                ["Email", "-", "-", "60 characters"],
            ],
            [40, 45, 45, 40],
        ),
    ),
    page(
        "Product names",
        "Product names are written exactly as below. Never abbreviate or change capitals.",
        table(
            [
                ["Name", "Never write", "Note"],
                ["PayWise", "Paywise, Pay Wise, PAYWISE, Pay-Wise", "Company and app name."],
                ["PayWise Business", "Paywise Business, PayWise business", "Merchant product."],
                ["PayWise Card", "PayWise card, Paywise Card", "Card product."],
                ["PayWise Pay Later", "PayWise PayLater, PayWise BNPL", "Buy now, pay later."],
                [
                    "PayWise Rewards",
                    "Paywise Rewards, PayWise rewards",
                    "Loyalty programme (new in 2026).",
                ],
            ],
            [42, 78, 50],
        ),
    ),
    page(
        "Words we avoid",
        "Some words are banned outright; others are discouraged and have a better choice.",
        table(
            [
                ["Word", "Status", "Use instead"],
                ["cheap", "banned", "affordable"],
                ["no risk", "banned", "-"],
                ["instant loan", "banned", "quick credit decision"],
                ["revolutionary", "banned", "new"],
                ["hassle-free", "discouraged", "simple"],
                ["world-class", "discouraged", "reliable"],
                ["cutting-edge", "discouraged", "modern"],
                ["seamless", "discouraged", "smooth"],
            ],
            [55, 40, 75],
        ),
    ),
    page(
        "Words we avoid, continued",
        "When in doubt, describe what the product does instead of how impressive it is.",
    ),
    page(
        "Claims",
        "Every factual claim must match an entry in the approved facts registry. The next pages "
        "set out the claim rules.",
    ),
    page(
        "Facts and numbers",
        "Factual claims need an approved fact. A claim that contradicts an approved fact must be "
        "corrected before publication. Use the current version of a fact; a superseded fact is "
        "outdated.",
    ),
    page(
        "Superlatives",
        'Superlatives such as "#1", "best", "leading" or "industry-leading" need an approved fact '
        'that backs them. Otherwise use "trusted".',
    ),
    page(
        "Security",
        'Never make absolute security or safety claims such as "100% secure", "unhackable" or '
        '"completely safe". Describe the specific protection instead.',
    ),
    page(
        "Promises",
        'Do not promise outcomes: no "guaranteed returns", "never worry again" or "risk-free". '
        "Describe what the product does.",
    ),
    page(
        "Free",
        'Any use of "free" must be backed by an approved fact or carry the offer disclaimer '
        '"T&C apply."',
    ),
    page(
        "Colour",
        "Use the brand palette. Colours covering more than 8% of a visual must be within ΔE00 10 "
        "of a brand colour.",
        table(
            [
                ["Name", "Hex"],
                ["PayWise Navy", "#13294B"],
                ["PayWise Teal", "#12A594"],
                ["Sky", "#4FB3E8"],
                ["Sunrise", "#F5A623"],
                ["Charcoal", "#2E3440"],
                ["Cloud", "#F4F7FA"],
                ["White", "#FFFFFF"],
            ],
            [60, 40],
        ),
    ),
    page(
        "Logo",
        "Never stretch or squash the logo: keep its proportions within 5%.",
        "Keep clear space of at least a quarter of the logo's height on every side.",
    ),
    page(
        "Accessibility",
        "Text in visuals needs a contrast ratio of at least 4.5:1, or 3:1 for large text "
        "(WCAG 2.2 AA). Every image needs alt text that describes what it shows.",
    ),
    page(
        "Disclaimers",
        'Promotions (a special or limited offer, cashback, or anything "free") must include '
        '"T&C apply."',
        'Any mention of PayWise Pay Later must include "Subject to eligibility."',
        'Any mention of "interest-free" must include "Interest-free period applies to eligible '
        'purchases only."',
    ),
]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)

    def footer(canvas: object, doc: object) -> None:
        c = canvas  # type: ignore[assignment]
        c.saveState()  # type: ignore[attr-defined]
        c.setFont("Helvetica", 8)  # type: ignore[attr-defined]
        c.setFillColor(colors.HexColor("#5B6573"))  # type: ignore[attr-defined]
        c.drawString(20 * mm, 12 * mm, f"PayWise Brand Book 2026 (fictional) · page {doc.page}")  # type: ignore[attr-defined]
        c.restoreState()  # type: ignore[attr-defined]

    story: list[object] = []
    for items in PAGES:
        story += items
    story.pop()  # no blank page at the end
    SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=22 * mm,
        bottomMargin=22 * mm,
        title="PayWise Brand Book 2026",
        author="PayWise (fictional)",
    ).build(story, onFirstPage=footer, onLaterPages=footer)  # type: ignore[arg-type]
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
