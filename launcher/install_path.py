"""Install path management for the M12 Labs launcher.

Prompts the user for the panel install location on first run and saves it for
reuse on all subsequent runs.  The value is stored in ``config.toml`` located
in the same directory as this file (i.e. the ``launcher/`` folder), so the
config travels with the launcher rather than being buried under ``~/.config``.

File format (TOML)::

    install_path = "/var/www/m12labs"
"""

from __future__ import annotations

import tomllib
from pathlib import Path

EXAMPLE_PATH = "/var/www/m12labs"

# Config file lives next to this source file so it stays with the launcher.
_CONFIG_FILE = Path(__file__).parent / "config.toml"


def load_saved_install_path() -> Path | None:
    """Return the previously saved install path, or None if not set."""
    try:
        with _CONFIG_FILE.open("rb") as fh:
            data = tomllib.load(fh)
        value = data.get("install_path", "").strip()
        if value:
            return Path(value)
    except OSError:
        pass
    return None


def save_install_path(path: Path) -> None:
    """Persist the install path to ``config.toml`` so future runs reuse it."""
    _CONFIG_FILE.write_text(
        f'install_path = "{path}"\n',
        encoding="utf-8",
    )


def prompt_for_install_path() -> Path:
    """Prompt the user to enter the panel install location and save it."""
    print("\nPanel install location has not been configured yet.")
    print(f"  Example: {EXAMPLE_PATH}")
    while True:
        raw = input("Enter panel install path: ").strip()
        if raw:
            path = Path(raw)
            save_install_path(path)
            print(f"Saved install path: {path}")
            return path
        print("Path cannot be empty. Please try again.")


def get_install_path() -> Path:
    """Return the saved install path, prompting the user if not yet set.

    On the first run the user is prompted once and the answer is saved to
    ``launcher/config.toml``.  Every subsequent run reloads that value
    without prompting.
    """
    saved = load_saved_install_path()
    if saved is not None:
        return saved
    return prompt_for_install_path()
