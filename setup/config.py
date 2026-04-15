"""Config management for the M12Labs panel installer.

Reads and writes ``setup/config.toml`` using ``tomllib``.
Creates the file with sensible defaults when it does not exist.

**Security:** The database password is NEVER persisted to disk by this
module.  It is collected from the user (or auto-generated) once, held
in memory for the duration of the install run, and written only into
the panel's ``.env`` file by ``steps/laravel.py``.

File format (TOML)::

    install_path = "/var/www/m12labs"
    db_name = "jexactyldb"
    db_user = "jexactyluser"
    non_interactive = false
    text_logs_enabled = true
"""

from __future__ import annotations

import logging
import os
import secrets
import string
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_INSTALL_PATH: Path = Path("/var/www/m12labs")
DEFAULT_DB_NAME: str = "jexactyldb"
DEFAULT_DB_USER: str = "jexactyluser"

# Config file lives next to this source file so it stays with the installer
_CONFIG_FILE = Path(__file__).parent / "config.toml"

_logger = logging.getLogger("m12labs.setup")


@dataclass
class InstallConfig:
    """Runtime configuration for the panel installer.

    Note: ``db_pass`` is intentionally absent.  The password only ever
    lives in memory (as a plain ``str`` local variable) and in the
    panel's ``.env``.  It must not be added to this dataclass or to any
    persisted file.
    """

    install_path: Path = field(default_factory=lambda: DEFAULT_INSTALL_PATH)
    db_name: str = DEFAULT_DB_NAME
    db_user: str = DEFAULT_DB_USER
    selected_release: str = ""
    selected_release_url: str = ""
    non_interactive: bool = False
    text_logs_enabled: bool = True


def load_config() -> InstallConfig:
    """Load config from ``config.toml``, returning defaults if missing or invalid."""
    try:
        with _CONFIG_FILE.open("rb") as fh:
            data = tomllib.load(fh)
    except OSError:
        _logger.debug("Config file not found or unreadable (%s) – using defaults", _CONFIG_FILE)
        return InstallConfig()

    install_path_str = str(data.get("install_path", "")).strip()
    db_name = str(data.get("db_name", DEFAULT_DB_NAME)).strip() or DEFAULT_DB_NAME
    db_user = str(data.get("db_user", DEFAULT_DB_USER)).strip() or DEFAULT_DB_USER

    cfg = InstallConfig(
        install_path=Path(install_path_str) if install_path_str else DEFAULT_INSTALL_PATH,
        db_name=db_name,
        db_user=db_user,
        selected_release=str(data.get("selected_release", "")).strip(),
        selected_release_url=str(data.get("selected_release_url", "")).strip(),
        non_interactive=bool(data.get("non_interactive", False)),
        text_logs_enabled=bool(data.get("text_logs_enabled", True)),
    )
    _logger.debug(
        "Config loaded: install_path=%s, db_name=%s, db_user=%s, selected_release=%s",
        cfg.install_path,
        cfg.db_name,
        cfg.db_user,
        cfg.selected_release,
    )
    return cfg


