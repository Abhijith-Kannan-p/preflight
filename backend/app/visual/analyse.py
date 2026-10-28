"""The visual review of one asset (an image, or the pages of a scanned PDF).

For each page: OCR (text becomes ordinary blocks with boxes), palette compliance (k-means
colours vs the brand palette, CIEDE2000), WCAG contrast for every text line, and the logo
(distortion and clear space). Produces findings with image regions plus a report the UI
draws: the palette strip, contrast measurements, the logo box and timings.
"""

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image

from app.engine.context import ReviewContext
from app.engine.schema import Finding, LineBox, NormalisedDoc, Region, RuleRef, Span
from app.visual import logo as logo_check
from app.visual import ocr
from app.visual.brand import (
    CLEAR_SPACE_RATIO,
    DEFAULT_PALETTE,
    MAX_DISTORTION,
    OFF_PALETTE_COVERAGE,
    OFF_PALETTE_DELTA_E,
)
from app.visual.colour import ciede2000, contrast_ratio, hex_to_rgb, kmeans, rgb_to_hex, rgb_to_lab

EventSink = Callable[[str, dict[str, Any]], Awaitable[None]]
PALETTE_K = 6
# WCAG "large text" is 18 pt (24 CSS px). Assuming an image is shown at its own size, a line
# box is about 1.2 times the font size, so boxes at least 29 px tall hold large text.
LARGE_TEXT_BOX_PX = 29

VISUAL_CHECKERS = [
    ("ocr", "Text in the image (OCR)"),
    ("palette", "Brand colours"),
    ("contrast", "Text contrast (WCAG 2.2)"),
    ("logo", "Logo use"),
]


@dataclass
class VisualResult:
    doc: NormalisedDoc
    findings: list[Finding]
    report: dict[str, Any]
    timings: dict[str, int] = field(default_factory=dict)
    # One entry per visual step, in the same shape as the text checkers' runs.
    runs: list[dict[str, Any]] = field(default_factory=list)


def palette_of(ctx: ReviewContext) -> list[dict[str, str]]:
    palette = ctx.settings.get("brand_palette") or DEFAULT_PALETTE
    return [{"name": str(c["name"]), "hex": str(c["hex"]).upper()} for c in palette]


def _rule(ctx: ReviewContext, code: str) -> RuleRef | None:
    rule = ctx.rule(code)
    return RuleRef(id=code, source=rule.source_ref) if rule else None


def _finding(
    ctx: ReviewContext,
    code: str,
    kind: str,
    explanation: str,
    region: Region | None,
    confidence: float,
    severity: str | None = None,
    span: Span | None = None,
    text: str = "",
) -> Finding | None:
    rule = _rule(ctx, code)
    if rule is None:
        return None
    return Finding(
        type=kind,
        span=span or Span(block=0, start=0, end=0),
        text=text,
        rule=rule,
        severity=severity or ctx.rules[code].severity,
        confidence=round(confidence, 2),
        explanation=explanation,
        detector="rules",
        region=region,
    )


# --- palette -----------------------------------------------------------------------------


