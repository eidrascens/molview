"""Application logging configured for both terminal and GNOME state directory."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging() -> Path | None:
    """Configure useful debug output and return the persistent log-file path."""
    level_name = os.environ.get("MOLVIEW_LOG_LEVEL", "DEBUG").upper()
    level = getattr(logging, level_name, logging.DEBUG)
    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)-8s %(name)s [%(threadName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not any(getattr(handler, "_molview_handler", False) for handler in root.handlers):
        stderr = logging.StreamHandler(sys.stderr)
        stderr.setLevel(level)
        stderr.setFormatter(formatter)
        stderr._molview_handler = True  # type: ignore[attr-defined]
        root.addHandler(stderr)

    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    log_path: Path | None = None
    requested_path = os.environ.get("MOLVIEW_LOG_FILE")
    try:
        if requested_path:
            log_path = Path(requested_path).expanduser()
            log_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            log_dir = state_home / "molview-gnome"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "molview.log"
        file_handler = RotatingFileHandler(
            log_path, maxBytes=3 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler._molview_handler = True  # type: ignore[attr-defined]
        root.addHandler(file_handler)
    except OSError as exc:
        logging.getLogger(__name__).warning("Cannot create log file: %s", exc)
        log_path = None

    logging.getLogger(__name__).debug(
        "Logging initialized: level=%s, log_file=%s, python=%s, executable=%s",
        logging.getLevelName(level), log_path or "unavailable", sys.version.split()[0], sys.executable,
    )
    return log_path
