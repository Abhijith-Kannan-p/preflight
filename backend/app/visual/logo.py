"""Find the PayWise logo mark and check it is used correctly.

Detection is multi-scale template matching (OpenCV, normalised cross-correlation) over a
range of sizes *and aspect ratios*: the aspect ratio of the best match is the measured
distortion. The search runs coarse-to-fine (a small copy of the image first, then a narrow
search at full resolution) so it stays fast on a 0.1-CPU host.

Clear space: the lockup (mark plus the "PayWise" wordmark that OCR finds beside it) must
have empty margin of `CLEAR_SPACE_RATIO` times the logo height on every side. Anything in
that ring that differs from the ring's background colour, or any other OCR text inside it,
is a violation.
"""

from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from app.visual.brand import CLEAR_SPACE_RATIO, logo_mark_path
from app.visual.ocr import OcrLine

Gray = NDArray[np.uint8]
MATCH_THRESHOLD = 0.62
COARSE_WIDTH = 320
COARSE_ASPECTS = [0.62, 0.8, 1.0, 1.25, 1.6]
TEAL = np.array([0x12, 0xA5, 0x94])
# The template is the mark without this share of its side on each edge (rounded corners).
INNER_CUT = 0.12
INTRUSION_THRESHOLD = 0.05
# The real mark is mostly brand teal; a candidate that is not is a chance correlation.
MIN_TEAL_SHARE = 0.25


@dataclass(frozen=True)
class LogoMatch:
    x: int
    y: int
    w: int
    h: int
    score: float

    @property
    def aspect(self) -> float:
        """Width over height of the (square) mark as found: 1.0 means undistorted."""
        return self.w / self.h

    @property
    def distortion(self) -> float:
        return abs(self.aspect - 1.0)


@lru_cache(maxsize=1)
def _template() -> Gray:
    """The opaque inner part of the mark (the rounded transparent corners are cut away)."""
    mark = Image.open(logo_mark_path()).convert("RGBA")
    flat = Image.new("RGB", mark.size, "#FFFFFF")
    flat.paste(mark, mask=mark.split()[3])
    gray = np.asarray(flat.convert("L"))
    side = gray.shape[0]
    cut = int(side * INNER_CUT)
    return np.ascontiguousarray(gray[cut : side - cut, cut : side - cut])


def _best(image: Gray, sizes: list[int], aspects: list[float]) -> tuple[float, int, int, int, int]:
    template = _template()
    best = (-1.0, 0, 0, 0, 0)
    for h in sizes:
        for aspect in aspects:
            w = max(8, int(round(h * aspect)))
            if h >= image.shape[0] or w >= image.shape[1] or h < 8:
                continue
            scaled = cv2.resize(template, (w, h), interpolation=cv2.INTER_AREA)
            result = cv2.matchTemplate(image, scaled, cv2.TM_CCOEFF_NORMED)
            _, score, _, (x, y) = cv2.minMaxLoc(result)
            if score > best[0]:
                best = (float(score), x, y, w, h)
    return best


