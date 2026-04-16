"""Screen capture: virtual desktop, a specific monitor, and rectangular region. 屏幕截图（虚拟桌面/指定显示器/矩形区域）。"""

from __future__ import annotations

import sys
from typing import Dict, List, Optional, Tuple

import mss
from PIL import Image


def _win_monitor_names_by_rect() -> List[dict]:
    """
    Windows only: enumerate monitors and return a list of dicts:
    {left, top, width, height, device, name}.

    - device: like "\\\\.\\DISPLAY1"
    - name: friendly string from EnumDisplayDevices (e.g. "DELL U2720Q")
    """
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return []

    user32 = ctypes.windll.user32

    class RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG), ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32),
        ]

    class DISPLAY_DEVICEW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("DeviceName", wintypes.WCHAR * 32),
            ("DeviceString", wintypes.WCHAR * 128),
            ("StateFlags", wintypes.DWORD),
            ("DeviceID", wintypes.WCHAR * 128),
            ("DeviceKey", wintypes.WCHAR * 128),
        ]

    MonitorEnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM)

    out: List[dict] = []

    def _proc(hmon: wintypes.HMONITOR, _hdc: wintypes.HDC, _rc: ctypes.POINTER(RECT), _lp: wintypes.LPARAM) -> wintypes.BOOL:
        mi = MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return True

        r = mi.rcMonitor
        left, top = int(r.left), int(r.top)
        width, height = int(r.right - r.left), int(r.bottom - r.top)
        device = str(mi.szDevice)

        name = ""
        try:
            dd = DISPLAY_DEVICEW()
            dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)
            if user32.EnumDisplayDevicesW(device, 0, ctypes.byref(dd), 0):
                name = str(dd.DeviceString).strip()
        except Exception:
            name = ""

        out.append(
            {
                "left": left,
                "top": top,
                "width": width,
                "height": height,
                "device": device,
                "name": name,
            }
        )
        return True

    try:
        user32.EnumDisplayMonitors(0, 0, MonitorEnumProc(_proc), 0)
    except Exception:
        return []
    return out


def list_monitors() -> List[dict]:
    """
    Return mss monitor descriptors.
    Index 0 is the virtual desktop (all monitors). 1..N are physical monitors.
    """
    with mss.mss() as sct:
        mons = [dict(m) for m in sct.monitors]

    # Best-effort: enrich with friendly monitor names on Windows.
    win = _win_monitor_names_by_rect()

    def _match_name(mon: dict) -> Optional[dict]:
        for w in win:
            if (
                int(mon.get("left", 0)) == int(w["left"])
                and int(mon.get("top", 0)) == int(w["top"])
                and int(mon.get("width", 0)) == int(w["width"])
                and int(mon.get("height", 0)) == int(w["height"])
            ):
                return w
        return None

    for i in range(1, len(mons)):
        m = mons[i]
        hit = _match_name(m)
        if hit:
            if hit.get("device"):
                m["device"] = hit["device"]
            if hit.get("name"):
                m["name"] = hit["name"]

    return mons


def grab_virtual_screen(monitor_index: int = 0) -> Tuple[Image.Image, dict]:
    with mss.mss() as sct:
        monitors = sct.monitors
        idx = int(monitor_index or 0)
        if idx < 0 or idx >= len(monitors):
            idx = 0
        mon = monitors[idx]
        shot = sct.grab(mon)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        return img, dict(mon)


def grab_region(left: int, top: int, width: int, height: int) -> Image.Image:
    region: Dict[str, int] = {"left": left, "top": top, "width": width, "height": height}
    with mss.mss() as sct:
        shot = sct.grab(region)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
