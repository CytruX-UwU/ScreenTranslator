"""Screen capture: virtual desktop, a specific monitor, and rectangular region. 屏幕截图（虚拟桌面/指定显示器/矩形区域）。"""

from typing import Dict, List, Tuple

import mss
from PIL import Image


def list_monitors() -> List[dict]:
    """
    Return mss monitor descriptors.
    Index 0 is the virtual desktop (all monitors). 1..N are physical monitors.
    """
    with mss.mss() as sct:
        return [dict(m) for m in sct.monitors]


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
