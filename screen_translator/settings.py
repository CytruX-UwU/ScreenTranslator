"""
Persistent user settings (Windows-friendly).

Currently stores:
- selected_monitor: int
  - 0 means "all displays" (mss virtual screen)
  - 1..N means a specific monitor index in mss.monitors
- hover_tooltip_enabled: bool — enlarged translation popup when hovering OCR boxes in the result window
- target_language: str — translation target language code (deep_translator / GoogleTranslator)
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    selected_monitor: int = 0
    hover_tooltip_enabled: bool = True
    target_language: str = "en"


def _settings_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata)
    else:
        base = Path.home() / ".config"
    return base / "ScreenTranslator" / "settings.json"


def load_settings() -> Settings:
    path = _settings_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Settings()
    except Exception:
        # Corrupt/partial file: fall back to defaults.
        return Settings()

    try:
        sel = int(raw.get("selected_monitor", 0))
    except Exception:
        sel = 0
    if sel < 0:
        sel = 0
    hover = raw.get("hover_tooltip_enabled", True)
    if isinstance(hover, str):
        hover = hover.strip().lower() in ("1", "true", "yes", "on")
    else:
        hover = bool(hover)
    lang = raw.get("target_language", "en")
    if not isinstance(lang, str):
        lang = "en"
    lang = lang.strip() or "en"
    return Settings(selected_monitor=sel, hover_tooltip_enabled=hover, target_language=lang)


def save_settings(s: Settings) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(s), ensure_ascii=False, indent=2), encoding="utf-8")

