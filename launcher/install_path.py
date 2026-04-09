"""Install path management for the M12 Labs launcher.

Prompts the user for the panel install location on first run and saves it for
reuse on all subsequent runs.  The value is stored as plain text under the
user's XDG-compatible config directory so no hardcoded paths are ever needed.
"""

from __future__ import annotations

from pathlib import Path

EXAMPLE_PATH = "/var/www/m12labs"

_CONFIG_DIR = Path.home() / ".config" / "m12labs"
_CONFIG_FILE = _CONFIG_DIR / "install_path"


def load_saved_install_path() -> Path | None:
    """Return the previously saved install path, or None if not set."""
    try:
        text = _CONFIG_FILE.read_text(encoding="utf-8").strip()
        if text:
            return Path(text)
    except OSError:
        pass
    return None


def save_install_path(path: Path) -> None:
    """Persist the install path so future runs do not prompt again."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(str(path) + "\n", encoding="utf-8")


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

    On the first run the user is prompted once and the answer is saved.
    Every subsequent run reloads the saved value without prompting.
    """
    saved = load_saved_install_path()
    if saved is not None:
        return saved
    return prompt_for_install_path()
