"""Colour maths against published reference values."""

import numpy as np
import pytest

from app.visual.colour import ciede2000, contrast_ratio, hex_to_rgb, kmeans, rgb_to_lab

# Sharma, Wu and Dalal (2005), Table 1: Lab pairs and their CIEDE2000 difference.
SHARMA = [
    ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
    ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
    ((50.0000, -1.3802, -84.2814), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, 0.0000, 0.0000), (50.0000, -1.0000, 2.0000), 2.3669),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0011), 7.2195),
    ((50.0000, 2.5000, 0.0000), (73.0000, 25.0000, -18.0000), 27.1492),
    ((50.0000, 2.5000, 0.0000), (58.0000, 24.0000, 15.0000), 19.4535),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((63.0109, -31.0961, -5.8663), (62.8187, -29.7946, -4.0864), 1.2630),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ((90.8027, -2.0831, 1.4410), (91.1528, -1.6435, 0.0447), 1.4441),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
]


@pytest.mark.parametrize(("lab1", "lab2", "expected"), SHARMA)
def test_ciede2000_matches_sharma_reference_data(
    lab1: tuple[float, ...], lab2: tuple[float, ...], expected: float
) -> None:
    assert ciede2000(np.array(lab1), np.array(lab2)) == pytest.approx(expected, abs=1e-4)
    assert ciede2000(np.array(lab2), np.array(lab1)) == pytest.approx(expected, abs=1e-4)


def test_lab_conversion_of_reference_colours() -> None:
    white, black, red = rgb_to_lab(np.array([[255, 255, 255], [0, 0, 0], [255, 0, 0]]))
    assert white == pytest.approx([100, 0, 0], abs=0.01)
    assert black == pytest.approx([0, 0, 0], abs=0.01)
    assert red == pytest.approx([53.24, 80.09, 67.20], abs=0.05)


def test_wcag_contrast_ratios() -> None:
    assert contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)
    assert contrast_ratio((255, 255, 255), (255, 255, 255)) == pytest.approx(1.0)
    # #767676 on white is the classic "just passes 4.5:1" grey.
    assert contrast_ratio(hex_to_rgb("#767676"), (255, 255, 255)) == pytest.approx(4.54, abs=0.01)
    assert contrast_ratio(hex_to_rgb("#777777"), (255, 255, 255)) < 4.5


def test_kmeans_recovers_flat_colour_regions() -> None:
    pixels = np.array([[19, 41, 75]] * 600 + [[245, 166, 35]] * 300 + [[255, 255, 255]] * 100)
    centres, labels = kmeans(pixels, k=3)
    found = sorted(tuple(int(round(v)) for v in c) for c in centres)
    assert found == sorted([(19, 41, 75), (245, 166, 35), (255, 255, 255)])
    assert sorted(np.bincount(labels).tolist()) == [100, 300, 600]
