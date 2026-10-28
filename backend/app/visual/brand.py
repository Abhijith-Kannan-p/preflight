"""The fictional PayWise visual identity: default palette, logo files and clear-space rule.

The palette lives in the workspace settings (`brand_palette`) so a brand manager can edit
it; these are the seeded defaults. The logo is our own simple design, drawn by
scripts/make_visual_data.py.
"""

from pathlib import Path

from app.config import get_settings

DEFAULT_PALETTE: list[dict[str, str]] = [
    {"name": "PayWise Navy", "hex": "#13294B"},
    {"name": "PayWise Teal", "hex": "#12A594"},
    {"name": "Sky", "hex": "#4FB3E8"},
    {"name": "Sunrise", "hex": "#F5A623"},
    {"name": "Charcoal", "hex": "#2E3440"},
    {"name": "Cloud", "hex": "#F4F7FA"},
    {"name": "White", "hex": "#FFFFFF"},
]

# Brand book: keep clear space of at least a quarter of the logo's height on every side.
CLEAR_SPACE_RATIO = 0.25
# A logo stretched or squashed by more than this is a misuse.
MAX_DISTORTION = 0.05
# Colours covering more than this share of an image, further than this from every brand
# colour (CIEDE2000), are off-palette.
OFF_PALETTE_COVERAGE = 0.08
OFF_PALETTE_DELTA_E = 10.0


def brand_dir() -> Path:
    return get_settings().data_dir / "brand"


def logo_mark_path() -> Path:
    return brand_dir() / "paywise_mark.png"
