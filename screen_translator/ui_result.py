"""Translated overlay result window: compact “processing” state, then image view. 结果窗口：处理中紧凑提示，完成后图片展示。"""

from typing import Any, Dict, Optional

import tkinter as tk
from PIL import Image, ImageTk

# --- Result window (Tk): titles, copy, colors, fonts, layout ---
# 结果窗口：标题、文案、颜色、字体、布局常量。

TITLE_PENDING = "Screen Translator — Processing"
TITLE_RESULT = "Screen Translator — result"

TEXT_PENDING_PRIMARY = "Processing…"
TEXT_PENDING_SECONDARY = "Translating and building overlay."
TEXT_RESULT_HINT = "Double-click: fullscreen / windowed   ·   Esc: close"

COLOR_BG_PENDING = "#1a1d24"
COLOR_FG_PENDING_PRIMARY = "#e6edf3"
COLOR_FG_PENDING_SECONDARY = "#8b949e"

COLOR_BG_RESULT = "#000000"
COLOR_FG_RESULT_HINT = "#c8c8c8"
# Hint strip overlaid on top of the image (does not reduce canvas area). 叠在图片上方，不占画布高度。
COLOR_BG_RESULT_HINT = "#252525"
RESULT_HINT_TOP_OFFSET = 10

FONT_FAMILY = "Segoe UI"
FONT_PENDING_PRIMARY = (FONT_FAMILY, 14)
FONT_PENDING_SECONDARY = (FONT_FAMILY, 10)
FONT_RESULT_HINT = (FONT_FAMILY, 10)

PENDING_WINDOW_W = 400
PENDING_WINDOW_H = 130
PENDING_PAD_X = 24
PENDING_PAD_Y = 20
PENDING_SECONDARY_PAD_Y = 8

RESULT_IMAGE_MAX_SIDE = 2400
RESULT_RESIZE_DEBOUNCE_MS = 80

# Semi-transparent box behind translated English on the screenshot overlay (RGBA); also used in pipeline.draw.
# 截图上译文背后的半透明底（RGBA）；pipeline 绘制叠加层时复用。alpha 约 80%。
OVERLAY_TRANSLATION_BG_RGBA = (15, 18, 24, int(round(255 * 0.9)))

_result_win: Optional[tk.Toplevel] = None


def _center_window(win: tk.Toplevel, w: int, h: int) -> None:
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")


def _clear_result_children() -> None:
    top = _result_win
    if top is None:
        return
    try:
        for w in top.winfo_children():
            w.destroy()
    except tk.TclError:
        pass


def close_result_window() -> None:
    """Close the result Toplevel if it exists (e.g. job failed). 任务失败等情况下关闭结果窗口。"""
    global _result_win
    top = _result_win
    if top is None:
        return
    try:
        top.destroy()
    except tk.TclError:
        pass
    _result_win = None


def open_result_pending(master: tk.Tk) -> None:
    """
    Compact (minimal) floating window with a visible “processing” message.
    Shown when translation is about to start (after OCR). OCR 完成后、翻译开始前显示紧凑处理中提示。
    """
    global _result_win
    top = _result_win
    if top is not None:
        try:
            if not top.winfo_exists():
                _result_win = None
                top = None
        except tk.TclError:
            _result_win = None
            top = None

    if _result_win is None:
        top = tk.Toplevel(master)
        _result_win = top
    else:
        top = _result_win
        _clear_result_children()

    top.title(TITLE_PENDING)
    top.configure(bg=COLOR_BG_PENDING)
    try:
        top.overrideredirect(False)
    except tk.TclError:
        pass
    top.attributes("-topmost", True)
    top.resizable(False, False)
    try:
        top.state("normal")
    except tk.TclError:
        pass

    fr = tk.Frame(top, bg=COLOR_BG_PENDING)
    fr.pack(fill="both", expand=True, padx=PENDING_PAD_X, pady=PENDING_PAD_Y)
    tk.Label(
        fr,
        text=TEXT_PENDING_PRIMARY,
        fg=COLOR_FG_PENDING_PRIMARY,
        bg=COLOR_BG_PENDING,
        font=FONT_PENDING_PRIMARY,
    ).pack()
    tk.Label(
        fr,
        text=TEXT_PENDING_SECONDARY,
        fg=COLOR_FG_PENDING_SECONDARY,
        bg=COLOR_BG_PENDING,
        font=FONT_PENDING_SECONDARY,
    ).pack(pady=(PENDING_SECONDARY_PAD_Y, 0))

    _center_window(top, PENDING_WINDOW_W, PENDING_WINDOW_H)

    def _on_close() -> None:
        close_result_window()

    top.protocol("WM_DELETE_WINDOW", _on_close)
    top.bind("<Escape>", lambda e: _on_close())
    top.focus_force()


