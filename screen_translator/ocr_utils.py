"""Normalize OCR outputs and box geometry helpers. 统一 OCR 输出格式与框几何工具。"""

import re
from typing import Any, List, Tuple

import numpy as np


def has_cjk(s: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", s))


def iter_ocr_items(ocr_out: Any) -> List[Tuple[Any, str, float]]:
    """
    Normalize RapidOCR return values to [(box, text, score), ...].
    将 RapidOCR 不同版本的返回值统一为 [(box, text, score), ...]。
    """
    items: List[Tuple[Any, str, float]] = []

    if ocr_out is None:
        return items

    if isinstance(ocr_out, tuple) and len(ocr_out) > 0:
        ocr_out = ocr_out[0]

    if hasattr(ocr_out, "boxes") and hasattr(ocr_out, "txts"):
        boxes = getattr(ocr_out, "boxes", None)
        txts = getattr(ocr_out, "txts", None)
        scores = getattr(ocr_out, "scores", None)
        if boxes is None or txts is None:
            return items
        n = len(txts)
        if scores is None:
            scores = [1.0] * n
        for i in range(n):
            box = np.array(boxes[i]) if not isinstance(boxes[i], np.ndarray) else boxes[i]
            t = str(txts[i])
            sc = float(scores[i]) if i < len(scores) else 1.0
            items.append((box, t, sc))
        return items

    if isinstance(ocr_out, (list, tuple)):
        for row in ocr_out:
            if not row:
                continue
            if len(row) >= 3:
                items.append((row[0], str(row[1]), float(row[2])))
            elif len(row) == 2:
                items.append((row[0], str(row[1]), 1.0))
    return items


def box_to_xyxy(box: Any) -> Tuple[int, int, int, int]:
    pts = np.asarray(box, dtype=np.float32).reshape(-1, 2)
    x1, y1 = pts.min(axis=0)
    x2, y2 = pts.max(axis=0)
    return int(x1), int(y1), int(x2), int(y2)
