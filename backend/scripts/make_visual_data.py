"""Draw the fictional PayWise visual assets, deterministically.

    python scripts/make_visual_data.py

Writes:
- data/brand/: the PayWise logo mark (PNG + SVG) and the logo lockup.
- data/seed/files/: the five one-click visual samples (festive banner, scanned flyer PDF,
  email with images, stretched-logo post, clean visual).
- data/eval/visual/: 100 labelled assets (96 generated from templates with known injected
  issues, plus four hand-composed samples) and labels.json.

Every issue in the labelled set is injected on purpose and recorded in its label, so the
evaluation measures the checks against ground truth rather than against themselves.
"""

import io
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
BRAND = ROOT / "data" / "brand"
FILES = ROOT / "data" / "seed" / "files"
EVAL = ROOT / "data" / "eval" / "visual"

NAVY, TEAL, SKY, SUNRISE = "#13294B", "#12A594", "#4FB3E8", "#F5A623"
CHARCOAL, CLOUD, WHITE = "#2E3440", "#F4F7FA", "#FFFFFF"
OFF_PALETTE = ["#E0115F", "#7B2CBF", "#8DB600", "#FF5F1F", "#00838F"]

# Text that the text checkers must catch once OCR has read it.
CLAIM_LINES = {
    "CLM-04": ["100% secure payments, every time", "Your money is 100% secure"],
    "CLM-01": ["India's #1 payments app", "The #1 way to get paid"],
    "TRM-02": ["Paywise makes payday simple", "Pay smarter with Paywise"],
}
CLEAN_LINES = [
    "Settle payments in under 10 seconds",
    "Bank-grade encryption on every payment",
    "Get paid faster with PayWise",
    "Simple invoices for growing shops",
    "Track every payment in one place",
    "Built for small businesses",
]


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)  # type: ignore[return-value]


# --- logo ------------------------------------------------------------------------------


def logo_mark(size: int) -> Image.Image:
    """The PayWise mark: a teal tile with a white P and a sunrise dot. Drawn 4x and reduced."""
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(0.22 * s), fill=TEAL)

    def box(*fractions: float) -> list[int]:
        return [int(f * s) for f in fractions]

    d.rounded_rectangle(box(0.28, 0.20, 0.72, 0.60), radius=int(0.18 * s), fill=WHITE)
    d.rounded_rectangle(box(0.40, 0.31, 0.60, 0.49), radius=int(0.08 * s), fill=TEAL)
    d.rectangle([int(0.28 * s), int(0.20 * s), int(0.40 * s), int(0.80 * s)], fill=WHITE)
    r = int(0.075 * s)
    cx, cy = int(0.72 * s), int(0.74 * s)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=SUNRISE)
    return img.resize((size, size), Image.Resampling.LANCZOS)


LOGO_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"
     role="img" aria-label="PayWise">
  <rect width="100" height="100" rx="22" fill="{TEAL}"/>
  <rect x="28" y="20" width="44" height="40" rx="18" fill="{WHITE}"/>
  <rect x="40" y="31" width="20" height="18" rx="8" fill="{TEAL}"/>
  <rect x="28" y="20" width="12" height="60" fill="{WHITE}"/>
  <circle cx="72" cy="74" r="7.5" fill="{SUNRISE}"/>