def save_config(cfg: InstallConfig) -> None:
    """Write all config fields to ``config.toml`` using an atomic write.

    **The database password is never written by this function.**
    """
    lines = [
        f'install_path = "{cfg.install_path}"',
        f'db_name = "{cfg.db_name}"',
        f'db_user = "{cfg.db_user}"',
        f'selected_release = "{cfg.selected_release}"',
        f'selected_release_url = "{cfg.selected_release_url}"',
        f"non_interactive = {str(cfg.non_interactive).lower()}",
        f"text_logs_enabled = {str(cfg.text_logs_enabled).lower()}",
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
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except OSError as exc:
        _logger.error("Failed to save config to %s: %s", _CONFIG_FILE, exc)
        raise

    _logger.debug(
        "Config saved: install_path=%s, db_name=%s, db_user=%s, selected_release=%s",
        cfg.install_path,
        cfg.db_name,
        cfg.db_user,
        cfg.selected_release,
    )


def generate_db_password(length: int = 24) -> str:
    """Generate a cryptographically secure random database password.

    The returned string lives only in memory and is never written to disk
    by this module.
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def prompt_for_install_path(cfg: InstallConfig) -> InstallConfig:
    """Prompt the user for the panel install path; persist and return updated config."""
    print(f"\nPanel install path (default: {DEFAULT_INSTALL_PATH}):")
    raw = input(f"  Enter path [press Enter for {DEFAULT_INSTALL_PATH}]: ").strip()
    cfg.install_path = Path(raw) if raw else DEFAULT_INSTALL_PATH
    save_config(cfg)
    _logger.info("Install path set to: %s", cfg.install_path)
    print(f"  Install path: {cfg.install_path}")
    return cfg


def prompt_for_db_config(cfg: InstallConfig) -> tuple[InstallConfig, str]:
    """Prompt for DB name/user (persisted) and password (in memory only).

    Returns:
        A tuple of ``(updated_config, db_pass_plaintext)``.

    **Security:** The returned password string is never saved to disk by
    this function.  The caller is responsible for passing it directly to
    the install steps and not persisting it anywhere.
    """
    print("\nDatabase configuration:")

    raw_name = input(f"  DB name   [default: {cfg.db_name}]: ").strip()
    if raw_name:
        cfg.db_name = raw_name

    raw_user = input(f"  DB user   [default: {cfg.db_user}]: ").strip()
    if raw_user:
        cfg.db_user = raw_user

    print("  DB password: leave blank to auto-generate a secure password.")
    raw_pass = input("  DB password [blank = auto-generate]: ").strip()
    if raw_pass:
        db_pass = raw_pass
    else:
        db_pass = generate_db_password()
        print(f"  Generated password: {db_pass}")
        print("  (Save this now – it will not be shown again.)")

    # Persist name and user to disk; password is intentionally NOT saved
    save_config(cfg)
    _logger.info(
        "DB config set: db_name=%s, db_user=%s (password not logged)",
        cfg.db_name,
        cfg.db_user,
    )
    return cfg, db_pass


def prompt_for_release(cfg: InstallConfig) -> InstallConfig:
    """Fetch available GitHub releases and prompt the user to pick one.

    Sets ``cfg.selected_release`` and ``cfg.selected_release_url``, persists
    them to ``config.toml``, and returns the updated config.

    Falls back to the hard-coded default release URL when the GitHub API is
    unreachable, so the installer can still proceed offline.
    """
    # Deferred import to keep config.py dependency-free at import time.
    from setup.steps.releases import (
        DEVELOP_BRANCH_TAG,
        DEVELOP_REPO_GIT_URL,
        fetch_releases,
        get_archive_url,
        prompt_release_selection,
    )
    import urllib.error

    print("\nFetching available M12 Labs releases from GitHub…")
    try:
        releases = fetch_releases()
    except (urllib.error.URLError, OSError) as exc:
        _logger.warning("Could not fetch releases (%s) – using default URL", exc)
        print(f"  Warning: could not reach GitHub ({exc}).")
        print("  Falling back to default release URL.")
        return cfg

    release = prompt_release_selection(releases)
    if release is None:
        # User pressed Back; keep existing selection (or empty = default).
        print("  No release selected – using previous selection or default.")
        return cfg

    if release.tag == DEVELOP_BRANCH_TAG:
        cfg.selected_release = DEVELOP_BRANCH_TAG
        cfg.selected_release_url = ""
    else:
        cfg.selected_release = release.tag
        cfg.selected_release_url = get_archive_url(release)

    save_config(cfg)
    _logger.info("Release selected: %s (%s)", cfg.selected_release, cfg.selected_release_url)
    print(f"  Selected: {release.name}")
    return cfg
