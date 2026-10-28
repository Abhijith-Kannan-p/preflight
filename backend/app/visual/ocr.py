"""OCR with RapidOCR on ONNX Runtime (PP-OCRv4 detection + recognition models, bundled in the
wheel, about 15 MB). No Tesseract binary, no PyTorch.

The engine is loaded on first use and can be released again, so on a 512 MB host it never
shares memory with the NLI model (`OCR_EXCLUSIVE`).

Detection runs on a copy reduced to `DET_SIDE` pixels (RapidOCR's own setting is overridden:
in "max" mode it raises any limit under 1500 px, so detection ran at full size). Measured in
a 512 MB / 0.1-CPU container on a 1200x630 banner: full size peaked at +230 MiB and 6-8 s;
736 px at +63 MiB and about 4 s, reading the text as well. Recognition still reads the text
crops from the full-size image. Scanned pages use a larger detection size for small type.

Lines found on a page are grouped into paragraphs, which become ordinary text blocks: every
text checker then runs on them, and a per-line layout maps any finding back to its box.
"""

import logging
import re
import threading
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image

from app.config import get_settings
from app.engine.schema import Block, LineBox
from app.ml.memory import trim

log = logging.getLogger(__name__)

_lock = threading.Lock()
_engine: Any = None


@dataclass(frozen=True)
class OcrLine:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    score: float

    @property
    def height(self) -> float:
        return self.y1 - self.y0


DET_SIDE = {"image": 736, "scan": 960}


def _lean_options(config: dict[str, Any]) -> Any:
    """RapidOCR's sessions with our small-host settings (no arena, basic optimisation)."""
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.log_severity_level = 4
    options.enable_cpu_mem_arena = False
    options.enable_mem_pattern = False
    threads = get_settings().ocr_threads
    options.intra_op_num_threads = threads if threads > 0 else 0
    options.inter_op_num_threads = 1
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
    return options


def _load() -> Any:
    from rapidocr_onnxruntime import RapidOCR
    from rapidocr_onnxruntime.utils import infer_engine

    infer_engine.OrtInferSession._init_sess_opts = staticmethod(_lean_options)
    # Banners are rarely rotated; skipping the angle classifier saves time and memory.
    return RapidOCR(use_cls=False, rec_batch_num=1, print_verbose=False)


def _set_detection_size(engine: Any, side: int) -> None:
    from rapidocr_onnxruntime.ch_ppocr_det.utils import DetPreProcess

    det = engine.text_det
    det.get_preprocess = lambda _max_wh: DetPreProcess(side, "max", det.mean, det.std)


def available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        return False
    return True


def release() -> None:
    """Free the OCR models (they are reloaded on the next visual review)."""
    global _engine
    with _lock:
        _engine = None
    trim()


def read(image: Image.Image, kind: str = "image") -> list[OcrLine]:
    """Text lines on an RGB image, top to bottom, in that image's pixel coordinates."""
    global _engine
    with _lock:
        if _engine is None:
            _engine = _load()
        _set_detection_size(_engine, DET_SIDE.get(kind, DET_SIDE["image"]))
        result, _ = _engine(np.asarray(image.convert("RGB"))[:, :, ::-1])  # RapidOCR wants BGR
    lines: list[OcrLine] = []
    for box, text, score in result or []:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        if text.strip():
            text = respace(text.strip())
            lines.append(OcrLine(text, min(xs), min(ys), max(xs), max(ys), float(score)))
    return sorted(lines, key=lambda line: (round(line.y0 / 8), line.x0))


_GLUED = [
    (re.compile(r"(?<=[a-z])(?=\d)"), " "),  # "till31" -> "till 31"
    (re.compile(r"(?<=\d)(?=[a-z]{3,})"), " "),  # "5seconds" -> "5 seconds" (keeps "10x")
    (re.compile(r"(?<=[?!;:,%])(?=[A-Za-z])"), " "),  # "Questions?Visit", "100%secure"
]


# A number read with letters in it, just before "%": "1oo%" or "1o 0%" is 100%.
_PERCENT = re.compile(r"(?<![\w])(\d[\dOoIl ]{0,4}?)\s?%")
_DIGIT_LOOKALIKES = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", " ": None})


def respace(text: str) -> str:
    """Undo common OCR slips: spaces dropped at letter-digit and punctuation boundaries, and
    the letters o and l read inside a percentage. (Two words glued together, like "onevery",
    are left as read.)"""
    text = _PERCENT.sub(lambda m: m.group(1).translate(_DIGIT_LOOKALIKES) + "%", text)
    for pattern, replacement in _GLUED:
        text = pattern.sub(replacement, text)
    return text


def _same_paragraph(prev: OcrLine, line: OcrLine) -> bool:
    gap = line.y0 - prev.y1
    similar_size = 0.78 < line.height / max(prev.height, 1) < 1.28
    aligned = abs(line.x0 - prev.x0) < 0.6 * max(prev.height, line.height) or (
        line.x0 < prev.x1 and line.x1 > prev.x0
    )
    return -0.3 * prev.height < gap < 0.7 * prev.height and similar_size and aligned


def to_blocks(
    pages: list[tuple[list[OcrLine], int, int]], first_block: int = 0
) -> tuple[list[Block], list[LineBox]]:
    """Group each page's lines into paragraph blocks. Boxes are stored as fractions of the
    page size, so they overlay correctly at any display size."""
    blocks: list[Block] = []
    layout: list[LineBox] = []
    offset = 0
    for page_index, (lines, width, height) in enumerate(pages):
        paragraphs: list[list[OcrLine]] = []
        for line in lines:
            if paragraphs and _same_paragraph(paragraphs[-1][-1], line):
                paragraphs[-1].append(line)
            else:
                paragraphs.append([line])
        for paragraph in paragraphs:
            block_id = first_block + len(blocks)
            parts: list[str] = []
            cursor = 0
            for line in paragraph:
                if parts:
                    cursor += 1  # the joining space
                start = cursor
                parts.append(line.text)
                cursor += len(line.text)
                layout.append(
                    LineBox(
                        block=block_id,
                        start=start,
                        end=cursor,
                        page=page_index,
                        x=line.x0 / width,
                        y=line.y0 / height,
                        w=(line.x1 - line.x0) / width,
                        h=(line.y1 - line.y0) / height,
                    )
                )
            text = " ".join(parts)
            blocks.append(Block(id=block_id, text=text, start_offset=offset))
            offset += len(text) + 2
    return blocks, layout
