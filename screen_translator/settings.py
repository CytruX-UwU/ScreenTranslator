"""
Persistent user settings (Windows-friendly).

Currently stores:
- selected_monitor: int
  - 0 means "all displays" (mss virtual screen)
  - 1..N means a specific monitor index in mss.monitors
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    selected_monitor: int = 0


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
    return Settings(selected_monitor=sel)


def save_settings(s: Settings) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(s), ensure_ascii=False, indent=2), encoding="utf-8")

