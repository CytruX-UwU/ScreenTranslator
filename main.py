"""
Entry: global hotkeys, capture / region, OCR and translation, result view, tray.
入口：全局快捷键、截图/选区、OCR 与翻译、结果展示、托盘。

PyInstaller: prefer --windowed/--noconsole; use --collect-all pystray if tray assets are missing.
打包：无控制台用 --windowed/--noconsole；托盘资源缺失时可加 --collect-all pystray。
"""

from __future__ import annotations

from dataclasses import replace

import logging
import queue
import sys
import tkinter as tk
from PIL import Image

from screen_translator.capture import grab_region, grab_virtual_screen
from screen_translator.console_fmt import green as console_green
from screen_translator.console_fmt import red as console_red
from screen_translator.config import HOTKEY_FULL, HOTKEY_REGION
from screen_translator.hotkeys import GlobalHotKeys
from screen_translator.pipeline import RESULT_EVENT_PROCESSING, process_and_show
from screen_translator.settings import Settings, load_settings, save_settings
from screen_translator.remote_startup import schedule_startup_remote
from screen_translator.tray import start_tray
from screen_translator.ui_region import region_selector
from screen_translator.ui_result import close_result_window, open_result_pending, show_result_image


def _startup_messages(hotkeys: GlobalHotKeys, *, hotkeys_enabled: bool) -> None:
    if sys.stdout is None:
        return
    lines = [
        "Screen Translator is running in the background (use the tray icon to exit).",
        console_green("Tip: right-click the tray icon to change settings (e.g. select which monitor to capture for fullscreen)."),
        f"  {HOTKEY_FULL} — capture the full screen and translate",
        f"  {HOTKEY_REGION} — drag a region, then translate (Esc cancels)",
        f"Hotkey backend: {hotkeys.backend}",
        "Exit: close this terminal, Ctrl+C, or tray Exit.",
    ]
    if not hotkeys_enabled:
        lines.insert(2, console_red("  (Hotkeys disabled: failed to register; another app may be using them.)"))
    try:
        for line in lines:
            print(line, flush=True)
    except OSError:
        pass


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    event_q: queue.Queue = queue.Queue()
    result_q: queue.Queue = queue.Queue()  # None | RESULT_EVENT_PROCESSING | (PIL.Image, ocr_regions)

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
    hotkeys_enabled = True
    try:
        hotkeys.start()
    except RuntimeError as e:
        hotkeys_enabled = False
        print(f"Hotkeys: {e}", file=sys.stderr)
    _startup_messages(hotkeys, hotkeys_enabled=hotkeys_enabled)

    root = tk.Tk()
    root.withdraw()

    schedule_startup_remote(root)

    settings = load_settings()
    settings_state: dict = {"settings": settings}

    def get_selected_monitor() -> int:
        return int(settings_state["settings"].selected_monitor)

    def set_selected_monitor(idx: int) -> None:
        s = settings_state["settings"]
        ns = replace(s, selected_monitor=int(idx))
        settings_state["settings"] = ns
        try:
            save_settings(ns)
        except Exception:
            # Keep runtime choice even if persistence fails.
            settings_state["settings"] = ns

    def get_hover_tooltip_enabled() -> bool:
        return bool(settings_state["settings"].hover_tooltip_enabled)

    def set_hover_tooltip_enabled(enabled: bool) -> None:
        s = settings_state["settings"]
        ns = replace(s, hover_tooltip_enabled=bool(enabled))
        settings_state["settings"] = ns
        try:
            save_settings(ns)
        except Exception:
            settings_state["settings"] = ns

    def get_target_language() -> str:
        return str(settings_state["settings"].target_language)

    def set_target_language(lang: str) -> None:
        s = settings_state["settings"]
        ns = replace(s, target_language=str(lang))
        settings_state["settings"] = ns
        try:
            save_settings(ns)
        except Exception:
            settings_state["settings"] = ns

    tray_icon = start_tray(
        root,
        hotkeys,
        get_selected_monitor=get_selected_monitor,
        set_selected_monitor=set_selected_monitor,
        get_target_language=get_target_language,
        set_target_language=set_target_language,
        get_hover_tooltip_enabled=get_hover_tooltip_enabled,
        set_hover_tooltip_enabled=set_hover_tooltip_enabled,
    )

    def pump() -> None:
        try:
            while True:
                item = result_q.get_nowait()
                if item is None:
                    close_result_window()
                elif item is RESULT_EVENT_PROCESSING:
                    open_result_pending(root)
                else:
                    img, regions = item
                    show_result_image(
                        root,
                        img,
                        ocr_regions=regions,
                        enable_ocr_hover_tooltip=get_hover_tooltip_enabled(),
                    )
        except queue.Empty:
            pass

        try:
            kind = event_q.get(timeout=0.15)
        except queue.Empty:
            root.after(40, pump)
            return

        if kind == "full":

            def cap() -> Image.Image:
                img, _ = grab_virtual_screen(get_selected_monitor())
                return img

            process_and_show(cap, result_q, get_target_language=get_target_language)
        elif kind == "region":
            bbox = region_selector(root)
            if bbox is not None:
                l, t, w, h = bbox

                def cap2() -> Image.Image:
                    return grab_region(l, t, w, h)

                process_and_show(cap2, result_q, get_target_language=get_target_language)

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
