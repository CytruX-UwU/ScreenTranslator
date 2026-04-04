"""
后台屏幕翻译：全局快捷键截图 → OCR 定位文字 → 中文译英文 → 半透明悬浮标注 → 全屏展示结果。
默认快捷键：Ctrl+Shift+1 全屏；Ctrl+Shift+2 框选区域。结果窗口按 Esc 关闭。
"""

from __future__ import annotations

import io
import queue
import re
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence, Tuple

import mss
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# -----------------------------------------------------------------------------
# 配置（可改为环境变量或单独配置文件）
# -----------------------------------------------------------------------------

HOTKEY_FULL = "<ctrl>+<shift>+1>"
HOTKEY_REGION = "<ctrl>+<shift>+2>"
OCR_MIN_SCORE = 0.35
FONT_MAX = 22
FONT_MIN = 10


def _has_cjk(s: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", s))


def _iter_ocr_items(ocr_out: Any) -> List[Tuple[Any, str, float]]:
    """将 RapidOCR 不同版本的返回值统一为 [(box, text, score), ...]。"""
    items: List[Tuple[Any, str, float]] = []

    if ocr_out is None:
        return items

    if isinstance(ocr_out, tuple) and len(ocr_out) > 0:
        ocr_out = ocr_out[0]

    # RapidOCROutput: boxes, txts, scores
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

    # 旧版 list: [[box, text, score], ...]
    if isinstance(ocr_out, (list, tuple)):
        for row in ocr_out:
            if not row:
                continue
            if len(row) >= 3:
                items.append((row[0], str(row[1]), float(row[2])))
            elif len(row) == 2:
                items.append((row[0], str(row[1]), 1.0))
    return items


def _box_to_xyxy(box: Any) -> Tuple[int, int, int, int]:
    pts = np.asarray(box, dtype=np.float32).reshape(-1, 2)
    x1, y1 = pts.min(axis=0)
    x2, y2 = pts.max(axis=0)
    return int(x1), int(y1), int(x2), int(y2)


def _pick_font(size: int) -> Any:
    candidates = [
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\msyh.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit_font_for_box(
    draw: ImageDraw.ImageDraw, text: str, x1: int, y1: int, x2: int, y2: int
) -> Any:
    w, h = max(1, x2 - x1), max(1, y2 - y1)
    for size in range(FONT_MAX, FONT_MIN - 1, -1):
        font = _pick_font(size)
        bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=2)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if tw <= w - 4 and th <= h - 4:
            return font
    return _pick_font(FONT_MIN)


def _grab_virtual_screen() -> Tuple[Image.Image, dict]:
    with mss.mss() as sct:
        mon = sct.monitors[0]
        shot = sct.grab(mon)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        return img, dict(mon)


def _grab_region(left: int, top: int, width: int, height: int) -> Image.Image:
    region = {"left": left, "top": top, "width": width, "height": height}
    with mss.mss() as sct:
        shot = sct.grab(region)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def _region_selector(master: tk.Tk) -> Optional[Tuple[int, int, int, int]]:
    """在主线程调用。返回 (left, top, width, height) 屏幕坐标，或取消时 None。"""
    with mss.mss() as sct:
        mon = sct.monitors[0]
    left, top, w, h = mon["left"], mon["top"], mon["width"], mon["height"]

    result: dict = {"bbox": None}

    top = tk.Toplevel(master)
    top.overrideredirect(True)
    top.geometry(f"{w}x{h}+{left}+{top}")
    top.attributes("-topmost", True)
    try:
        top.attributes("-alpha", 0.28)
    except tk.TclError:
        pass
    top.configure(bg="black")

    canvas = tk.Canvas(top, highlightthickness=0, bg="black")
    canvas.pack(fill="both", expand=True)

    state: dict = {"start": None, "rect": None}

    def on_press(e: tk.Event) -> None:
        state["start"] = (e.x_root, e.y_root)
        if state["rect"]:
            canvas.delete(state["rect"])
            state["rect"] = None

    def on_drag(e: tk.Event) -> None:
        if state["start"] is None:
            return
        if state["rect"]:
            canvas.delete(state["rect"])
        x0, y0 = state["start"]
        state["rect"] = canvas.create_rectangle(
            x0 - left,
            y0 - top,
            e.x_root - left,
            e.y_root - top,
            outline="#00ff88",
            width=2,
        )

    def on_release(e: tk.Event) -> None:
        if state["start"] is None:
            return
        x0, y0 = state["start"]
        x1, y1 = e.x_root, e.y_root
        ax, bx = sorted([x0, x1])
        ay, by = sorted([y0, y1])
        if bx - ax < 8 or by - ay < 8:
            result["bbox"] = None
        else:
            result["bbox"] = (ax, ay, bx - ax, by - ay)
        top.destroy()

    def on_esc(_: tk.Event) -> None:
        result["bbox"] = None
        top.destroy()

    canvas.bind("<Button-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    top.bind("<Escape>", on_esc)
    top.focus_force()
    master.wait_window(top)
    return result["bbox"]


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
        if not _has_cjk(t):
            return text
        try:
            return self.translator.translate(t)
        except Exception:
            return text

    def run_ocr(self, rgb: Image.Image) -> List[Tuple[Any, str, float]]:
        arr = np.array(rgb)
        out = self.ocr(arr)
        return _iter_ocr_items(out)

    def annotate(self, rgb: Image.Image, ocr_items: Sequence[Tuple[Any, str, float]]) -> Image.Image:
        base = rgb.convert("RGBA")
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw_o = ImageDraw.Draw(overlay, "RGBA")

        kept: List[Tuple[Tuple[int, int, int, int], str]] = []
        for box, text, score in ocr_items:
            if score < OCR_MIN_SCORE or not text.strip():
                continue
            en = self.translate(text)
            x1, y1, x2, y2 = _box_to_xyxy(box)
            draw_o.rectangle([x1, y1, x2, y2], fill=(15, 18, 24, 175))
            kept.append(((x1, y1, x2, y2), en))

        composed = Image.alpha_composite(base, overlay)
        draw = ImageDraw.Draw(composed, "RGBA")

        for (x1, y1, x2, y2), en in kept:
            if not en.strip():
                continue
            font = _fit_font_for_box(draw, en, x1, y1, x2, y2)
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
            print("正在加载 OCR 模型（首次运行会下载模型，请稍候）…", flush=True)
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
                print(f"截图失败: {e}", flush=True)
                result_queue.put(None)
                return
            try:
                pipe = get_pipeline()
                items = pipe.run_ocr(img)
                if not items:
                    print("未检测到文字。", flush=True)
                out = pipe.annotate(img, items)
            except Exception as e:
                print(f"处理失败: {e}", flush=True)
                result_queue.put(None)
                return
            result_queue.put(out)

    threading.Thread(target=work, daemon=True).start()


def show_result(master: tk.Tk, pil_image: Image.Image) -> None:
    top = tk.Toplevel(master)
    top.title("Screen Translator — Esc 关闭")
    top.attributes("-topmost", True)
    top.attributes("-fullscreen", True)
    top.configure(bg="black")

    max_side = 2400
    w, h = pil_image.size
    disp = pil_image
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        nw, nh = int(w * scale), int(h * scale)
        resample = getattr(Image, "Resampling", Image).LANCZOS
        disp = pil_image.resize((nw, nh), resample)

    bio = io.BytesIO()
    disp.save(bio, format="PNG")
    bio.seek(0)
    from PIL import ImageTk

    photo = ImageTk.PhotoImage(data=bio.read())

    lbl = tk.Label(top, image=photo, bg="black")
    lbl.image = photo  # noqa: keep ref
    lbl.pack(expand=True)

    hint = tk.Label(
        top,
        text="按 Esc 或单击关闭",
        fg="#cccccc",
        bg="black",
        font=("Segoe UI", 12),
    )
    hint.place(relx=0.5, rely=0.02, anchor="n")

    def close(_: Any = None) -> None:
        top.destroy()

    top.bind("<Escape>", close)
    top.bind("<Button-1>", close)
    top.focus_force()


def main() -> None:
    from pynput import keyboard

    event_q: queue.Queue = queue.Queue()
    result_q: queue.Queue[Optional[Image.Image]] = queue.Queue()

    def on_full() -> None:
        event_q.put("full")

    def on_region() -> None:
        event_q.put("region")

    hotkeys = keyboard.GlobalHotKeys(
        {
            HOTKEY_FULL: on_full,
            HOTKEY_REGION: on_region,
        }
    )

    print("屏幕翻译已在后台运行。")
    print(f"  {HOTKEY_FULL} — 截取整个虚拟桌面并翻译")
    print(f"  {HOTKEY_REGION} — 框选区域后翻译（拖拽选区，Esc 取消）")
    print("关闭此终端或 Ctrl+C 结束进程。")

    hotkeys.start()

    root = tk.Tk()
    root.withdraw()

    def pump() -> None:
        try:
            while True:
                done = result_q.get_nowait()
                if done is not None:
                    show_result(root, done)
        except queue.Empty:
            pass

        try:
            kind = event_q.get(timeout=0.15)
        except queue.Empty:
            root.after(40, pump)
            return

        if kind == "full":

            def cap() -> Image.Image:
                img, _ = _grab_virtual_screen()
                return img

            process_and_show(cap, result_q)
        elif kind == "region":
            bbox = _region_selector(root)
            if bbox is not None:
                l, t, w, h = bbox

                def cap2() -> Image.Image:
                    return _grab_region(l, t, w, h)

                process_and_show(cap2, result_q)

        root.after(40, pump)

    root.after(100, pump)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        hotkeys.stop()


if __name__ == "__main__":
    main()
