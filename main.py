"""
入口：全局快捷键 → 截图 / 框选 → OCR 与翻译流水线 → 结果展示。
"""

from __future__ import annotations

import queue
from typing import Optional

import tkinter as tk
from PIL import Image

from screen_translator.capture import grab_region, grab_virtual_screen
from screen_translator.config import HOTKEY_FULL, HOTKEY_REGION
from screen_translator.pipeline import process_and_show
from screen_translator.ui_region import region_selector
from screen_translator.ui_result import show_result


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


if __name__ == "__main__":
    main()
