"""OCR, translation, overlay rendering, and background job scheduling. OCR、翻译、叠加绘制与后台任务调度。"""

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw

from screen_translator.config import (
    OCR_DET_LIMIT_SIDE_LEN,
    OCR_INTER_OP_NUM_THREADS,
    OCR_INTRA_OP_NUM_THREADS,
    OCR_MAX_SIDE_LEN,
    OCR_MIN_SCORE,
    OCR_USE_CLS,
    OCR_USE_CUDA,
    OCR_USE_DML,
)
from screen_translator.ocr_utils import box_to_xyxy, has_cjk, iter_ocr_items
from screen_translator.ort_ep import resolve_ocr_ep_flags
from screen_translator.render import fit_font_for_box

logger = logging.getLogger(__name__)


@dataclass
class Pipeline:
    ocr: Any
    translator: Any

    @classmethod
    def create(cls) -> "Pipeline":
        from rapidocr_onnxruntime import RapidOCR
        from deep_translator import GoogleTranslator

        use_cuda, use_dml = resolve_ocr_ep_flags(OCR_USE_CUDA, OCR_USE_DML)
        ocr = RapidOCR(
            use_cls=OCR_USE_CLS,
            max_side_len=OCR_MAX_SIDE_LEN,
            det_limit_side_len=OCR_DET_LIMIT_SIDE_LEN,
            intra_op_num_threads=OCR_INTRA_OP_NUM_THREADS,
            inter_op_num_threads=OCR_INTER_OP_NUM_THREADS,
            det_use_cuda=use_cuda,
            cls_use_cuda=use_cuda,
            rec_use_cuda=use_cuda,
            det_use_dml=use_dml,
            cls_use_dml=use_dml,
            rec_use_dml=use_dml,
        )
        translator = GoogleTranslator(source="zh-CN", target="en")
        return cls(ocr=ocr, translator=translator)

    def translate(self, text: str) -> str:
        t = text.strip()
        if not t:
            return text
        if not has_cjk(t):
            return text
        try:
            return self.translator.translate(t)
        except Exception:
            return text

    def run_ocr(self, rgb: Image.Image) -> List[Tuple[Any, str, float]]:
        logger.info("OCR starting (image size %dx%d)", rgb.size[0], rgb.size[1])
        t0 = time.perf_counter()
        arr = np.array(rgb)
        out = self.ocr(arr)
        items = iter_ocr_items(out)
        ms = (time.perf_counter() - t0) * 1000.0
        logger.info("OCR finished in %.1f ms (%d region(s))", ms, len(items))
        return items

    def annotate(self, rgb: Image.Image, ocr_items: Sequence[Tuple[Any, str, float]]) -> Image.Image:
        base = rgb.convert("RGBA")
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw_o = ImageDraw.Draw(overlay, "RGBA")

        kept: List[Tuple[Tuple[int, int, int, int], str]] = []
        if not ocr_items:
            logger.info("Translation skipped (no OCR regions).")
        else:
            logger.info("Translation starting (%d region(s) from OCR)", len(ocr_items))
            n_tr = 0
            translate_s = 0.0
            for box, text, score in ocr_items:
                if score < OCR_MIN_SCORE or not text.strip():
                    continue
                t_one = time.perf_counter()
                en = self.translate(text)
                translate_s += time.perf_counter() - t_one
                n_tr += 1
                x1, y1, x2, y2 = box_to_xyxy(box)
                draw_o.rectangle([x1, y1, x2, y2], fill=(15, 18, 24, 175))
                kept.append(((x1, y1, x2, y2), en))
            logger.info(
                "Translation finished in %.1f ms (%d string(s); score/text filtered excluded)",
                translate_s * 1000.0,
                n_tr,
            )

        composed = Image.alpha_composite(base, overlay)
        draw = ImageDraw.Draw(composed, "RGBA")

        for (x1, y1, x2, y2), en in kept:
            if not en.strip():
                continue
            font = fit_font_for_box(draw, en, x1, y1, x2, y2)
            tw, th = x2 - x1, y2 - y1
            bbox = draw.multiline_textbbox((0, 0), en, font=font, spacing=2)
            twt, tht = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tx = x1 + max(2, (tw - twt) // 2)
            ty = y1 + max(2, (th - tht) // 2)
            draw.text((tx + 1, ty + 1), en, fill=(0, 0, 0, 220), font=font, spacing=2)
            draw.text((tx, ty), en, fill=(240, 248, 255, 255), font=font, spacing=2)

        return composed.convert("RGB")


_pipeline: Optional[Pipeline] = None
_pipeline_lock = threading.Lock()
_ocr_task_lock = threading.Lock()


def get_pipeline() -> Pipeline:
    global _pipeline
    with _pipeline_lock:
        if _pipeline is None:
            logger.info("Loading OCR model (first run may download files)…")
            _pipeline = Pipeline.create()
        return _pipeline


def process_and_show(
    capture: Callable[[], Image.Image], result_queue: "queue.Queue[Optional[Image.Image]]"
) -> None:
    def work() -> None:
        with _ocr_task_lock:
            try:
                t_cap = time.perf_counter()
                img = capture()
                ms_cap = (time.perf_counter() - t_cap) * 1000.0
                logger.info(
                    "Screenshot done in %.1f ms (image %dx%d)",
                    ms_cap,
                    img.size[0],
                    img.size[1],
                )
            except Exception as e:
                logger.exception("Capture failed: %s", e)
                result_queue.put(None)
                return
            try:
                pipe = get_pipeline()
                items = pipe.run_ocr(img)
                if not items:
                    logger.info("No text detected after OCR.")
                out = pipe.annotate(img, items)
            except Exception as e:
                logger.exception("Processing failed: %s", e)
                result_queue.put(None)
                return
            result_queue.put(out)

    threading.Thread(target=work, daemon=True).start()
