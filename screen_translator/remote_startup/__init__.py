"""Remote startup content: author message, release check, ordered scheduling."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from .author_message import (
    fetch_author_message_rows,
    render_author_message_console,
)
from .release_check import (
    fetch_latest_release,
    local_version_string,
    render_release_update_notice,
)

if TYPE_CHECKING:
    import tkinter as tk

__all__ = ["schedule_startup_remote"]


def schedule_startup_remote(root: "tk.Tk") -> None:
    """
    Background thread: fetch remote author JSON first, then GitHub latest release.
    On the Tk main thread, callbacks run in order — author console output first,
    then update notice (console line or message box).

    Call after ``Tk()`` exists (e.g. after ``withdraw()``).
    """

    def worker() -> None:
        rows = fetch_author_message_rows()
        root.after(0, lambda rs=rows: render_author_message_console(rs))

        local = local_version_string()
        latest = fetch_latest_release()
        root.after(
            0,
            lambda r=root, loc=local, lat=latest: render_release_update_notice(r, local=loc, latest=lat),
        )

    threading.Thread(target=worker, daemon=True).start()
