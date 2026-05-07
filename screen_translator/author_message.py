"""
Author note fetched from the GitHub repo at startup (console only).

Default source:
  https://raw.githubusercontent.com/CytruX-UwU/ScreenTranslator/master/author_message.json

Expected JSON shape:
  { "message": [ { "format": ["green"], "text": "..." }, ... ] }

``format`` is a list of strings (tags), compared case-insensitively:
  ``hide`` — skip this block (not printed; useful for drafts / debugging).
  ``red``, ``green``, ``blue`` — console color; at most one applies: red > green > blue.

Legacy: ``format`` may still be a single string; it is split on whitespace into tags.

Other root keys (e.g. ``_documentation``) are ignored.

Plain UTF-8 text (non-JSON) is still supported as a fallback (no coloring).

Overrides:
  SCREEN_TRANSLATOR_AUTHOR_MESSAGE_URL / _BRANCH / _PATH (default path: author_message.json)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

GITHUB_OWNER = "CytruX-UwU"
GITHUB_REPO = "ScreenTranslator"
DEFAULT_BRANCH = "master"
DEFAULT_REPO_PATH = "author_message.json"


def author_message_url() -> str:
    override = os.environ.get("SCREEN_TRANSLATOR_AUTHOR_MESSAGE_URL", "").strip()
    if override:
        return override
    branch = os.environ.get("SCREEN_TRANSLATOR_AUTHOR_MESSAGE_BRANCH", DEFAULT_BRANCH).strip() or DEFAULT_BRANCH
    path = os.environ.get("SCREEN_TRANSLATOR_AUTHOR_MESSAGE_PATH", DEFAULT_REPO_PATH).strip() or DEFAULT_REPO_PATH
    path = path.lstrip("/")
    return f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{branch}/{path}"


def _text_to_display_lines_plain(text: str) -> list[str]:
    if text.startswith("\ufeff"):
        text = text[1:]
    out: list[str] = []
    for ln in text.splitlines():
        stripped = ln.strip()
        if stripped.startswith("#"):
            continue
        out.append(ln.rstrip("\r\n"))
    while out and not out[-1].strip():
        out.pop()
    while out and not out[0].strip():
        out.pop(0)
    return out


def _normalize_format_tags(fmt_raw: object) -> list[str]:
    """Coerce JSON ``format`` to a list of non-empty tag strings."""
    if fmt_raw is None:
        return []
    if isinstance(fmt_raw, list):
        out: list[str] = []
        for x in fmt_raw:
            if isinstance(x, str):
                s = x.strip()
            else:
                s = str(x).strip()
            if s:
                out.append(s)
        return out
    if isinstance(fmt_raw, str):
        return [t for t in fmt_raw.split() if t]
    return []


def _tags_include_hide(tags: list[str]) -> bool:
    return any(t.lower() == "hide" for t in tags)


def apply_format_tags(tags: list[str], text: str) -> str:
    """
    Apply console color from tags (red > green > blue). Caller must skip segments when ``hide`` is set.
    """
    from screen_translator.console_fmt import blue, green, red

    lt = [t.lower() for t in tags]
    if "red" in lt:
        return red(text)
    if "green" in lt:
        return green(text)
    if "blue" in lt:
        return blue(text)
    return text


def _rows_from_json(text: str) -> list[tuple[list[str], str]]:
    data = json.loads(text)
    msg = data.get("message")
    if not isinstance(msg, list):
        return []
    rows: list[tuple[list[str], str]] = []
    for item in msg:
        if not isinstance(item, dict):
            continue
        tags = _normalize_format_tags(item.get("format"))
        t = item.get("text")
        if not isinstance(t, str):
            continue
        for segment in t.splitlines(keepends=True):
            rows.append((tags, segment))
    return rows


def _parse_body_to_rows(text: str) -> list[tuple[list[str], str]]:
    stripped = text.lstrip("\ufeff\u200b").strip()
    if stripped.startswith("{"):
        try:
            return _rows_from_json(text.lstrip("\ufeff\u200b"))
        except json.JSONDecodeError as e:
            logger.debug("author message JSON parse failed: %s", e)
    plain_lines = _text_to_display_lines_plain(text)
    return [([], ln + "\n") for ln in plain_lines]


def fetch_author_message_rows(*, timeout_sec: float = 4.0) -> list[tuple[list[str], str]]:
    """Return (format_tags, segment) rows to print; empty on failure."""
    url = author_message_url()
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "screen-translator-author-message"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        logger.debug("author message fetch failed: %s", e)
        return []

    try:
        body = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        logger.debug("author message decode failed: %s", e)
        return []

    return _parse_body_to_rows(body)


def schedule_console_author_message() -> None:
    """Fetch author message in a daemon thread; print styled segments when done (TTY only)."""

    def worker() -> None:
        from screen_translator.console_fmt import stdout_is_tty

        rows = fetch_author_message_rows()
        if not rows or not stdout_is_tty():
            return
        try:
            for tags, segment in rows:
                if _tags_include_hide(tags):
                    continue
                print(apply_format_tags(tags, segment), end="", flush=True)
        except OSError:
            pass

    threading.Thread(target=worker, daemon=True).start()