</svg>
"""


def logo_lockup(height: int, ink: str = NAVY) -> Image.Image:
    """Mark plus wordmark; the wordmark is white on dark backgrounds."""
    mark = logo_mark(height)
    words = font(int(height * 0.62))
    width = height + int(height * 0.25) + int(words.getlength("PayWise"))
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    img.alpha_composite(mark, (0, 0))
    ImageDraw.Draw(img).text(
        (height + int(height * 0.25), height // 2), "PayWise", font=words, fill=ink, anchor="lm"
    )
    return img


# --- composition -----------------------------------------------------------------------


@dataclass
class Line:
    text: str
    colour: str
    size: int
    bold: bool = False


@dataclass
class Spec:
    name: str
    width: int
    height: int
    background: str
    lines: list[Line]
    logo: tuple[int, int, int] | None = None  # x, y, height
    stretch: float = 1.0  # horizontal stretch of the logo (1.0 = correct)
    crowd_logo: bool = False  # put a bar inside the logo's clear space
    patch: tuple[str, float] | None = None  # colour, share of the image
    accent: str | None = None  # a small (under 4%) accent shape
    labels: dict[str, object] = field(default_factory=dict)


def compose(spec: Spec) -> Image.Image:
    img = Image.new("RGBA", (spec.width, spec.height), spec.background)
    d = ImageDraw.Draw(img)
    if spec.patch:
        colour, share = spec.patch
        side = int((share * spec.width * spec.height) ** 0.5)
        d.rectangle([spec.width - side, spec.height - side, spec.width, spec.height], fill=colour)
    if spec.accent:
        r = int(0.08 * min(spec.width, spec.height))
        d.ellipse([spec.width - 3 * r, r, spec.width - r, 3 * r], fill=spec.accent)
    x = int(spec.width * 0.07)
    y = int(spec.height * 0.38) if spec.logo else int(spec.height * 0.16)
    for line in spec.lines:
        f = font(line.size)
        d.text(
            (x, y),
            line.text,
            font=f,
            fill=line.colour,
            stroke_width=1 if line.bold else 0,
            stroke_fill=line.colour,
        )
        y += int(line.size * 1.55)
    if spec.logo:
        lx, ly, lh = spec.logo
        lockup = logo_lockup(lh, contrasting(spec.background))
        if spec.stretch != 1.0:
            lockup = lockup.resize((int(lockup.width * spec.stretch), lh), Image.Resampling.LANCZOS)
        img.alpha_composite(lockup, (lx, ly))
        if spec.crowd_logo:
            gap = int(lh * 0.08)
            d.rectangle(
                [lx, ly + lh + gap, lx + lockup.width, ly + lh + gap + int(lh * 0.3)],
                fill=SKY if spec.background != SKY else NAVY,
            )
    return img.convert("RGB")


def contrasting(background: str) -> str:
    return WHITE if background in (NAVY, CHARCOAL, TEAL) else NAVY


LOW_CONTRAST = {WHITE: "#C9D3DD", CLOUD: "#C2CCD6", NAVY: "#2B4470", SKY: "#7CC8F0"}


def generated_spec(index: int, rng: random.Random) -> Spec:
    size = rng.choice([(1200, 630), (1080, 1080), (1080, 1350)])
    background = rng.choice([WHITE, CLOUD, NAVY, SKY])
    ink = contrasting(background)
    labels: dict[str, object] = {}
    text_rules: list[str] = []
    lines: list[Line] = []
    headline = rng.choice(CLEAN_LINES)
    if rng.random() < 0.35:
        rule = rng.choice(sorted(CLAIM_LINES))
        headline = rng.choice(CLAIM_LINES[rule])
        text_rules.append(rule)
    lines.append(Line(headline, ink, int(size[0] * 0.045), bold=True))
    lines.append(Line(rng.choice(CLEAN_LINES), ink, int(size[0] * 0.03)))
    low = rng.random() < 0.3
    if low:
        lines.append(
            Line("Offer details at paywise.example", LOW_CONTRAST[background], int(size[0] * 0.026))
        )
    else:
        lines.append(Line("Learn more at paywise.example", ink, int(size[0] * 0.026)))
    labels["ACC-01"] = low

    has_logo = rng.random() < 0.75
    stretch = 1.0
    crowd = False
    logo = None
    if has_logo:
        lh = int(min(size) * rng.uniform(0.09, 0.13))
        logo = (int(size[0] * 0.07), int(size[1] * 0.10), lh)
        if rng.random() < 0.35:
            stretch = rng.choice([0.75, 0.8, 1.25, 1.35, 1.5])
        crowd = rng.random() < 0.3
    labels["logo"] = has_logo
    labels["VIS-02"] = has_logo and stretch != 1.0
    labels["VIS-03"] = has_logo and crowd

    off = rng.random() < 0.35
    patch = (rng.choice(OFF_PALETTE), rng.uniform(0.12, 0.25)) if off else None
    accent = rng.choice(OFF_PALETTE) if (not off and rng.random() < 0.25) else None
    labels["VIS-01"] = off
    labels["text_rules"] = text_rules
    labels["expected_text"] = [line.text for line in lines]
    return Spec(
        f"gen_{index:03d}",
        size[0],
        size[1],
        background,
        lines,
        logo,
        stretch,
        crowd,
        patch,
        accent,
        labels,
    )


# --- samples ---------------------------------------------------------------------------


def festive_banner() -> Spec:
    return Spec(
        "festive_banner",
        1200,
        630,
        NAVY,
        [
            Line("India's #1 payments app", WHITE, 54, bold=True),
            Line("100% secure payments this festive season", WHITE, 36),
            Line("Cashback offer valid till 31 December", LOW_CONTRAST[NAVY], 30),
        ],
        logo=(84, 60, 70),
        patch=("#E0115F", 0.16),
        labels={
            "VIS-01": True,
            "ACC-01": True,
            "VIS-02": False,
            "VIS-03": False,
            "logo": True,
            "text_rules": ["CLM-01", "CLM-04"],
        },
    )


def stretched_post() -> Spec:
    return Spec(
        "stretched_logo_post",
        1080,
        1080,
        CLOUD,
        [
            Line("Get paid faster with PayWise", NAVY, 52, bold=True),
            Line("Simple invoices for growing shops", NAVY, 34),
        ],
        logo=(76, 110, 120),
        stretch=1.4,
        crowd_logo=True,
        labels={
            "VIS-01": False,
            "ACC-01": False,
            "VIS-02": True,
            "VIS-03": True,
            "logo": True,
            "text_rules": [],
        },
    )


def clean_visual() -> Spec:
    return Spec(
        "clean_visual",
        1200,
        630,
        WHITE,
        [
            Line("Settle payments in under 10 seconds", NAVY, 50, bold=True),
            Line("Bank-grade encryption on every payment", CHARCOAL, 34),
            Line("Learn more at paywise.example", CHARCOAL, 28),
        ],
        logo=(84, 60, 70),
        labels={
            "VIS-01": False,
            "ACC-01": False,
            "VIS-02": False,
            "VIS-03": False,
            "logo": True,
            "text_rules": [],
        },
    )


def scanned_flyer() -> Image.Image:
    """A grey, slightly noisy 'scan' of a printed flyer with an outdated settlement time."""
    page = Image.new("RGB", (1240, 1754), "#FBFAF6")
    d = ImageDraw.Draw(page)
    page.paste(logo_lockup(110).convert("RGB"), (110, 120))
    y = 380
    for text, size in [
        ("Merchant update", 64),
        ("PayWise now settles merchant payments in under 5 seconds.", 38),
        ("No setup fee for new shops this month.", 38),
        ("Questions? Visit paywise.example/merchants", 32),
    ]:
        d.text((110, y), text, font=font(size), fill="#222222")
        y += int(size * 2.1)
    page = page.rotate(0.6, resample=Image.Resampling.BICUBIC, fillcolor="#FBFAF6")
    rng = random.Random(11)
    px = page.load()
    for _ in range(9000):
        x, yy = rng.randrange(page.width), rng.randrange(page.height)
        g = rng.randrange(150, 230)
        px[x, yy] = (g, g, g)
    return page.filter(ImageFilter.GaussianBlur(0.6))


def write_pdf(image: Image.Image, path: Path) -> None:
    """An image-only PDF (no text layer, a JPEG per page), like a real scan."""
    buffer = io.BytesIO()
    image.convert("L").save(buffer, format="JPEG", quality=70)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=buffer.getvalue())
    doc.save(path, deflate=True)


EMAIL_HTML = """<!doctype html>
<html><body style="margin:0;background:#F4F7FA;font-family:Arial,sans-serif;color:#13294B">
  <table width="600" align="center" style="background:#FFFFFF">
    <tr><td style="padding:24px">
      <img src="https://paywise.example/img/logo.png" alt="PayWise logo" width="140">
      <h1 style="color:#13294B">Your October merchant round-up</h1>
      <p>Settle payments in under 10 seconds and track every payment in one place.</p>
      <img src="https://paywise.example/img/festive-banner.png" width="552">
      <p style="color:#E0115F">Earn cashback on your first ten bill payments.</p>
      <img src="https://paywise.example/img/team.jpg"
           alt="image of team_photo_final.jpg" width="552">
      <p>Warm regards,<br>The PayWise team</p>
    </td></tr>
  </table>
