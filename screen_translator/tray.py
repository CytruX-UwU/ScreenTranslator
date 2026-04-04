"""系统托盘（pystray），与 tk 主线程通过 root.after 协调退出。"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import pystray
from PIL import Image, ImageDraw

if TYPE_CHECKING:
    import tkinter as tk

    from screen_translator.hotkeys import GlobalHotKeys


def _tray_image() -> Image.Image:
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((4, 4, 60, 60), radius=12, fill=(52, 120, 220, 255))
    d.rounded_rectangle((12, 18, 52, 46), radius=6, fill=(230, 240, 255, 255))
    return im


def start_tray(root: "tk.Tk", hotkeys: "GlobalHotKeys", tooltip: str = "屏幕翻译") -> pystray.Icon:
    """
    在后台线程中运行托盘图标；返回 Icon 供 finally 中 stop，或供异常路径清理。
    退出菜单项会在 tk 主线程上调用 hotkeys.stop()、icon.stop()、root.quit()。
    """
    image = _tray_image()

    def on_quit(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        root.after(0, lambda: _shutdown_from_tray(icon, root, hotkeys))

    menu = pystray.Menu(
        pystray.MenuItem("退出", on_quit),
    )
    icon = pystray.Icon("screen_translator", image, tooltip, menu)

    def run_loop() -> None:
        icon.run()

    threading.Thread(target=run_loop, name="pystray-tray", daemon=True).start()
    return icon


def _shutdown_from_tray(icon: pystray.Icon, root: "tk.Tk", hotkeys: "GlobalHotKeys") -> None:
    try:
        hotkeys.stop()
    finally:
        try:
            icon.stop()
        except Exception:
            pass
        root.quit()
