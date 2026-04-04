"""Fullscreen display of the translated overlay image. 全屏展示带翻译叠加层的结果图。"""

import io
from typing import Any

import tkinter as tk
from PIL import Image, ImageTk


def show_result(master: tk.Tk, pil_image: Image.Image) -> None:
    top = tk.Toplevel(master)
    top.title("Screen Translator — press Esc to close")
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
    photo = ImageTk.PhotoImage(data=bio.read())

    lbl = tk.Label(top, image=photo, bg="black")
    lbl.image = photo  # noqa: keep ref — prevent GC / 防止被回收
    lbl.pack(expand=True)

    hint = tk.Label(
        top,
        text="Press Esc or click to close",
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