</body></html>
"""


def main() -> None:
    BRAND.mkdir(parents=True, exist_ok=True)
    FILES.mkdir(parents=True, exist_ok=True)
    EVAL.mkdir(parents=True, exist_ok=True)
    logo_mark(256).save(BRAND / "paywise_mark.png")
    (BRAND / "paywise_mark.svg").write_text(LOGO_SVG, encoding="utf-8")
    logo_lockup(160).save(BRAND / "paywise_logo.png")

    samples = [festive_banner(), stretched_post(), clean_visual()]
    for spec in samples:
        compose(spec).save(FILES / f"paywise_{spec.name}.png", optimize=True)
    flyer = scanned_flyer()
    write_pdf(flyer, FILES / "paywise_scanned_flyer.pdf")
    (FILES / "paywise_email_with_images.html").write_text(EMAIL_HTML, encoding="utf-8")

    rng = random.Random(2026)
    labels = []
    for index in range(96):
        spec = generated_spec(index, rng)
        image = compose(spec)
        name = f"{spec.name}.png"
        if index % 4 == 3:  # a quarter are JPEGs, as real exports often are
            name = f"{spec.name}.jpg"
            image.save(EVAL / name, quality=85)
        else:
            image.save(EVAL / name, optimize=True)
        labels.append({"file": name, **spec.labels})
    for spec in samples:
        name = f"sample_{spec.name}.png"
        compose(spec).save(EVAL / name, optimize=True)
        labels.append(
            {"file": name, **spec.labels, "expected_text": [line.text for line in spec.lines]}
        )
    flyer.convert("L").resize((620, 877)).save(EVAL / "sample_scanned_flyer.png", optimize=True)
    labels.append(
        {
            "file": "sample_scanned_flyer.png",
            "VIS-01": False,
            "ACC-01": False,
            "VIS-02": False,
            "VIS-03": False,
            "logo": True,
            "text_rules": [],
            "expected_text": ["PayWise now settles merchant payments in under 5 seconds."],
        }
    )
    labels = labels[:100]
    (EVAL / "labels.json").write_text(json.dumps(labels, indent=1), encoding="utf-8")
    counts = {
        k: sum(1 for item in labels if item.get(k))
        for k in ("VIS-01", "VIS-02", "VIS-03", "ACC-01", "logo")
    }
    print(f"{len(labels)} assets; positives: {counts}", file=sys.stderr)


if __name__ == "__main__":
    main()