def check_palette(
    image: Image.Image, page: int, ctx: ReviewContext
) -> tuple[list[dict[str, Any]], list[Finding]]:
    small = image.convert("RGB").copy()
    small.thumbnail((120, 120))
    pixels = np.asarray(small).reshape(-1, 3).astype(np.float64)
    centres, labels = kmeans(pixels, PALETTE_K)
    palette = palette_of(ctx)
    brand_lab = rgb_to_lab(np.array([hex_to_rgb(c["hex"]) for c in palette], dtype=np.float64))
    width, height = small.size
    grid = labels.reshape(height, width)
    entries: list[dict[str, Any]] = []
    findings: list[Finding] = []
    for index, centre in enumerate(centres):
        coverage = float((labels == index).mean())
        if coverage < 0.01:
            continue
        distances = ciede2000(rgb_to_lab(centre[None, :])[0][None, :], brand_lab)
        nearest = int(np.argmin(distances))
        delta = float(distances[nearest])
        off = coverage > OFF_PALETTE_COVERAGE and delta > OFF_PALETTE_DELTA_E
        entry = {
            "hex": rgb_to_hex(centre),
            "coverage": round(coverage, 3),
            "nearest": palette[nearest],
            "delta_e": round(delta, 1),
            "off_palette": off,
        }
        entries.append(entry)
        if off:
            ys, xs = np.nonzero(grid == index)
            region = Region(
                page=page,
                x=xs.min() / width,
                y=ys.min() / height,
                w=(xs.max() + 1 - xs.min()) / width,
                h=(ys.max() + 1 - ys.min()) / height,
            )
            finding = _finding(
                ctx,
                "VIS-01",
                "visual",
                f"{entry['hex']} covers {coverage:.0%} of the image and is not a brand colour: "
                f"the closest, {palette[nearest]['name']} {palette[nearest]['hex']}, is "
                f"ΔE00 {delta:.1f} away (the limit is {OFF_PALETTE_DELTA_E:.0f}).",
                region,
                confidence=min(0.99, 0.7 + delta / 100),
            )
            if finding:
                findings.append(finding)
    entries.sort(key=lambda e: -e["coverage"])
    return entries, findings


# --- contrast ----------------------------------------------------------------------------


