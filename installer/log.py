"""File logging setup for the M12Labs panel installer.

Provides a single named logger (``m12labs.setup``) that writes verbose debug
output to a timestamped text file under ``<install_path>/setup_logs/``.

Console output is intentionally **not** handled here – all user-facing output
is produced by ``print()`` calls throughout the codebase.  The logger is for
rich, file-only debug output that helps diagnose problems without cluttering
the terminal.

Usage::

    from installer.log import setup_logging, get_logger

    # Call once at startup (after install_path and config are known):
    setup_logging(install_path, text_logs_enabled=True)

    # In any other module:
    from installer.log import get_logger
    logger = get_logger()
    logger.debug("Something happened: %s", detail)
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

LOG_DIR_NAME = "setup_logs"
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_LOGGER_NAME = "m12labs.setup"


def setup_logging(install_path: Path | None, text_logs_enabled: bool) -> logging.Logger:
    """Configure and return the ``m12labs.setup`` logger.

    When *text_logs_enabled* is ``True`` and *install_path* is set, a
    ``FileHandler`` is attached that writes every DEBUG-and-above message to::

        <install_path>/setup_logs/logs-YYYY-MM-DD_HH-MM-SS.txt

    The log directory is created automatically if it does not exist.

    Console output is **not** affected by this function.  All ``print()``
    calls elsewhere remain the sole source of terminal output.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    # Remove any handlers added by a previous call (e.g. during tests)
    logger.handlers.clear()
    # Prevent log records from propagating to the root logger
    logger.propagate = False

    if text_logs_enabled and install_path is not None:
        log_dir = install_path / LOG_DIR_NAME
        log_file: Path | None = None

        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            log_file = log_dir / f"logs-{timestamp}.txt"
        except OSError:
            pass

        # Fall back to /tmp when install_path doesn't exist yet or isn't writable
        if log_file is None or not log_file.parent.exists():
            try:
                import tempfile as _tempfile
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                tmp_dir = Path(_tempfile.gettempdir())
                log_file = tmp_dir / f"m12labs-installer-{timestamp}.log"
            except OSError:
                log_file = None

        if log_file is not None:
            try:
                file_handler = logging.FileHandler(log_file, encoding="utf-8")
                file_handler.setLevel(logging.DEBUG)
                file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
                logger.addHandler(file_handler)
            except OSError:
                # If the log file cannot be created, continue without file logging
                pass

    return logger


def get_logger() -> logging.Logger:
    """Return the ``m12labs.setup`` application logger.

    The logger must have been configured via :func:`setup_logging` before
    calling this function.  If it has not been configured yet, log records
    are silently discarded (no handlers attached).
    """
    return logging.getLogger(_LOGGER_NAME)
