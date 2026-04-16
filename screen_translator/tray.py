"""System tray (pystray); shutdown is coordinated with tk via root.after. 系统托盘（pystray），与 tk 主线程通过 root.after 协调退出。"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Callable, List, Sequence

import pystray
from PIL import Image, ImageDraw

if TYPE_CHECKING:
    import tkinter as tk

    from screen_translator.hotkeys import GlobalHotKeys

from screen_translator.capture import list_monitors

_HOVER_HELP_TITLE = "Enlarge translation on hover"
_HOVER_HELP_MESSAGE = (
    "When this option is enabled, move the pointer over an OCR box in the full-screen "
    "result window.\n\n"
    "A small floating window then shows the full translation in a larger font. "
    "That preview may sit on top of other overlay text so crowded regions stay readable.\n\n"
    "Turn the option off in the tray menu if you prefer a static image with no pop-ups."
)


def _tray_image() -> Image.Image:
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((4, 4, 60, 60), radius=12, fill=(52, 120, 220, 255))
    d.rounded_rectangle((12, 18, 52, 46), radius=6, fill=(230, 240, 255, 255))
    return im


def start_tray(
    root: "tk.Tk",
    hotkeys: "GlobalHotKeys",
    *,
    get_selected_monitor: Callable[[], int],
    set_selected_monitor: Callable[[int], None],
    get_hover_tooltip_enabled: Callable[[], bool],
    set_hover_tooltip_enabled: Callable[[bool], None],
    tooltip: str = "Screen Translator",
) -> pystray.Icon:
    """
    Run the tray icon in a background thread; return Icon for finally/cleanup.
    在后台线程中运行托盘图标；返回 Icon 供 finally 或异常路径清理。

    Quit calls hotkeys.stop(), icon.stop(), root.quit() on the tk thread.
    「退出」在 tk 主线程上执行 hotkeys.stop()、icon.stop()、root.quit()。
    """
    image = _tray_image()

    def on_quit(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        root.after(0, lambda: _shutdown_from_tray(icon, root, hotkeys))

    def _mon_label(i: int, mon: dict) -> str:
        l, t, w, h = mon.get("left", 0), mon.get("top", 0), mon.get("width", 0), mon.get("height", 0)
        name = str(mon.get("name", "") or "").strip()
        if i == 0:
            return f"All displays ({w}×{h})"
        if name:
            return f"Display {i} — {name} ({w}×{h} @ {l},{t})"
        return f"Display {i} ({w}×{h} @ {l},{t})"

    monitors: List[dict] = list_monitors()
    max_monitor_index = max(0, len(monitors) - 1)

    def _coerce_selected_monitor() -> int:
        """
        Ensure the selected monitor index is valid for the current monitor list.
        If invalid (e.g. monitor disconnected), fall back to 0 (All displays) and persist it.
        """
        try:
            sel = int(get_selected_monitor())
        except Exception:
            sel = 0
        if sel < 0 or sel > max_monitor_index:
            sel = 0
            try:
                set_selected_monitor(0)
            except Exception:
                pass
        return sel

    # Coerce once at tray startup so the menu always has one checked item.
    _coerce_selected_monitor()

    def _make_monitor_items() -> Sequence[pystray.MenuItem]:
        items: List[pystray.MenuItem] = []

        for i, mon in enumerate(monitors):
            label = _mon_label(i, mon)

            def _make_action(idx: int) -> Callable[[pystray.Icon, pystray.MenuItem], None]:
                def _action(icon: pystray.Icon, item: pystray.MenuItem) -> None:
                    set_selected_monitor(idx)
                    try:
                        icon.update_menu()
                    except Exception:
                        pass

                return _action

            def _make_checked(idx: int) -> Callable[[pystray.MenuItem], bool]:
                def _checked(item: pystray.MenuItem) -> bool:
                    return _coerce_selected_monitor() == idx

                return _checked

            items.append(pystray.MenuItem(label, _make_action(i), checked=_make_checked(i), radio=True))

        return items

    monitor_menu = pystray.Menu(*_make_monitor_items())

    def on_toggle_hover_tooltip(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        set_hover_tooltip_enabled(not bool(get_hover_tooltip_enabled()))
        try:
            icon.update_menu()
        except Exception:
            pass

    def _hover_tooltip_checked(item: pystray.MenuItem) -> bool:
        return bool(get_hover_tooltip_enabled())

    def on_about_hover_tooltip(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        def _show() -> None:
            from tkinter import messagebox

            messagebox.showinfo(_HOVER_HELP_TITLE, _HOVER_HELP_MESSAGE, parent=root)

        root.after(0, _show)

    menu = pystray.Menu(
        pystray.MenuItem("Monitor", monitor_menu),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Enlarge translation on hover",
            on_toggle_hover_tooltip,
            checked=_hover_tooltip_checked,
        ),
        pystray.MenuItem("About enlarge-on-hover…", on_about_hover_tooltip),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", on_quit),
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
