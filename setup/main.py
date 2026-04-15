#!/usr/bin/env python3
"""M12Labs panel setup – interactive full-install walkthrough.

Can be invoked in any of these ways::

    # From the repo root:
    python3 -m setup.main
    python3 setup/main.py
    bash setup.sh

    # From inside the setup/ directory:
    python3 main.py

The installer will:
  1. Verify the platform is Linux.
  2. Load (or create) ``setup/config.toml`` with sensible defaults.
  3. Prompt for the panel install path.
  4. Prompt to select a release version (or develop branch).
  5. Prompt for DB name, DB user, and DB password (password held in memory only).
  6. Execute each install step in order, printing live progress.
  7. Print a final summary with NGINX / SSL reminders.

Security:
    The database password is NEVER written to ``setup/config.toml`` or
    to any other file on disk by this module.  It exists only in memory
    during the run and is written once into the panel's ``.env``.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path

# Ensure the repo root is on sys.path so that setup.* imports work
# regardless of the current working directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _ensure_linux() -> bool:
    if platform.system().lower() != "linux":
        print("This installer supports Linux only.")
        print(f"Detected platform: {platform.system()}")
        return False
    return True


def _warn_if_not_privileged() -> None:
    """Warn the user if they are not running as root or with sudo."""
    try:
        is_root = os.geteuid() == 0
    except AttributeError:
        is_root = False

    if not is_root and not shutil.which("sudo"):
        print(
            "\nWarning: you are not running as root and sudo is not available."
            "\nSome steps (package installation, systemd, chown) may fail."
        )


def _print_final_summary(install_path: Path, db_name: str, db_user: str) -> None:
    """Print the post-install summary and NGINX / SSL reminders."""
    width = 60
    print("\n" + "─" * width)
    print("  M12Labs panel installation complete!")
    print("─" * width)
    print(f"  Install path : {install_path}")
    print(f"  DB name      : {db_name}")
    print(f"  DB user      : {db_user}")
    print(f"  DB password  : (saved in {install_path / '.env'})")
    print("─" * width)
    print()
    print("  Next steps:")
    print()
    print("  1. Configure NGINX to serve the panel:")
    print(f"       root {install_path / 'public'};")
    print("       index index.php;")
    print("       (see M12Docs for a full NGINX server block example)")
    print()
    print("  2. Set up SSL (Let's Encrypt recommended):")
    print("       sudo apt-get install certbot python3-certbot-nginx")
    print("       sudo certbot --nginx -d your.domain.com")
    print()
    print("  3. Start / restart NGINX:")
    print("       sudo systemctl restart nginx")
    print()
    print("─" * width)


def full_install() -> int:
    """Run the complete interactive panel install walkthrough.

    Returns:
        ``0`` on success, ``1`` on failure.
    """
    # Deferred imports keep startup fast and allow the platform guard to run
    # before any setup-module code is imported.
    from setup.config import load_config, prompt_for_db_config, prompt_for_install_path, prompt_for_release
    from setup.log import get_logger, setup_logging
    from setup.steps.deps import install_dependencies
    from setup.steps.files import clone_panel, detect_existing_panel, download_panel, read_installed_version
    from setup.steps.releases import DEVELOP_BRANCH_TAG
    from setup.steps.database import setup_database
    from setup.steps.laravel import configure_laravel
    from setup.steps.workers import configure_workers

    print("=" * 60)
    print("  M12Labs Panel Setup – Interactive Installer")
    print("=" * 60)
    print()

    if not _ensure_linux():
        return 1

    _warn_if_not_privileged()

    # Config and prompts
    cfg = load_config()
    cfg = prompt_for_install_path(cfg)

    # Pre-flight: detect an existing panel installation and offer an update.
    if detect_existing_panel(cfg.install_path):
        installed_ver = read_installed_version(cfg.install_path)
        ver_label = f"v{installed_ver}" if installed_ver else "unknown version"
        print(f"\n  ⚠  M12Labs panel already detected at {cfg.install_path} ({ver_label}).")
        print("  Running the installer again will UPDATE the panel to your chosen version.")
        try:
            answer = input("  Continue with update? [y/N]: ").strip().lower()
        except EOFError:
            answer = ""
        if answer != "y":
            print("\nUpdate cancelled – no changes were made.")
            return 0

    cfg = prompt_for_release(cfg)
    cfg, db_pass = prompt_for_db_config(cfg)

    is_develop = cfg.selected_release == DEVELOP_BRANCH_TAG

    # Logging (after install_path is known)
    setup_logging(cfg.install_path, cfg.text_logs_enabled)
    logger = get_logger()
    logger.info(
        "Install started: install_path=%s, release=%s, db_name=%s, db_user=%s",
        cfg.install_path,
        cfg.selected_release or "(default)",
        cfg.db_name,
        cfg.db_user,
    )

    print()
    print("Starting installation.  This will take several minutes.")
    print("You will be prompted to answer artisan questions during Step 4.")
    print()

    install_path: Path = cfg.install_path

    # Step 1: System dependencies
    if not install_dependencies():
        logger.error("Install aborted: Step 1 (dependencies) failed")
        print("\n✗ Installation failed at Step 1. See output above.")
        return 1

    # Step 2: Obtain panel files
    if is_develop:
        if not clone_panel(install_path):
            logger.error("Install aborted: Step 2 (clone) failed")
            print("\n✗ Installation failed at Step 2. See output above.")
            return 1
    elif not download_panel(install_path, release_url=cfg.selected_release_url or None):
        logger.error("Install aborted: Step 2 (download) failed")
        print("\n✗ Installation failed at Step 2. See output above.")
        return 1

    # Step 3: Database setup
    if not setup_database(cfg.db_name, cfg.db_user, db_pass):
        logger.error("Install aborted: Step 3 (database) failed")
        print("\n✗ Installation failed at Step 3. See output above.")
        return 1

    # Step 4: Laravel environment
    if not configure_laravel(install_path, cfg.db_name, cfg.db_user, db_pass):
        logger.error("Install aborted: Step 4 (Laravel) failed")
        print("\n✗ Installation failed at Step 4. See output above.")
        # db_pass is no longer needed past this point; overwrite it in memory.
        db_pass = ""
        return 1

    # Overwrite the password in memory as soon as it is no longer needed.
    db_pass = ""

    # Step 5: Cron and queue worker
    if not configure_workers(install_path):
        logger.error("Install aborted: Step 5 (workers) failed")
        print("\n✗ Installation failed at Step 5. See output above.")
        return 1

    logger.info("Install completed successfully: install_path=%s", install_path)
    _print_final_summary(install_path, cfg.db_name, cfg.db_user)
    return 0


def main() -> int:
    return full_install()


if __name__ == "__main__":
    sys.exit(main())
