"""
Global hotkeys on Windows: user32.RegisterHotKey + dedicated thread message loop (WM_HOTKEY).
全局快捷键：仅 Windows，RegisterHotKey + 消息循环。
"""

from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes
from typing import Callable, Optional

from screen_translator.config import HOTKEY_FULL, HOTKEY_REGION

# Must match config (Ctrl+Shift+1/2). 与 config 中 Ctrl+Shift+1/2 一致（RegisterHotKey）。
_MOD_CTRL_SHIFT = 0x0002 | 0x0004
_VK_1 = 0x31
_VK_2 = 0x32

_WM_HOTKEY = 0x0312
_WM_QUIT = 0x0012

_ID_FULL = 1
_ID_REGION = 2


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


class GlobalHotKeys:
    """Windows-only global hotkeys via RegisterHotKey. start() / stop()."""

    def __init__(
        self,
        mapping: dict[str, Callable[[], None]],
    ) -> None:
        self._mapping = mapping
        self._impl_stop: Optional[Callable[[], None]] = None

    def start(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Screen Translator global hotkeys require Windows.")
        self._impl_stop = _start_register_hotkey(self._mapping)

    def stop(self) -> None:
        if self._impl_stop:
            self._impl_stop()
            self._impl_stop = None

    @property
    def backend(self) -> str:
        return "RegisterHotKey (user32)"


def _start_register_hotkey(
    mapping: dict[str, Callable[[], None]],
) -> Callable[[], None]:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    on_full = mapping.get(HOTKEY_FULL)
    on_region = mapping.get(HOTKEY_REGION)
    if on_full is None or on_region is None:
        raise RuntimeError("Hotkey mapping must include HOTKEY_FULL and HOTKEY_REGION.")

    done = threading.Event()
    thread_id_holder: dict[str, int] = {}
    ok_holder: dict[str, bool] = {"v": False}

    def worker() -> None:
        thread_id_holder["id"] = int(kernel32.GetCurrentThreadId())
        if not user32.RegisterHotKey(None, _ID_FULL, _MOD_CTRL_SHIFT, _VK_1):
            done.set()
            return
        if not user32.RegisterHotKey(None, _ID_REGION, _MOD_CTRL_SHIFT, _VK_2):
            user32.UnregisterHotKey(None, _ID_FULL)
            done.set()
            return
        ok_holder["v"] = True
        done.set()

        msg = _MSG()
        while True:
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r == 0:
                break
            if r == -1:
                break
            if msg.message == _WM_HOTKEY:
                wp = int(msg.wParam)
                if wp == _ID_FULL:
                    on_full()
                elif wp == _ID_REGION:
                    on_region()
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        user32.UnregisterHotKey(None, _ID_FULL)
        user32.UnregisterHotKey(None, _ID_REGION)

    t = threading.Thread(target=worker, name="win-hotkeys", daemon=True)
    t.start()
    done.wait(timeout=3.0)
    if not ok_holder["v"]:
        tid = thread_id_holder.get("id")
        if tid:
            user32.PostThreadMessageW(tid, _WM_QUIT, 0, 0)
        t.join(timeout=2.0)
        raise RuntimeError(
            "Failed to register global hotkeys (Ctrl+Shift+1 and Ctrl+Shift+2). "
            "Another application may already use them."
        )

    def stop() -> None:
        tid = thread_id_holder.get("id")
        if tid:
            user32.PostThreadMessageW(tid, _WM_QUIT, 0, 0)
        t.join(timeout=3.0)

    return stop
