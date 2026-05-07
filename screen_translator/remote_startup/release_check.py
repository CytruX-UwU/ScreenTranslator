"""Background GitHub Release check vs local version (pyproject / installed metadata)."""

from __future__ import annotations

import importlib.metadata
import json
import logging
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import tkinter as tk

from packaging.version import InvalidVersion, Version

from screen_translator.console_fmt import blue as console_blue
from screen_translator.console_fmt import stdout_is_tty

logger = logging.getLogger(__name__)

GITHUB_OWNER_REPO = "CytruX-UwU/ScreenTranslator"
RELEASES_LATEST_API = f"https://api.github.com/repos/{GITHUB_OWNER_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_OWNER_REPO}/releases"

_TAG_PREFIX_RE = re.compile(r"^v\s*(.+)$", re.IGNORECASE)


def _normalize_tag_version(tag_name: str) -> str:
    t = tag_name.strip()
    m = _TAG_PREFIX_RE.match(t)
    return (m.group(1) if m else t).strip()


def _pyproject_path() -> Optional[Path]:
    """
    Development: ``<repo>/pyproject.toml`` (this file lives under ``screen_translator/remote_startup/``).

    PyInstaller: bundled copy under ``sys._MEIPASS``, or ``pyproject.toml`` next to the executable.
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bundled = Path(meipass) / "pyproject.toml"
            if bundled.is_file():
                return bundled
        beside_exe = Path(sys.executable).resolve().parent / "pyproject.toml"
        if beside_exe.is_file():
            return beside_exe
        return None
    # remote_startup/release_check.py -> parent.parent.parent == repo root
    return Path(__file__).resolve().parent.parent.parent / "pyproject.toml"


def _read_version_from_pyproject() -> Optional[str]:
    path = _pyproject_path()
    if path is None or not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return m.group(1) if m else None


def local_version_string() -> str:
    """Prefer repo ``pyproject.toml`` when present (dev checkout); else installed metadata."""
    pv = _read_version_from_pyproject()
    if pv:
        return pv
    try:
        return importlib.metadata.version("screen-translator")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


@dataclass(frozen=True)
class LatestRelease:
    version: str
    html_url: str


def fetch_latest_release(*, timeout_sec: float = 4.0) -> Optional[LatestRelease]:
    req = urllib.request.Request(
        RELEASES_LATEST_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "screen-translator-release-check",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        logger.debug("release check request failed: %s", e)
        return None

    tag = str(data.get("tag_name") or "").strip()
    if not tag:
        return None
    ver = _normalize_tag_version(tag)
    url = str(data.get("html_url") or "").strip() or RELEASES_PAGE
    return LatestRelease(version=ver, html_url=url)


def remote_is_newer(local: str, remote: str) -> bool:
    try:
        return Version(remote) > Version(local)
    except InvalidVersion:
        logger.debug("invalid version for compare: local=%r remote=%r", local, remote)
        return False


def render_release_update_notice(root: "tk.Tk", *, local: str, latest: Optional[LatestRelease]) -> None:
    """
    If GitHub latest is newer than ``local``, print to console (TTY) or show a message box.
    Must run on the Tk main thread (e.g. via ``root.after``).
    """
    if latest is None or not remote_is_newer(local, latest.version):
        return

    line = (
        f"Update available: v{latest.version} (current v{local}). "
        f"See {latest.html_url}"
    )
    # logger.info("%s", line)

    if stdout_is_tty():
        try:
            print(console_blue(line), flush=True)
        except OSError:
            pass
        return

    import tkinter.messagebox as mb

    mb.showinfo(
        "Screen Translator — update available",
        f"A newer release is available (v{latest.version}).\n"
        f"You are on v{local}.\n\n"
        f"Open the releases page to download:\n{latest.html_url}",
        parent=root,
    )
