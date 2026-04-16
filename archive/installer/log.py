"""File logging setup for the M12 Labs installer.

Provides a single named logger (``m12labs``) that writes verbose debug output
to a timestamped text file under ``<panel_root>/extension_logs/``.

Console output is intentionally **not** handled here – all user-facing output
is produced by ``print()`` calls throughout the codebase.  The logger is for
rich, file-only debug output that helps diagnose problems without cluttering
the terminal.

Usage::

    from log import setup_logging, get_logger

    # Call once at startup (after install_path and config are known):
    setup_logging(install_path, text_logs_enabled=True)

    # In any other module:
    from log import get_logger
    logger = get_logger()
    logger.debug("Something happened: %s", detail)
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

LOG_DIR_NAME = "extension_logs"
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_LOGGER_NAME = "m12labs"


def setup_logging(install_path: Path | None, text_logs_enabled: bool) -> logging.Logger:
    """Configure and return the ``m12labs`` logger.

    When *text_logs_enabled* is ``True`` and *install_path* is set, a
    ``FileHandler`` is attached that writes every DEBUG-and-above message to::

        <install_path>/extension_logs/logs-YYYY-MM-DD_HH-MM-SS.txt

    The log directory is created automatically if it does not exist.

    Console output is **not** affected by this function.  All ``print()``
    calls elsewhere remain the sole source of terminal output.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    # Remove any handlers added by a previous call (e.g. during tests).
    logger.handlers.clear()
    # Prevent log records from propagating to the root logger.
    logger.propagate = False

    if text_logs_enabled and install_path is not None:
        log_dir = install_path / LOG_DIR_NAME
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            log_file = log_dir / f"logs-{timestamp}.txt"
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
            logger.addHandler(file_handler)
        except OSError:
            # If the log directory or file cannot be created, silently
            # continue without file logging rather than crashing the installer.
            pass

    return logger


def get_logger() -> logging.Logger:
    """Return the ``m12labs`` application logger.

    The logger must have been configured via :func:`setup_logging` before
    calling this function.  If it has not been configured yet, log records
    are silently discarded (no handlers attached).
    """
    return logging.getLogger(_LOGGER_NAME)
