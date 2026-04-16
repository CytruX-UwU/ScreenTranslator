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
    TRANSLATE_BATCH_DELIM,
    TRANSLATE_BATCH_MAX_CHARS,
)
from screen_translator.ui_result import OVERLAY_TRANSLATION_BG_RGBA
from screen_translator.ocr_utils import box_to_xyxy, has_cjk, iter_ocr_items
from screen_translator.ort_ep import resolve_ocr_ep_flags
from screen_translator.render import (
    OVERLAY_MULTILINE_SPACING,
    fit_font_for_box,
    line_height_px,
    wrap_text_to_width,
)

logger = logging.getLogger(__name__)


def _pack_cjk_texts_into_batches(
    texts: List[str], max_chars: int, delim: str
) -> List[List[str]]:
    """Pack consecutive CJK strings into batches; each batch joined length ≤ max_chars (incl. delimiters)."""
    if not texts:
        return []
    batches: List[List[str]] = []
    cur: List[str] = []
    cur_len = 0
    dlen = len(delim)
    for t in texts:
        if len(t) > max_chars:
            if cur:
                batches.append(cur)
                cur = []
                cur_len = 0
            batches.append([t])
            continue
        overhead = dlen if cur else 0
        piece = overhead + len(t)
        if cur and cur_len + piece > max_chars:
            batches.append(cur)
            cur = [t]
            cur_len = len(t)
        else:
            if not cur:
                cur = [t]
                cur_len = len(t)
            else:
                cur.append(t)
                cur_len += piece
    if cur:
        batches.append(cur)
    return batches


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

    def _translate_one_api(self, text: str) -> str:
        """Single HTTP translate; `text` must be non-empty CJK when called."""
        try:
            return self.translator.translate(text)
        except Exception:
            return text

    def _translate_merged_batch(self, batch: List[str], delim: str) -> List[str]:
        """One API call for multiple segments; split back or fall back to per-string."""
        if len(batch) == 1:
            return [self._translate_one_api(batch[0])]
        joined = delim.join(batch)
        try:
            out = self.translator.translate(joined)
        except Exception:
            return [self._translate_one_api(t) for t in batch]
        parts = out.split(delim)
        if len(parts) == len(batch):
            return parts
        logger.warning(
            "Merged translation split mismatch: expected %d segment(s), got %d; "
            "falling back to per-string translation.",
            len(batch),
            len(parts),
        )
        return [self._translate_one_api(t) for t in batch]

    def translate_cjk_strings_batched(
        self, texts: List[str], max_chars: int, delim: str
    ) -> Tuple[List[str], int]:
        """
        Translate a list of CJK strings with minimal HTTP calls.
        Returns (translations in same order, number of HTTP requests).
        """
        if not texts:
            return [], 0
        batches = _pack_cjk_texts_into_batches(texts, max_chars, delim)
        out: List[str] = []
        n_http = 0
        for batch in batches:
            n_http += 1
            out.extend(self._translate_merged_batch(batch, delim))
        if len(out) != len(texts):
            logger.warning(
                "Batch translation length mismatch: expected %d, got %d; padding with originals.",
                len(texts),
                len(out),
            )
            while len(out) < len(texts):
                out.append(texts[len(out)])
            out = out[: len(texts)]
        return out, n_http

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
            entries: List[Tuple[Any, str]] = []
            for box, text, score in ocr_items:
                if score < OCR_MIN_SCORE or not text.strip():
                    continue
                entries.append((box, text))

            if not entries:
                logger.info("Translation skipped (no regions after score filter).")
            else:
                logger.info("Translation starting (%d region(s) from OCR)", len(entries))
                t_tr0 = time.perf_counter()
                cjk_texts: List[str] = []
                cjk_index: List[int] = []
                for i, (_, text) in enumerate(entries):
                    t = text.strip()
                    if has_cjk(t):
                        cjk_texts.append(t)
                        cjk_index.append(i)
                ens: List[str] = [""] * len(entries)
                for i, (_, text) in enumerate(entries):
                    t = text.strip()
                    if not has_cjk(t):
                        ens[i] = text
                n_http = 0
                if cjk_texts:
                    translated, n_http = self.translate_cjk_strings_batched(
                        cjk_texts,
                        TRANSLATE_BATCH_MAX_CHARS,
                        TRANSLATE_BATCH_DELIM,
                    )
                    for j, ti in enumerate(cjk_index):
                        ens[ti] = translated[j]
                translate_s = time.perf_counter() - t_tr0
                n_tr = len(entries)
                for i, (box, _) in enumerate(entries):
                    en = ens[i]
                    x1, y1, x2, y2 = box_to_xyxy(box)
                    draw_o.rectangle([x1, y1, x2, y2], fill=OVERLAY_TRANSLATION_BG_RGBA)
                    kept.append(((x1, y1, x2, y2), en))
                logger.info(
                    "Translation finished in %.1f ms (%d string(s), %d HTTP request(s) for %d CJK string(s); "
                    "batch max %d chars per request",
                    translate_s * 1000.0,
                    n_tr,
                    n_http,
                    len(cjk_texts),
                    TRANSLATE_BATCH_MAX_CHARS,
                )

        composed = Image.alpha_composite(base, overlay)
        draw = ImageDraw.Draw(composed, "RGBA")
        img_w, img_h = composed.size
        margin = 2

        for (x1, y1, x2, y2), en in kept:
            if not en.strip():
                continue
            font = fit_font_for_box(draw, en, x1, y1, x2, y2)
            tw, th = x2 - x1, y2 - y1
            text = en.strip()
            bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=OVERLAY_MULTILINE_SPACING)
            twt, tht = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tx = x1 + max(2, (tw - twt) // 2)
            ty = y1 + max(2, (th - tht) // 2)

            if (
                tx < margin
                or ty < margin
                or tx + twt > img_w - margin
                or ty + tht > img_h - margin
            ):
                max_w = max(1, img_w - tx - margin)
                text = wrap_text_to_width(draw, text, font, max_w)
                bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=OVERLAY_MULTILINE_SPACING)
                twt, tht = bbox[2] - bbox[0], bbox[3] - bbox[1]
                tx = x1 + max(2, (tw - twt) // 2)
                ty = y1 + max(2, (th - tht) // 2)
                ty = max(margin, ty - line_height_px(draw, font, spacing=OVERLAY_MULTILINE_SPACING) // 2)

            draw.text(
                (tx + 1, ty + 1),
                text,
                fill=(0, 0, 0, 220),
                font=font,
                spacing=OVERLAY_MULTILINE_SPACING,
            )
            draw.text(
                (tx, ty),
                text,
                fill=(240, 248, 255, 255),
                font=font,
                spacing=OVERLAY_MULTILINE_SPACING,
            )

        return composed.convert("RGB")


_pipeline: Optional[Pipeline] = None
_pipeline_lock = threading.Lock()
_ocr_task_lock = threading.Lock()

# Queued before annotate() so the UI can show “processing” during translation + overlay draw.
# 在 annotate（翻译与绘制）之前入队，供 UI 显示处理中。
RESULT_EVENT_PROCESSING = object()


def get_pipeline() -> Pipeline:
    global _pipeline
    with _pipeline_lock:
        if _pipeline is None:
            logger.info("Loading OCR model (first run may download files)…")
            _pipeline = Pipeline.create()
        return _pipeline


def process_and_show(
    capture: Callable[[], Image.Image],
    result_queue: "queue.Queue[Optional[object]]",
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
                result_queue.put(RESULT_EVENT_PROCESSING)
                out = pipe.annotate(img, items)
            except Exception as e:
                logger.exception("Processing failed: %s", e)
                result_queue.put(None)
                return
            result_queue.put(out)

    threading.Thread(target=work, daemon=True).start()