def show_result_image(master: tk.Tk, pil_image: Image.Image) -> None:
    """
    Normal decorated window; opens fullscreen by default; double-click toggles fullscreen / windowed.
    Image is only scaled down to fit the view; smaller images are not upscaled.
    普通窗口，默认全屏；双击全屏/窗口。仅当图大于可视区域时缩小适配，小图不放大。
    """
    global _result_win
    top = _result_win
    if top is not None:
        try:
            if not top.winfo_exists():
                top = None
                _result_win = None
        except tk.TclError:
            top = None
            _result_win = None
    if top is None:
        top = tk.Toplevel(master)
        _result_win = top

    _clear_result_children()

    top.title(TITLE_RESULT)
    top.configure(bg=COLOR_BG_RESULT)
    try:
        top.overrideredirect(False)
    except tk.TclError:
        pass
    top.attributes("-topmost", False)
    top.resizable(True, True)

    source = pil_image.convert("RGB")
    sw0, sh0 = source.size
    if max(sw0, sh0) > RESULT_IMAGE_MAX_SIDE:
        r = RESULT_IMAGE_MAX_SIDE / max(sw0, sh0)
        resample = getattr(Image, "Resampling", Image).LANCZOS
        source = source.resize((int(sw0 * r), int(sh0 * r)), resample)

    state: Dict[str, Any] = {
        "source": source,
        "photo": None,
        "after_id": None,
    }

    body = tk.Frame(top, bg=COLOR_BG_RESULT)
    body.pack(fill=tk.BOTH, expand=True)

    canvas = tk.Canvas(
        body,
        bg=COLOR_BG_RESULT,
        highlightthickness=0,
        borderwidth=0,
    )
    canvas.pack(fill=tk.BOTH, expand=True)

    hint = tk.Label(
        body,
        text=TEXT_RESULT_HINT,
        fg=COLOR_FG_RESULT_HINT,
        bg=COLOR_BG_RESULT_HINT,
        font=FONT_RESULT_HINT,
        padx=12,
        pady=5,
    )
    hint.place(relx=0.5, y=RESULT_HINT_TOP_OFFSET, anchor="n")
    hint.lift()

    def redraw() -> None:
        canvas.update_idletasks()
        cw = max(canvas.winfo_width(), 2)
        ch = max(canvas.winfo_height(), 2)
        iw, ih = state["source"].size
        if iw < 1 or ih < 1:
            return
        # Only shrink to fit; never upscale small images. 只缩小以适配，小图不放大。
        scale = min(1.0, cw / iw, ch / ih)
        nw = max(1, int(round(iw * scale)))
        nh = max(1, int(round(ih * scale)))
        resample = getattr(Image, "Resampling", Image).LANCZOS
        disp = state["source"].resize((nw, nh), resample)
        state["photo"] = ImageTk.PhotoImage(disp)
        canvas.delete("all")
        canvas.create_image(cw // 2, ch // 2, image=state["photo"], anchor=tk.CENTER)

    def schedule_redraw(_event: Any = None) -> None:
        aid = state["after_id"]
        if aid is not None:
            try:
                top.after_cancel(aid)
            except Exception:
                pass
            state["after_id"] = None

        def _run() -> None:
            state["after_id"] = None
            redraw()

        state["after_id"] = top.after(RESULT_RESIZE_DEBOUNCE_MS, _run)

    def toggle_fullscreen(_event: Any = None) -> None:
        fs = bool(top.attributes("-fullscreen"))
        try:
            top.attributes("-fullscreen", not fs)
        except tk.TclError:
            return
        top.after(120, redraw)

    canvas.bind("<Configure>", schedule_redraw)
    canvas.bind("<Double-Button-1>", toggle_fullscreen)
    hint.bind("<Double-Button-1>", toggle_fullscreen)

    def _on_close() -> None:
        try:
            top.attributes("-fullscreen", False)
        except tk.TclError:
            pass
        close_result_window()

    top.protocol("WM_DELETE_WINDOW", _on_close)
    top.bind("<Escape>", lambda e: _on_close())

    # Default: fullscreen; double-click still toggles fullscreen / windowed.
    # 默认全屏；双击仍可全屏/窗口切换。
    try:
        top.attributes("-fullscreen", True)
    except tk.TclError:
        try:
            top.state("zoomed")
        except tk.TclError:
            sw = top.winfo_screenwidth()
            sh = top.winfo_screenheight()
            top.geometry(f"{int(sw * 0.92)}x{int(sh * 0.88)}+{int(sw * 0.04)}+{int(sh * 0.06)}")

    top.update_idletasks()
    top.after(50, redraw)
    top.focus_force()
