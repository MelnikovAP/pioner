"""Process-wide logging setup (P1-40 / P2-4).

Single entry point that starts a **per-session log file**. Call
:func:`configure_logging` once when an application opens (the GUI entry
``runUI`` does this before the window is built, so startup itself is captured).

The session file is ``<LOGS_FOLDER>/pioner_session_<start-timestamp>.log`` with a
filesystem-safe timestamp (``-``/``_`` only, no ``:`` or spaces). The timestamp
is stamped once at call time; tests pass a fixed ``timestamp`` for determinism.

NOTE: the log directory is currently the repo's ``logs/`` folder (a stopgap); the
proper location is still open -- see TODO P1-40.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from pioner.shared.constants import LOGS_FOLDER_REL_PATH, SESSION_LOG_FILE_PREFIX

#: Filesystem-safe start-timestamp format (no ``:`` so it is a valid filename on
#: every OS). Example: ``2026-06-09_14-30-05``.
SESSION_LOG_TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"

_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

#: Marks the handlers this module installs, so a repeat call can drop them
#: instead of stacking duplicates (idempotent re-configuration).
_SESSION_HANDLER_FLAG = "_pioner_session_handler"


def session_log_filename(timestamp: Optional[str] = None) -> str:
    """Return the session log filename (``pioner_session_<timestamp>.log``)."""
    ts = timestamp if timestamp is not None else datetime.now().strftime(
        SESSION_LOG_TIMESTAMP_FORMAT
    )
    return f"{SESSION_LOG_FILE_PREFIX}{ts}.log"


def configure_logging(
    *,
    log_dir: Optional[str] = None,
    level: int = logging.INFO,
    timestamp: Optional[str] = None,
    console: bool = False,
) -> Path:
    """Attach a per-session file handler (and optional console handler) to root.

    Returns the log file path. **Idempotent:** any handlers this function
    previously installed are removed first, so calling it more than once swaps
    the session file rather than stacking handlers.

    Parameters
    ----------
    log_dir
        Directory for the session file; defaults to ``LOGS_FOLDER_REL_PATH``
        (the repo ``logs/`` stopgap). Created if missing.
    level
        Root log level (default ``INFO``).
    timestamp
        Filesystem-safe start-timestamp string; defaults to the wall clock at
        call time. Pass a fixed value for deterministic tests.
    console
        Also echo to stderr (the GUI entry point uses this).
    """
    directory = Path(log_dir) if log_dir is not None else Path(LOGS_FOLDER_REL_PATH)
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / session_log_filename(timestamp)

    root = logging.getLogger()
    root.setLevel(level)

    # Drop handlers from a previous configure_logging() call (idempotent).
    for handler in list(root.handlers):
        if getattr(handler, _SESSION_HANDLER_FLAG, False):
            root.removeHandler(handler)
            handler.close()

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    setattr(file_handler, _SESSION_HANDLER_FLAG, True)
    root.addHandler(file_handler)

    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(level)
        stream_handler.setFormatter(formatter)
        setattr(stream_handler, _SESSION_HANDLER_FLAG, True)
        root.addHandler(stream_handler)

    logging.getLogger(__name__).info("PIONER session log started -> %s", log_path)
    return log_path
