"""
Entry: global hotkeys, capture / region, OCR and translation, result view, tray.
入口：全局快捷键、截图/选区、OCR 与翻译、结果展示、托盘。

PyInstaller: prefer --windowed/--noconsole; use --collect-all pystray if tray assets are missing.
打包：无控制台用 --windowed/--noconsole；托盘资源缺失时可加 --collect-all pystray。
"""

from __future__ import annotations

import queue
import sys
from typing import Optional

import tkinter as tk
from PIL import Image

from screen_translator.capture import grab_region, grab_virtual_screen
from screen_translator.config import HOTKEY_FULL, HOTKEY_REGION
from screen_translator.hotkeys import GlobalHotKeys
from screen_translator.pipeline import process_and_show
from screen_translator.tray import start_tray
from screen_translator.ui_region import region_selector
from screen_translator.ui_result import show_result


def _startup_messages(hotkeys: GlobalHotKeys) -> None:
    if sys.stdout is None:
        return
    lines = [
        "Screen Translator is running in the background (use the tray icon to exit).",
        f"  {HOTKEY_FULL} — capture the full virtual desktop and translate",
        f"  {HOTKEY_REGION} — drag a region, then translate (Esc cancels)",
        f"Hotkey backend: {hotkeys.backend} (win32=native RegisterHotKey, pynput=fallback)",
        "Exit: close this terminal, Ctrl+C, or tray Exit.",
    ]
    try:
        for line in lines:
            print(line, flush=True)
    except OSError:
        pass


def main() -> None:
    event_q: queue.Queue = queue.Queue()
    result_q: queue.Queue[Optional[Image.Image]] = queue.Queue()

    def on_full() -> None:
        event_q.put("full")

    def on_region() -> None:
        event_q.put("region")

    hotkeys = GlobalHotKeys(
        {
            HOTKEY_FULL: on_full,
            HOTKEY_REGION: on_region,
        }
    )
    hotkeys.start()
    _startup_messages(hotkeys)

    root = tk.Tk()
    root.withdraw()

    tray_icon = start_tray(root, hotkeys)

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
                img, _ = grab_virtual_screen()
                return img

            process_and_show(cap, result_q)
        elif kind == "region":
            bbox = region_selector(root)
            if bbox is not None:
                l, t, w, h = bbox

                def cap2() -> Image.Image:
                    return grab_region(l, t, w, h)

                process_and_show(cap2, result_q)

        root.after(40, pump)

    root.after(100, pump)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        hotkeys.stop()
        try:
            tray_icon.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