def find_logo(image: Image.Image) -> LogoMatch | None:
    """The best match of the logo mark, in `image` pixels, or None if it is not there."""
    gray: Gray = np.asarray(image.convert("L"))
    scale = min(1.0, COARSE_WIDTH / gray.shape[1])
    small: Gray = np.asarray(
        cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA), dtype=np.uint8
    )
    shortest = min(small.shape)
    # Logos are between about 4% and 35% of the shorter side.
    sizes, h = [], max(8, int(shortest * 0.04))
    while h < shortest * 0.35:
        sizes.append(h)
        h = int(h * 1.15) + 1
    score, x, y, w, h = _best(small, sizes, COARSE_ASPECTS)
    if score < MATCH_THRESHOLD - 0.15:
        return None
    # Refine around the coarse hit at full resolution: size and aspect in small steps.
    fx, fy, fw, fh = (int(v / scale) for v in (x, y, w, h))
    pad = int(fh * 0.5)
    x0, y0 = max(0, fx - pad), max(0, fy - pad)
    roi = gray[y0 : min(gray.shape[0], fy + fh + pad), x0 : min(gray.shape[1], fx + fw + pad)]
    roi = np.ascontiguousarray(roi)
    # Coordinate descent: best size at the current aspect, then best aspect at that size.
    aspect = fw / fh
    best = (-1.0, 0, 0, 0, 0)
    sizes = list(range(max(8, int(fh * 0.8)), int(fh * 1.25) + 1, max(1, fh // 40)))
    for _ in range(2):
        found = _best(roi, sizes, [aspect])
        if found[0] > best[0]:
            best, fh = found, found[4]
        aspects = [aspect * (0.85 + 0.01 * i) for i in range(31)]
        found = _best(roi, [fh], aspects)
        if found[0] > best[0]:
            best, aspect = found, found[3] / found[4]
    score, rx, ry, rw, rh = best
    if score < MATCH_THRESHOLD:
        return None
    match = LogoMatch(x0 + rx, y0 + ry, rw, rh, score)
    if _is_grayscale(image):
        # A scan or print: colour cannot confirm or measure it, so the shape match must do.
        # Grow the inner-part match to the whole tile.
        inner = 1 - 2 * INNER_CUT
        full_w, full_h = match.w / inner, match.h / inner
        return LogoMatch(
            max(0, int(round(match.x - INNER_CUT * full_w))),
            max(0, int(round(match.y - INNER_CUT * full_h))),
            int(round(full_w)),
            int(round(full_h)),
            match.score,
        )
    if _teal_share(image, match) < MIN_TEAL_SHARE:
        return None
    return _measure_tile(image, match)


def _measure_tile(image: Image.Image, match: LogoMatch) -> LogoMatch:
    """Measure the teal tile itself: its bounding box gives the aspect ratio to the pixel,
    which template matching alone cannot do for small logos."""
    rgb = np.asarray(image.convert("RGB")).astype(np.int16)
    pad_x, pad_y = int(match.w * 0.35), int(match.h * 0.35)
    x0, y0 = max(0, match.x - pad_x), max(0, match.y - pad_y)
    x1 = min(rgb.shape[1], match.x + match.w + pad_x)
    y1 = min(rgb.shape[0], match.y + match.h + pad_y)
    mask = (np.abs(rgb[y0:y1, x0:x1] - TEAL).max(axis=-1) < 50).astype(np.uint8)
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count < 2:
        return match
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    bx, by, bw, bh, _ = (int(v) for v in stats[biggest])
    if bw < 8 or bh < 8:
        return match
    return LogoMatch(x0 + bx, y0 + by, bw, bh, match.score)


def _is_grayscale(image: Image.Image) -> bool:
    rgb = np.asarray(image.convert("RGB").resize((64, 64))).astype(np.int16)
    return bool(np.abs(rgb - rgb.mean(axis=-1, keepdims=True)).max() < 12)


def _teal_share(image: Image.Image, match: LogoMatch) -> float:
    box = np.asarray(image.convert("RGB"))[match.y : match.y + match.h, match.x : match.x + match.w]
    if box.size == 0:
        return 0.0
    return float((np.abs(box.astype(np.int16) - TEAL).max(axis=-1) < 50).mean())


def lockup_box(match: LogoMatch, lines: list[OcrLine]) -> tuple[int, int, int, int]:
    """The mark plus a "PayWise" wordmark set beside it on the same line, if OCR found one."""
    x0, y0, x1, y1 = match.x, match.y, match.x + match.w, match.y + match.h
    centre = (y0 + y1) / 2
    for line in lines:
        beside = line.x0 > x0 and line.x0 - x1 < match.h * 0.8 and line.y0 < centre < line.y1
        if beside and "pay" in line.text.lower():
            x1, y0, y1 = max(x1, int(line.x1)), min(y0, int(line.y0)), max(y1, int(line.y1))
    return x0, y0, x1, y1


def clear_space_intrusion(
    image: Image.Image, match: LogoMatch, lines: list[OcrLine]
) -> tuple[float, tuple[int, int, int, int]] | None:
    """How much of the clear-space ring is occupied (0-1) and the ring's bounds, or None if
    the ring is clean."""
    rgb = np.asarray(image.convert("RGB")).astype(np.int16)
    height, width = rgb.shape[:2]
    lx0, ly0, lx1, ly1 = lockup_box(match, lines)
    margin = int(round(match.h * CLEAR_SPACE_RATIO))
    rx0, ry0 = max(0, lx0 - margin), max(0, ly0 - margin)
    rx1, ry1 = min(width, lx1 + margin), min(height, ly1 + margin)
    ring = np.ones((ry1 - ry0, rx1 - rx0), dtype=bool)
    ring[ly0 - ry0 : ly1 - ry0, lx0 - rx0 : lx1 - rx0] = False
    # A median filter removes scan speckle and JPEG noise before looking for intruders.
    area = cv2.medianBlur(np.ascontiguousarray(rgb[ry0:ry1, rx0:rx1], dtype=np.uint8), 5)
    pixels = area.astype(np.int16)[ring]
    if len(pixels) == 0:
        return None
    colours, counts = np.unique(pixels // 8, axis=0, return_counts=True)
    background = colours[counts.argmax()] * 8 + 4
    different = np.abs(pixels - background).max(axis=1) > 40
    share = float(different.mean())
    for line in lines:
        inside = line.x1 > rx0 and line.x0 < rx1 and line.y1 > ry0 and line.y0 < ry1
        outside_lockup = line.x0 >= lx1 or line.x1 <= lx0 or line.y0 >= ly1 or line.y1 <= ly0
        if inside and outside_lockup:
            share = max(share, 0.1)
    # Rotated or blurred edges of the logo itself can graze the ring by a few percent.
    return (share, (rx0, ry0, rx1, ry1)) if share > INTRUSION_THRESHOLD else None
