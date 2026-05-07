"""Background GitHub Release check vs local version (pyproject / installed metadata)."""

from __future__ import annotations

import importlib.metadata
import json
import logging
import re
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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


def _read_version_from_pyproject() -> Optional[str]:
    root = Path(__file__).resolve().parent.parent
    path = root / "pyproject.toml"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return m.group(1) if m else None


def local_version_string() -> str:
    """Prefer installed distribution metadata; fall back to repo pyproject.toml."""
    try:
        return importlib.metadata.version("screen-translator")
    except importlib.metadata.PackageNotFoundError:
        v = _read_version_from_pyproject()
        return v if v else "0.0.0"


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


def schedule_startup_release_notice(root) -> None:
    """
    Fetch latest release in a daemon thread; if newer than local, notify on the Tk thread.
    Console: one line to stdout; windowed / no TTY: tkinter message box.
    """

    def worker() -> None:
        local = local_version_string()
        latest = fetch_latest_release()
        if latest is None or not remote_is_newer(local, latest.version):
            return

        line = (
            f"Update available: v{latest.version} (current v{local}). "
            f"See {latest.html_url}"
        )

        def on_main_thread() -> None:
            logger.info("%s", line)
            if stdout_is_tty():
                try:
                    print(console_blue(line), flush=True)
                except OSError:
                    pass
            else:
                import tkinter.messagebox as mb

                mb.showinfo(
                    "Screen Translator — update available",
                    f"A newer release is available (v{latest.version}).\n"
                    f"You are on v{local}.\n\n"
                    f"Open the releases page to download:\n{latest.html_url}",
                )

        root.after(0, on_main_thread)

    threading.Thread(target=worker, daemon=True).start()
