"""Config management for the M12 Labs launcher.

Reads and writes ``config.toml`` located in the same directory as this file.
Creates the file with sensible defaults when it does not exist yet.

File format (TOML)::

    install_path = "/var/www/m12labs"
    show_detailed_checks = false
    build_on_update = false
    build_on_uninstall = false
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

EXAMPLE_PATH = "/var/www/m12labs"

# Config file lives next to this source file so it stays with the launcher.
_CONFIG_FILE = Path(__file__).parent / "config.toml"


@dataclass
class Config:
    install_path: Path | None = None
    show_detailed_checks: bool = False
    build_on_update: bool = False
    build_on_uninstall: bool = False


def load_config() -> Config:
    """Load config from ``config.toml``, returning defaults if missing or invalid."""
    try:
        with _CONFIG_FILE.open("rb") as fh:
            data = tomllib.load(fh)
    except OSError:
        return Config()

    install_path_str = data.get("install_path", "").strip()
    return Config(
        install_path=Path(install_path_str) if install_path_str else None,
        show_detailed_checks=bool(data.get("show_detailed_checks", False)),
        build_on_update=bool(data.get("build_on_update", False)),
        build_on_uninstall=bool(data.get("build_on_uninstall", False)),
    )


def save_config(config: Config) -> None:
    """Write all config fields to ``config.toml``."""
    install_path_value = str(config.install_path) if config.install_path is not None else ""
    lines = [
        f'install_path = "{install_path_value}"',
        f"show_detailed_checks = {str(config.show_detailed_checks).lower()}",
        f"build_on_update = {str(config.build_on_update).lower()}",
        f"build_on_uninstall = {str(config.build_on_uninstall).lower()}",
    ]
    _CONFIG_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def prompt_for_install_path(config: Config) -> Config:
    """Prompt the user for the panel install path, persist and return updated config."""
    if config.install_path is None:
        print("\nPanel install location has not been configured yet.")
    else:
        print(f"\nCurrent install path: {config.install_path}")
    print(f"  Example: {EXAMPLE_PATH}")
    while True:
        raw = input("Enter panel install path: ").strip()
        if raw:
            config.install_path = Path(raw)
            save_config(config)
            print(f"Saved install path: {config.install_path}")
            return config
        print("Path cannot be empty. Please try again.")


def ensure_install_path(config: Config) -> Config:
    """Return config with ``install_path`` set, prompting the user if not yet configured."""
    if config.install_path is not None:
        return config
    return prompt_for_install_path(config)
