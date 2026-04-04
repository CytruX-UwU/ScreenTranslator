"""Screen capture: virtual desktop and rectangular region. 屏幕截图（虚拟桌面与矩形区域）。"""

from typing import Dict, Tuple

import mss
from PIL import Image


def grab_virtual_screen() -> Tuple[Image.Image, dict]:
    with mss.mss() as sct:
        mon = sct.monitors[0]
        shot = sct.grab(mon)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        return img, dict(mon)


def grab_region(left: int, top: int, width: int, height: int) -> Image.Image:
    region: Dict[str, int] = {"left": left, "top": top, "width": width, "height": height}
    with mss.mss() as sct:
        shot = sct.grab(region)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
