"""Font selection and fitting for overlay labels in Pipeline. Pipeline 叠加文字用的字体选择与适配。"""

from typing import Any, List

from PIL import ImageDraw, ImageFont

from screen_translator.config import FONT_MAX, FONT_MIN

# Pillow `spacing`: extra pixels between lines for multiline text (0 = tight; no gap beyond font metrics).
# 多行时行与行之间的「额外」空白；0 表示不额外留白，仅依赖字体自带行高，避免字母重叠。
OVERLAY_MULTILINE_SPACING = 0


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
        bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=OVERLAY_MULTILINE_SPACING)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if tw <= w - 4 and th <= h - 4:
            return font
    return pick_font(FONT_MIN)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: Any) -> float:
    try:
        return float(draw.textlength(text, font=font))
    except Exception:
        bbox = draw.textbbox((0, 0), text, font=font)
        return float(bbox[2] - bbox[0])


def wrap_text_to_width(draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int) -> str:
    """Greedy wrap to max_width (px); long tokens split by character."""
    max_width = max(1, int(max_width))
    s = " ".join(text.strip().split())
    if not s:
        return ""
    words = s.split(" ")
    lines: List[str] = []
    cur = ""

    def push(line: str) -> None:
        if line:
            lines.append(line)

    for w in words:
        cand = w if not cur else f"{cur} {w}"
        if _text_width(draw, cand, font) <= max_width:
            cur = cand
            continue
        push(cur)
        cur = ""
        if _text_width(draw, w, font) > max_width:
            chunk = ""
            for ch in w:
                cand2 = f"{chunk}{ch}"
                if chunk and _text_width(draw, cand2, font) > max_width:
                    push(chunk)
                    chunk = ch
                else:
                    chunk = cand2
            push(chunk)
        else:
            cur = w
    push(cur)
    return "\n".join(lines)


def line_height_px(draw: ImageDraw.ImageDraw, font: Any, spacing: int = OVERLAY_MULTILINE_SPACING) -> int:
    """Approximate one line height for overlay positioning (half-line shift)."""
    bbox = draw.multiline_textbbox((0, 0), "Ag", font=font, spacing=spacing)
    return max(1, int(bbox[3] - bbox[1]))
