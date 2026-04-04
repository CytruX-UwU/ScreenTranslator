"""OCR, translation, overlay rendering, and background job scheduling. OCR、翻译、叠加绘制与后台任务调度。"""

import queue
import threading
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw

from screen_translator.config import OCR_MIN_SCORE
from screen_translator.ocr_utils import box_to_xyxy, has_cjk, iter_ocr_items
from screen_translator.render import fit_font_for_box


@dataclass
class Pipeline:
    ocr: Any
    translator: Any

    @classmethod
    def create(cls) -> "Pipeline":
        from rapidocr_onnxruntime import RapidOCR
        from deep_translator import GoogleTranslator

        ocr = RapidOCR()
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
        arr = np.array(rgb)
        out = self.ocr(arr)
        return iter_ocr_items(out)

    def annotate(self, rgb: Image.Image, ocr_items: Sequence[Tuple[Any, str, float]]) -> Image.Image:
        base = rgb.convert("RGBA")
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw_o = ImageDraw.Draw(overlay, "RGBA")

        kept: List[Tuple[Tuple[int, int, int, int], str]] = []
        for box, text, score in ocr_items:
            if score < OCR_MIN_SCORE or not text.strip():
                continue
            en = self.translate(text)
            x1, y1, x2, y2 = box_to_xyxy(box)
            draw_o.rectangle([x1, y1, x2, y2], fill=(15, 18, 24, 175))
            kept.append(((x1, y1, x2, y2), en))

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
            print("Loading OCR model (first run may download files)…", flush=True)
            _pipeline = Pipeline.create()
        return _pipeline


def process_and_show(
    capture: Callable[[], Image.Image], result_queue: "queue.Queue[Optional[Image.Image]]"
) -> None:
    def work() -> None:
        with _ocr_task_lock:
            try:
                img = capture()
            except Exception as e:
                print(f"Capture failed: {e}", flush=True)
                result_queue.put(None)
                return
            try:
                pipe = get_pipeline()
                items = pipe.run_ocr(img)
                if not items:
                    print("No text detected.", flush=True)
                out = pipe.annotate(img, items)
            except Exception as e:
                print(f"Processing failed: {e}", flush=True)
                result_queue.put(None)
                return
            result_queue.put(out)

    threading.Thread(target=work, daemon=True).start()
