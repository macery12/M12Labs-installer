"""Config management for the M12 Labs installer.

Reads and writes ``config.toml`` located in the same directory as this file.
Creates the file with sensible defaults when it does not exist yet.

File format (TOML)::

    install_path = "/var/www/m12labs"
    show_detailed_checks = false
    build_on_update = false
    build_on_uninstall = false
    text_logs_enabled = true
"""

from __future__ import annotations

import logging
import os
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

EXAMPLE_PATH = "/var/www/m12labs"

# Config file lives next to this source file so it stays with the installer.
_CONFIG_FILE = Path(__file__).parent / "config.toml"

_logger = logging.getLogger("m12labs")


@dataclass
class Config:
    install_path: Path | None = None
    show_detailed_checks: bool = False
    build_on_update: bool = False
    build_on_uninstall: bool = False
    text_logs_enabled: bool = True


def load_config() -> Config:
    """Load config from ``config.toml``, returning defaults if missing or invalid."""
    try:
        with _CONFIG_FILE.open("rb") as fh:
            data = tomllib.load(fh)
    except OSError:
        _logger.debug("Config file not found or unreadable (%s) – using defaults", _CONFIG_FILE)
        return Config()

    install_path_str = data.get("install_path", "").strip()
    cfg = Config(
        install_path=Path(install_path_str) if install_path_str else None,
        show_detailed_checks=bool(data.get("show_detailed_checks", False)),
        build_on_update=bool(data.get("build_on_update", False)),
        build_on_uninstall=bool(data.get("build_on_uninstall", False)),
        text_logs_enabled=bool(data.get("text_logs_enabled", True)),
    )
    _logger.debug(
        "Config loaded from %s: install_path=%s, text_logs_enabled=%s, "
        "show_detailed_checks=%s, build_on_update=%s, build_on_uninstall=%s",
        _CONFIG_FILE,
        cfg.install_path,
        cfg.text_logs_enabled,
        cfg.show_detailed_checks,
        cfg.build_on_update,
        cfg.build_on_uninstall,
    )
    return cfg


def save_config(config: Config) -> None:
    """Write all config fields to ``config.toml`` using an atomic write.

    The new content is written to a temporary file in the same directory first,
    then renamed into place.  This prevents a partially-written (corrupted)
    config file if the process is interrupted mid-write.
    """
    install_path_value = str(config.install_path) if config.install_path is not None else ""
    lines = [
        f'install_path = "{install_path_value}"',
        f"show_detailed_checks = {str(config.show_detailed_checks).lower()}",
        f"build_on_update = {str(config.build_on_update).lower()}",
        f"build_on_uninstall = {str(config.build_on_uninstall).lower()}",
        f"text_logs_enabled = {str(config.text_logs_enabled).lower()}",
    ]
    content = "\n".join(lines) + "\n"

    config_dir = _CONFIG_FILE.parent
    try:
        fd, tmp_path = tempfile.mkstemp(dir=config_dir, prefix=".config_tmp_", suffix=".toml")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, _CONFIG_FILE)
        except Exception:
            # Clean up the temp file on failure to avoid leaving debris.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except OSError as exc:
        _logger.error("Failed to save config to %s: %s", _CONFIG_FILE, exc)
        raise

    _logger.debug(
        "Config saved to %s: install_path=%s, text_logs_enabled=%s, "
        "show_detailed_checks=%s, build_on_update=%s, build_on_uninstall=%s",
        _CONFIG_FILE,
        config.install_path,
        config.text_logs_enabled,
        config.show_detailed_checks,
        config.build_on_update,
        config.build_on_uninstall,
    )


_REQUIRED_FILES = ("artisan", "package.json", "composer.json")


def validate_install_path(path: Path) -> str | None:
    """Check that *path* looks like a valid M12 Labs panel installation.

    Returns ``None`` when the path is valid, or a human-readable error string
    describing the first problem found.
    """
    if not path.exists():
        return "directory does not exist"
    if not path.is_dir():
        return "not a directory"
    for required in _REQUIRED_FILES:
        if not (path / required).is_file():
            return f"missing `{required}`"
    return None


def prompt_for_install_path(config: Config) -> Config:
    """Prompt the user for the panel install path, persist and return updated config."""
    if config.install_path is None:
        _logger.info("Install path not configured – prompting user")
        print("\nPanel install location has not been configured yet.")
    else:
        _logger.info("User changing install path (current: %s)", config.install_path)
        print(f"\nCurrent install path: {config.install_path}")
    print(f"  Example: {EXAMPLE_PATH}")
    while True:
        raw = input("Enter panel install path: ").strip()
        if not raw:
            print("Path cannot be empty. Please try again.")
            continue
        candidate = Path(raw)
        error = validate_install_path(candidate)
        if error:
            _logger.warning("Invalid install path %s: %s", candidate, error)
            print(f"Invalid path: {error}. Please try again.")
            continue
        config.install_path = candidate
        save_config(config)
        _logger.info("Install path set to: %s", config.install_path)
        print(f"Saved install path: {config.install_path}")
        return config


def ensure_install_path(config: Config) -> Config:
    """Return config with ``install_path`` set, prompting the user if not yet configured."""
    if config.install_path is not None:
        _logger.debug("Install path already set: %s", config.install_path)
        return config
    return prompt_for_install_path(config)
