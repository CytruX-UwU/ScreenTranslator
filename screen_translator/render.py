"""Font selection and fitting for overlay labels in Pipeline. Pipeline 叠加文字用的字体选择与适配。"""

from typing import Any, Tuple

from PIL import ImageDraw, ImageFont

from screen_translator.config import FONT_MAX, FONT_MIN


def pick_font(size: int) -> Any:
    candidates = [
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\msyh.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def fit_font_for_box(
    draw: ImageDraw.ImageDraw, text: str, x1: int, y1: int, x2: int, y2: int
) -> Any:
    w, h = max(1, x2 - x1), max(1, y2 - y1)
    for size in range(FONT_MAX, FONT_MIN - 1, -1):
        font = pick_font(size)
        bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=2)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if tw <= w - 4 and th <= h - 4:
            return font
    return pick_font(FONT_MIN)
