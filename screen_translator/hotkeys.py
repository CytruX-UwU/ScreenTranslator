"""
全局快捷键：Windows 下优先使用 RegisterHotKey + 消息循环（控制台 / IDE / 打包 exe 下比
WH_KEYBOARD_LL 钩子更稳定）；失败或非 Windows 时回退到 pynput。
"""

from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes
from typing import Callable, Optional

from screen_translator.config import HOTKEY_FULL, HOTKEY_REGION

# 与 config 中 Ctrl+Shift+1 / 2 一致（RegisterHotKey）
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
    """接口与 pynput.keyboard.GlobalHotKeys 相近：start() / stop()。"""

    def __init__(
        self,
        mapping: dict[str, Callable[[], None]],
    ) -> None:
        self._mapping = mapping
        self._impl_stop: Optional[Callable[[], None]] = None
        self._impl_kind: str = ""

    def start(self) -> None:
        if sys.platform == "win32":
            stopper = _try_start_win_register_hotkey(self._mapping)
            if stopper is not None:
                self._impl_stop = stopper
                self._impl_kind = "win32"
                return
        self._start_pynput()
        self._impl_kind = "pynput"

    def _start_pynput(self) -> None:
        from pynput import keyboard

        hotkeys = keyboard.GlobalHotKeys(self._mapping)
        hotkeys.start()
        self._impl_stop = hotkeys.stop

    def stop(self) -> None:
        if self._impl_stop:
            self._impl_stop()
            self._impl_stop = None

    @property
    def backend(self) -> str:
        return self._impl_kind


def _try_start_win_register_hotkey(
    mapping: dict[str, Callable[[], None]],
) -> Optional[Callable[[], None]]:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    on_full = mapping.get(HOTKEY_FULL)
    on_region = mapping.get(HOTKEY_REGION)
    if on_full is None or on_region is None:
        return None

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
        return None

    def stop() -> None:
        tid = thread_id_holder.get("id")
        if tid:
            user32.PostThreadMessageW(tid, _WM_QUIT, 0, 0)
        t.join(timeout=3.0)

    return stop
