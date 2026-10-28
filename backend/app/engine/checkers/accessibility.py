"""AccessibilityChecker: alt text for images (HTML emails, DOCX files and uploaded images) and
brand colours declared in HTML emails.

- ACC-02: an image in an HTML email or a DOCX has no alt text at all.
- ACC-03: alt text that does not describe anything ("image of…", a file name, one word),
  and an uploaded image whose alt text was left empty.
- VIS-01: a colour set in the email's CSS that is not in the brand palette.
"""

import re

import numpy as np

from app.engine.context import ReviewContext
from app.engine.schema import Finding, ImageRef, NormalisedDoc, RuleRef, Span
from app.visual.brand import DEFAULT_PALETTE, OFF_PALETTE_DELTA_E
from app.visual.colour import ciede2000, hex_to_rgb, rgb_to_lab

_FILE_NAME = re.compile(
    r"\.(png|jpe?g|gif|webp|svg|bmp|tiff?)\b|^(img|dsc|image|photo)[-_ ]?\d+", re.I
)
_FILLER = re.compile(
    r"^\s*(an?\s+)?(image|picture|photo|graphic|screenshot)\s+(of|showing)\b", re.I
)
_BLANK_WORDS = {"image", "picture", "photo", "graphic", "banner", "logo", "img", "icon"}


def alt_problem(alt: str | None) -> str | None:
    """Why this alt text is not useful, or None if it is fine. `None` alt is handled apart."""
    text = (alt or "").strip()
    if not text:
        return "is empty"
    if _FILE_NAME.search(text):
        return "contains a file name"
    if _FILLER.match(text):
        return 'starts with "image of"; screen readers already announce that it is an image'
    words = re.findall(r"[\w'#%-]+", text)
    if len(words) < 2 or {w.lower() for w in words} <= _BLANK_WORDS:
        return "is too short to describe the image"
    if len(text) > 250:
        return "is longer than 250 characters; move the detail into the body text"
    return None


class AccessibilityChecker:
    name = "accessibility"
    label = "Alt text and email colours"

    async def run(self, doc: NormalisedDoc, ctx: ReviewContext) -> list[Finding]:
        findings: list[Finding] = []
        for image in doc.images:
            finding = self._alt_finding(image, ctx)
            if finding:
                findings.append(finding)
        findings += self._css_colours(doc, ctx)
        return findings

    @staticmethod
    def _make(
        ctx: ReviewContext, code: str, kind: str, explanation: str, conf: float
    ) -> Finding | None:
        rule = ctx.rule(code)
        if rule is None:
            return None
        return Finding(
            type=kind,
            span=Span(block=0, start=0, end=0),
            text="",
            rule=RuleRef(id=code, source=rule.source_ref),
            severity=rule.severity,
            confidence=conf,
            explanation=explanation,
            detector="rules",
        )

    def _alt_finding(self, image: ImageRef, ctx: ReviewContext) -> Finding | None:
        where = {"html": "in the email", "docx": "in the document", "upload": ""}[image.source]
        name = f"“{image.name}” {where}".strip()
        if image.alt is None and image.source != "upload":
            return self._make(
                ctx,
                "ACC-02",
                "accessibility",
                f"The image {name} has no alt text, so screen-reader users miss it entirely. "
                'Add an alt attribute that says what the image shows (use alt="" only for '
                "purely decorative images).",
                0.97,
            )
        problem = alt_problem(image.alt)
        if problem is None:
            return None
        return self._make(
            ctx,
            "ACC-03",
            "accessibility",
            f"The alt text for {name} {problem}. Describe what the image shows and says, "
            f"for example its headline.",
            0.9,
        )

    def _css_colours(self, doc: NormalisedDoc, ctx: ReviewContext) -> list[Finding]:
        if not doc.colours:
            return []
        palette = ctx.settings.get("brand_palette") or DEFAULT_PALETTE
        brand = rgb_to_lab(np.array([hex_to_rgb(c["hex"]) for c in palette], dtype=np.float64))
        findings: list[Finding] = []
        for colour in sorted(set(doc.colours)):
            try:
                lab = rgb_to_lab(np.array([hex_to_rgb(colour)], dtype=np.float64))
            except ValueError:
                continue
            distances = ciede2000(lab, brand)
            nearest = int(np.argmin(distances))
            delta = float(distances[nearest])
            if delta <= OFF_PALETTE_DELTA_E:
                continue
            finding = self._make(
                ctx,
                "VIS-01",
                "visual",
                f"The email's CSS uses {colour.upper()}, which is not a brand colour: the closest, "
                f"{palette[nearest]['name']} {palette[nearest]['hex']}, is ΔE00 {delta:.1f} away "
                f"(the limit is {OFF_PALETTE_DELTA_E:.0f}).",
                0.9,
            )
            if finding:
                findings.append(finding)
        return findings
