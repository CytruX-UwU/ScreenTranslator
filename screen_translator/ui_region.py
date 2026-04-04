"""全屏半透明框选区域。"""

from typing import Optional, Tuple

import mss
import tkinter as tk


def region_selector(master: tk.Tk) -> Optional[Tuple[int, int, int, int]]:
    """在主线程调用。返回 (left, top, width, height) 屏幕坐标，或取消时 None。"""
    with mss.mss() as sct:
        mon = sct.monitors[0]
    mon_left, mon_top, w, h = mon["left"], mon["top"], mon["width"], mon["height"]

    result: dict = {"bbox": None}

    win = tk.Toplevel(master)
    win.overrideredirect(True)
    win.geometry(f"{w}x{h}+{mon_left}+{mon_top}")
    win.attributes("-topmost", True)
    try:
        win.attributes("-alpha", 0.28)
    except tk.TclError:
        pass
    win.configure(bg="black")

    canvas = tk.Canvas(win, highlightthickness=0, bg="black")
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
            x0 - mon_left,
            y0 - mon_top,
            e.x_root - mon_left,
            e.y_root - mon_top,
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
        win.destroy()

    def on_esc(_: tk.Event) -> None:
        result["bbox"] = None
        win.destroy()

    canvas.bind("<Button-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    win.bind("<Escape>", on_esc)
    win.focus_force()
    master.wait_window(win)
    return result["bbox"]
