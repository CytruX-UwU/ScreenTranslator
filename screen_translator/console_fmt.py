"""ANSI foreground colors when stdout is a TTY; enables Windows VT mode when needed."""

from __future__ import annotations

import ctypes
import os
import sys


def enable_windows_vt_mode() -> None:
    """Best-effort enable ANSI escape processing on Windows consoles."""
    if os.name != "nt":
        return
    try:
        handle = ctypes.windll.kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)) == 0:
            return
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        ctypes.windll.kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def stdout_is_tty() -> bool:
    try:
        out = sys.stdout
        if out is None:
            return False
        if not hasattr(out, "isatty"):
            return False
        return bool(out.isatty())
    except Exception:
        return False


def ansi_foreground(sgr_code: int, text: str) -> str:
    """Wrap text with SGR foreground code (e.g. 31 red, 32 green) when stdout is a TTY."""
    if not stdout_is_tty():
        return text
    enable_windows_vt_mode()
    return f"\x1b[{sgr_code}m{text}\x1b[0m"


def green(text: str) -> str:
    return ansi_foreground(32, text)


def red(text: str) -> str:
    return ansi_foreground(31, text)


def blue(text: str) -> str:
    return ansi_foreground(34, text)