def _line_colours(rgb: np.ndarray, line: ocr.OcrLine) -> tuple[np.ndarray, np.ndarray] | None:
    """Background = the most common colour around the box edge; text = the pixels inside
    the box furthest from it (anti-aliased edge pixels would understate the contrast)."""
    height, width = rgb.shape[:2]
    x0, y0 = max(0, int(line.x0) - 2), max(0, int(line.y0) - 2)
    x1, y1 = min(width, int(line.x1) + 2), min(height, int(line.y1) + 2)
    crop = rgb[y0:y1, x0:x1].reshape(-1, 3).astype(np.float64)
    if len(crop) < 20:
        return None
    box = rgb[y0:y1, x0:x1]
    edge = np.concatenate([box[0], box[-1], box[:, 0], box[:, -1]]).astype(np.int32)
    colours, counts = np.unique(edge // 6, axis=0, return_counts=True)
    background = colours[counts.argmax()].astype(np.float64) * 6 + 3
    distance = np.abs(crop - background).max(axis=1)
    far = crop[distance >= np.percentile(distance, 90)]
    if len(far) == 0 or np.abs(far.mean(axis=0) - background).max() < 12:
        return None
    return np.median(far, axis=0), background


def _within(line: ocr.OcrLine, box: tuple[int, int, int, int]) -> bool:
    x0, y0, x1, y1 = box
    return x0 - 2 <= line.x0 and line.x1 <= x1 + 2 and y0 - 2 <= line.y0 and line.y1 <= y1 + 2


def check_contrast(
    image: Image.Image,
    page: int,
    lines: list[ocr.OcrLine],
    layout: list[LineBox],
    scale: float,
    ctx: ReviewContext,
    doc_blocks: list[Any],
    logo: logo_check.LogoMatch | None = None,
) -> tuple[list[dict[str, Any]], list[Finding]]:
    """WCAG contrast of every text line, except the logo's own wordmark (logo rules cover it)."""
    rgb = np.asarray(image.convert("RGB"))
    lockup = logo_check.lockup_box(logo, lines) if logo else None
    page_boxes = [b for b in layout if b.page == page]
    measured: list[dict[str, Any]] = []
    findings: list[Finding] = []
    for line, box in zip(lines, page_boxes, strict=False):
        if lockup and _within(line, lockup):
            continue
        colours = _line_colours(rgb, line)
        if colours is None:
            continue
        text_rgb, bg_rgb = colours
        ratio = contrast_ratio(text_rgb, bg_rgb)
        large = line.height / scale >= LARGE_TEXT_BOX_PX
        needed = 3.0 if large else 4.5
        passed = ratio >= needed
        region = Region(page=page, x=box.x, y=box.y, w=box.w, h=box.h)
        measured.append(
            {
                "text": line.text,
                "ratio": round(ratio, 2),
                "needed": needed,
                "large": large,
                "passed": passed,
                "foreground": rgb_to_hex(text_rgb),
                "background": rgb_to_hex(bg_rgb),
                "region": region.model_dump(),
            }
        )
        if passed:
            continue
        block_text = doc_blocks[box.block].text
        finding = _finding(
            ctx,
            "ACC-01",
            "accessibility",
            f"Text contrast is {ratio:.1f}:1 ({rgb_to_hex(text_rgb)} on {rgb_to_hex(bg_rgb)}); "
            f"WCAG 2.2 AA needs {needed:g}:1 for {'large' if large else 'normal'} text.",
            region,
            confidence=0.9 if ratio < needed - 0.5 else 0.7,
            span=Span(block=box.block, start=box.start, end=box.end),
            text=block_text[box.start : box.end],
        )
        if finding:
            findings.append(finding)
    return measured, findings


# --- logo --------------------------------------------------------------------------------


def _without_logo(
    lines: list[ocr.OcrLine], match: logo_check.LogoMatch | None
) -> list[ocr.OcrLine]:
    if match is None:
        return lines
    lockup = logo_check.lockup_box(match, lines)
    return [line for line in lines if not (_inside(line, match) or _within(line, lockup))]


def _inside(line: ocr.OcrLine, match: logo_check.LogoMatch) -> bool:
    cx, cy = (line.x0 + line.x1) / 2, (line.y0 + line.y1) / 2
    return match.x <= cx <= match.x + match.w and match.y <= cy <= match.y + match.h


def check_logo(
    image: Image.Image,
    page: int,
    lines: list[ocr.OcrLine],
    ctx: ReviewContext,
    match: logo_check.LogoMatch | None,
) -> tuple[dict[str, Any] | None, list[Finding]]:
    if match is None:
        return None, []
    width, height = image.size
    region = Region(
        page=page,
        x=match.x / width,
        y=match.y / height,
        w=min(1.0, match.w / width),
        h=min(1.0, match.h / height),
    )
    report: dict[str, Any] = {
        "region": region.model_dump(),
        "aspect": round(match.aspect, 3),
        "distortion": round(match.distortion, 3),
        "score": round(match.score, 3),
        "clear_space": None,
    }
    findings: list[Finding] = []
    if match.distortion > MAX_DISTORTION:
        direction = "stretched" if match.aspect > 1 else "squashed"
        finding = _finding(
            ctx,
            "VIS-02",
            "visual",
            f"The logo is {direction}: its width-to-height ratio is {match.aspect:.2f} instead of "
            f"1.00 ({match.distortion:.0%} distortion; the limit is {MAX_DISTORTION:.0%}). "
            "Resize it proportionally.",
            region,
            confidence=min(0.99, 0.75 + match.distortion),
        )
        if finding:
            findings.append(finding)
    intrusion = logo_check.clear_space_intrusion(image, match, lines)
    if intrusion is not None:
        share, (rx0, ry0, rx1, ry1) = intrusion
        ring = Region(
            page=page, x=rx0 / width, y=ry0 / height, w=(rx1 - rx0) / width, h=(ry1 - ry0) / height
        )
        report["clear_space"] = {"region": ring.model_dump(), "occupied": round(share, 3)}
        finding = _finding(
            ctx,
            "VIS-03",
            "visual",
            f"Something sits inside the logo's clear space ({share:.0%} of the margin is "
            f"occupied). Keep {CLEAR_SPACE_RATIO:.0%} of the logo's height empty on every side.",
            ring,
            confidence=0.8,
        )
        if finding:
            findings.append(finding)
    return report, findings


# --- the whole asset ---------------------------------------------------------------------


async def analyse(
    pages: list[Image.Image],
    ctx: ReviewContext,
    source_format: str,
    images: list[Any],
    emit: EventSink,
    scales: list[float] | None = None,
) -> VisualResult:
    """`scales[i]`: how much page i was reduced from the original (for "large text")."""
    scales = scales or [1.0] * len(pages)
    timings: dict[str, int] = {}
    runs: list[dict[str, Any]] = []

    async def stage(name: str, label: str) -> float:
        await emit("checker_started", {"checker": name, "label": label})
        return time.perf_counter()

    async def done(name: str, label: str, started: float, found: int) -> None:
        ms = int((time.perf_counter() - started) * 1000)
        timings[name] = timings.get(name, 0) + ms
        run = {"name": name, "label": label, "ok": True, "findings": found, "ms": ms}
        runs.append(run)
        await emit("checker_done", run)

    started = await stage("ocr", "Text in the image (OCR)")
    all_lines = [ocr.read(page, source_format) for page in pages]
    # The logo (its letterform and its "PayWise" wordmark) is not copy: logo rules cover it,
    # so its lines are dropped before the text checks.
    matches = [logo_check.find_logo(page) for page in pages]
    page_lines = [
        _without_logo(lines, match) for lines, match in zip(all_lines, matches, strict=True)
    ]
    blocks, layout = ocr.to_blocks(
        [(lines, page.width, page.height) for lines, page in zip(page_lines, pages, strict=True)]
    )
    await done("ocr", "Text in the image (OCR)", started, sum(len(lines) for lines in page_lines))
    doc = NormalisedDoc(blocks=blocks, source_format=source_format, layout=layout, images=images)

    findings: list[Finding] = []
    report_pages: list[dict[str, Any]] = []
    started = await stage("palette", "Brand colours")
    palettes = [check_palette(page, i, ctx) for i, page in enumerate(pages)]
    await done("palette", "Brand colours", started, sum(len(f) for _, f in palettes))

    started = await stage("contrast", "Text contrast (WCAG 2.2)")
    contrasts = [
        check_contrast(page, i, page_lines[i], layout, scales[i], ctx, blocks, matches[i])
        for i, page in enumerate(pages)
    ]
    await done("contrast", "Text contrast (WCAG 2.2)", started, sum(len(f) for _, f in contrasts))

    started = await stage("logo", "Logo use")
    # The logo checks need the wordmark's line to know where the lockup ends.
    logos = [check_logo(page, i, all_lines[i], ctx, matches[i]) for i, page in enumerate(pages)]
    await done("logo", "Logo use", started, sum(len(f) for _, f in logos))

    for i, page in enumerate(pages):
        entries, palette_findings = palettes[i]
        measured, contrast_findings = contrasts[i]
        logo_report, logo_findings = logos[i]
        findings += palette_findings + contrast_findings + logo_findings
        report_pages.append(
            {
                "index": i,
                "width": page.width,
                "height": page.height,
                "palette": entries,
                "contrast": measured,
                "logo": logo_report,
                "lines": len(page_lines[i]),
            }
        )
    report = {
        "pages": report_pages,
        "brand_palette": palette_of(ctx),
        "timings_ms": timings,
        "thresholds": {
            "off_palette_coverage": OFF_PALETTE_COVERAGE,
            "off_palette_delta_e": OFF_PALETTE_DELTA_E,
            "max_distortion": MAX_DISTORTION,
            "clear_space_ratio": CLEAR_SPACE_RATIO,
            "large_text_box_px": LARGE_TEXT_BOX_PX,
        },
    }
    return VisualResult(doc=doc, findings=findings, report=report, timings=timings, runs=runs)


def attach_regions(findings: list[Finding], doc: NormalisedDoc) -> None:
    """Give text findings on OCR text the box of the lines their span covers, so every
    finding can be drawn on the image."""
    for finding in findings:
        if finding.region is not None or finding.document_level:
            continue
        boxes = [
            b
            for b in doc.layout
            if b.block == finding.span.block
            and b.start < finding.span.end
            and finding.span.start < b.end
        ]
        if not boxes:
            continue
        x0, y0 = min(b.x for b in boxes), min(b.y for b in boxes)
        x1, y1 = max(b.x + b.w for b in boxes), max(b.y + b.h for b in boxes)
        finding.region = Region(page=boxes[0].page, x=x0, y=y0, w=x1 - x0, h=y1 - y0)
