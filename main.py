"""
入口：全局快捷键 → 截图 / 框选 → OCR 与翻译流水线 → 结果展示；系统托盘常驻。

打包建议（PyInstaller）：对无窗程序使用 --windowed/--noconsole，并视情况
--collect-all pystray，避免托盘资源遗漏。详见项目说明或下方注释。
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
        "屏幕翻译已在后台运行（托盘图标可退出）。",
        f"  {HOTKEY_FULL} — 截取整个虚拟桌面并翻译",
        f"  {HOTKEY_REGION} — 框选区域后翻译（拖拽选区，Esc 取消）",
        f"热键后端: {hotkeys.backend}（win32=系统注册，pynput=兼容回退）",
        "关闭此终端、Ctrl+C 或托盘「退出」结束进程。",
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
