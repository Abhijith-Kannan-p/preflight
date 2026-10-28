"""Colour maths for the visual review: sRGB to CIELAB, CIEDE2000 colour difference, WCAG 2.2
contrast ratio and a small deterministic k-means. Pure numpy, no extra dependencies.

CIEDE2000 follows Sharma, Wu and Dalal (2005), "The CIEDE2000 Color-Difference Formula:
Implementation Notes, Supplementary Test Data, and Mathematical Observations"; the tests use
their published test pairs.
"""

import numpy as np
from numpy.typing import ArrayLike, NDArray

Floats = NDArray[np.float64]

# D65 reference white for sRGB.
_WHITE = np.array([0.95047, 1.0, 1.08883])
_RGB_TO_XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ]
)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    if len(value) != 6:
        raise ValueError(f"not a hex colour: #{value}")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def rgb_to_hex(rgb: ArrayLike) -> str:
    values = np.asarray(rgb, dtype=np.float64).ravel()[:3]
    return "#" + "".join(f"{int(round(max(0.0, min(255.0, float(c))))):02X}" for c in values)


def _linear(rgb: Floats) -> Floats:
    """sRGB 0-255 to linear-light 0-1 (the sRGB transfer function)."""
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def rgb_to_lab(rgb: Floats) -> Floats:
    """Convert (..., 3) sRGB values in 0-255 to CIELAB (D65)."""
    xyz = _linear(rgb) @ _RGB_TO_XYZ.T / _WHITE
    eps, kappa = 216 / 24389, 24389 / 27
    f = np.where(xyz > eps, np.cbrt(xyz), (kappa * xyz + 16) / 116)
    lab: Floats = np.empty_like(f, dtype=np.float64)
    lab[..., 0] = 116 * f[..., 1] - 16
    lab[..., 1] = 500 * (f[..., 0] - f[..., 1])
    lab[..., 2] = 200 * (f[..., 1] - f[..., 2])
    return lab


def ciede2000(lab1: Floats, lab2: Floats) -> Floats:
    """CIEDE2000 colour difference between broadcastable (..., 3) Lab arrays (kL=kC=kH=1)."""
    lab1, lab2 = np.asarray(lab1, dtype=np.float64), np.asarray(lab2, dtype=np.float64)
    l1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    l2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    c_bar = (np.hypot(a1, b1) + np.hypot(a2, b2)) / 2
    g = 0.5 * (1 - np.sqrt(c_bar**7 / (c_bar**7 + 25.0**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    h1p = np.where((a1p == 0) & (b1 == 0), 0.0, h1p)
    h2p = np.where((a2p == 0) & (b2 == 0), 0.0, h2p)

    dlp, dcp = l2 - l1, c2p - c1p
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(c1p * c2p == 0, 0.0, dh)
    dhp = 2 * np.sqrt(c1p * c2p) * np.sin(np.radians(dh) / 2)

    lp_bar, cp_bar = (l1 + l2) / 2, (c1p + c2p) / 2
    h_sum = h1p + h2p
    hp_bar = np.where(
        c1p * c2p == 0,
        h_sum,
        np.where(
            np.abs(h1p - h2p) <= 180,
            h_sum / 2,
            np.where(h_sum < 360, (h_sum + 360) / 2, (h_sum - 360) / 2),
        ),
    )
    t = (
        1
        - 0.17 * np.cos(np.radians(hp_bar - 30))
        + 0.24 * np.cos(np.radians(2 * hp_bar))
        + 0.32 * np.cos(np.radians(3 * hp_bar + 6))
        - 0.20 * np.cos(np.radians(4 * hp_bar - 63))
    )
    d_theta = 30 * np.exp(-(((hp_bar - 275) / 25) ** 2))
    r_c = 2 * np.sqrt(cp_bar**7 / (cp_bar**7 + 25.0**7))
    s_l = 1 + 0.015 * (lp_bar - 50) ** 2 / np.sqrt(20 + (lp_bar - 50) ** 2)
    s_c = 1 + 0.045 * cp_bar
    s_h = 1 + 0.015 * cp_bar * t
    r_t = -np.sin(np.radians(2 * d_theta)) * r_c
    return np.asarray(
        np.sqrt(
            (dlp / s_l) ** 2 + (dcp / s_c) ** 2 + (dhp / s_h) ** 2 + r_t * (dcp / s_c) * (dhp / s_h)
        )
    )


def relative_luminance(rgb: ArrayLike) -> float:
    """WCAG 2.2 relative luminance of an sRGB colour (0-255 channels)."""
    r, g, b = _linear(np.asarray(rgb, dtype=np.float64).ravel()[:3])
    return float(0.2126 * r + 0.7152 * g + 0.0722 * b)


def contrast_ratio(fg: ArrayLike, bg: ArrayLike) -> float:
    """WCAG 2.2 contrast ratio, from 1 (no contrast) to 21 (black on white)."""
    a, b = relative_luminance(fg), relative_luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def kmeans(
    pixels: Floats, k: int, iterations: int = 20, seed: int = 7
) -> tuple[Floats, NDArray[np.intp]]:
    """Deterministic k-means (k-means++ seeding) on (n, 3) colours. Returns centres and labels."""
    pixels = np.asarray(pixels, dtype=np.float64)
    n = len(pixels)
    k = max(1, min(k, n))
    rng = np.random.default_rng(seed)
    centres = [pixels[rng.integers(n)]]
    for _ in range(1, k):
        d2 = np.min(((pixels[:, None, :] - np.array(centres)[None]) ** 2).sum(-1), axis=1)
        total = d2.sum()
        if total == 0:
            break
        centres.append(pixels[rng.choice(n, p=d2 / total)])
    c = np.array(centres)
    labels = np.zeros(n, dtype=np.intp)
    for _ in range(iterations):
        labels = ((pixels[:, None, :] - c[None]) ** 2).sum(-1).argmin(axis=1)
        moved = np.array(
            [
                pixels[labels == j].mean(axis=0) if np.any(labels == j) else c[j]
                for j in range(len(c))
            ]
        )
        if np.allclose(moved, c, atol=0.5):
            c = moved
            break
        c = moved
    return c, labels
