#!/usr/bin/env python3
"""M12Labs panel setup – interactive menu-driven installer.

Can be invoked in any of these ways::

    # From the repo root:
    python3 -m setup.main
    python3 setup/main.py
    bash setup.sh

    # From inside the setup/ directory:
    python3 main.py

Flow:
  1. Prompt for the panel install directory.
  2. Inspect the directory and classify it as:
       - existing install  (.env present + panel files)
       - partial setup     (panel files present, .env missing)
       - fresh target      (no panel files; usable for a new install)
  3. Show menu:  1) Install  2) Update  3) Uninstall  4) Database Tools
  4. Execute the chosen action.

Security:
    The database password is NEVER written to ``setup/config.toml`` or
    to any other file on disk by this module.  It exists only in memory
    during the run and is written once into the panel's ``.env``.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Ensure the repo root is on sys.path so that setup.* imports work
# regardless of the current working directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ─────────────────────────────────────────────────── platform helpers ──── #

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


# ──────────────────────────────────────────────────── directory prompt ──── #

def _prompt_install_dir(cfg):
    """Prompt for the panel install directory and persist the choice.

    Returns the updated config object.
    """
    from setup.config import DEFAULT_INSTALL_PATH, save_config

    default = cfg.install_path or DEFAULT_INSTALL_PATH
    print(f"\nPanel install directory (default: {default}):")
    try:
        raw = input(f"  Enter path [press Enter for {default}]: ").strip()
    except EOFError:
        raw = ""
    cfg.install_path = Path(raw) if raw else default
    save_config(cfg)
    return cfg


# ──────────────────────────────────────────────────── state detection ──── #

def _print_state_banner(install_path: Path, state: str) -> None:
    """Print a human-readable description of the detected panel state."""
    print()
    if state == "existing":
        from setup.steps.files import read_installed_version
        ver = read_installed_version(install_path)
        ver_label = f"v{ver}" if ver else "unknown version"
        print(f"  ✓ Existing M12Labs panel detected at {install_path} ({ver_label}).")
    elif state == "partial":
        print(f"  ⚠  Partial/incomplete panel setup detected at {install_path}.")
        print("     Some panel files are present but .env is missing.")
        print("     Consider running Install to complete setup, or investigate first.")
    else:
        if install_path.is_dir():
            print(f"  • Directory exists at {install_path} (no panel files found).")
        else:
            print(f"  • Fresh install target: {install_path} (directory will be created).")


# ──────────────────────────────────────────────────────── main menu ──── #

def _show_menu() -> str:
    """Display the main menu and return the user's choice."""
    print()
    print("  Main Menu:")
    print("  ─────────────────────────────")
    print("  1) Install")
    print("  2) Update")
    print("  3) Uninstall  (coming soon)")
    print("  4) Database Tools")
    print("  q) Quit")
    print()
    try:
        choice = input("  Select an option [1/2/3/4/q]: ").strip().lower()
    except EOFError:
        choice = "q"
    return choice


# ──────────────────────────────────────────── database tools sub-menu ──── #

def _db_test_connection(install_path: Path) -> None:
    """Test the database connection using credentials from the panel's .env."""
    from setup.config import read_db_credentials_from_env
    from setup.steps.database import check_db_connection
    from setup.system import read_env_value

    env_path = install_path / ".env"
    if not env_path.exists():
        print("  .env file not found – cannot load database credentials.")
        return

    creds = read_db_credentials_from_env(env_path)
    db_host = read_env_value(env_path, "DB_HOST") or "127.0.0.1"
    db_port = read_env_value(env_path, "DB_PORT") or "3306"

    if not creds["db_pass"]:
        print("  DB_PASSWORD not found in .env – cannot test connection.")
        return

    print(
        f"  Testing connection: "
        f"{creds['db_user']}@{db_host}:{db_port}/{creds['db_name']} …"
    )
    ok = check_db_connection(
        db_host=db_host,
        db_port=db_port,
        db_name=creds["db_name"],
        db_user=creds["db_user"],
        db_pass=creds["db_pass"],
    )
    if ok:
        print("  ✓ Database connection successful.")
    else:
        print("  ✗ Database connection failed.")
        print(
            "    Check that MariaDB/MySQL is running and the credentials"
            " in .env are correct."
        )


def _db_check_service() -> None:
    """Optionally check whether the MariaDB service is running (diagnostic only)."""
    print("  Checking MariaDB service status…")
    if not shutil.which("systemctl"):
        print("  systemctl not found – cannot check service status.")
        return
    result = subprocess.run(
        ["systemctl", "status", "mariadb"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("  ✓ MariaDB service is running.")
    else:
        print("  ✗ MariaDB service does not appear to be running.")
        print("    To start it: sudo systemctl start mariadb")
    # Show a concise excerpt of the status output for context
    lines = (result.stdout or result.stderr or "").splitlines()
    for line in lines[:10]:
        print(f"    {line}")


def _database_tools(install_path: Path) -> None:
    """Database Tools sub-menu."""
    while True:
        print()
        print("  Database Tools:")
        print("  ─────────────────────────────")
        print("  1) Test database connection  (uses .env credentials)")
        print("  2) Check MariaDB service status")
        print("  b) Back to main menu")
        print()
        try:
            choice = input("  Select an option [1/2/b]: ").strip().lower()
        except EOFError:
            break

        if choice == "1":
            _db_test_connection(install_path)
        elif choice == "2":
            _db_check_service()
        elif choice in ("b", "back", "q"):
            break
        else:
            print("  Invalid option. Please enter 1, 2, or b.")


# ──────────────────────────────────────────────────── install / update ──── #

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


def _run_install(cfg) -> int:
    """Run the full interactive install walkthrough.

    Returns:
        ``0`` on success, ``1`` on failure.
    """
    from setup.config import prompt_for_db_config, prompt_for_release
    from setup.log import get_logger, setup_logging
    from setup.steps.deps import install_dependencies
    from setup.steps.files import clone_panel, download_panel
    from setup.steps.releases import DEVELOP_BRANCH_TAG
    from setup.steps.database import setup_database
    from setup.steps.laravel import configure_laravel
    from setup.steps.workers import configure_workers

    # If .env already exists, prompt_for_db_config will offer to reuse it.
    cfg = prompt_for_release(cfg)
    cfg, db_pass = prompt_for_db_config(cfg)

    is_develop = cfg.selected_release == DEVELOP_BRANCH_TAG

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


def _run_update(cfg) -> int:
    """Run the minimal update flow for an existing panel installation.

    * Loads database credentials from the panel's ``.env`` (does not prompt).
    * Validates the DB connection before proceeding.
    * If the connection check fails, the user is directed to Database Tools.
    * Does NOT prompt the user to modify database credentials.

    Args:
        cfg: :class:`~setup.config.InstallConfig` with ``install_path`` set.

    Returns:
        ``0`` on success, ``1`` on failure.
    """
    from setup.config import read_db_credentials_from_env, prompt_for_release
    from setup.log import get_logger, setup_logging
    from setup.steps.files import clone_panel, download_panel
    from setup.steps.laravel import artisan, update_laravel
    from setup.steps.releases import DEVELOP_BRANCH_TAG
    from setup.steps.database import check_db_connection
    from setup.system import read_env_value

    install_path: Path = cfg.install_path
    env_path = install_path / ".env"

    # ── Validate existing DB credentials before modifying anything ── #
    if env_path.exists():
        creds = read_db_credentials_from_env(env_path)
        db_host = read_env_value(env_path, "DB_HOST") or "127.0.0.1"
        db_port = read_env_value(env_path, "DB_PORT") or "3306"

        if creds["db_pass"]:
            print(
                f"\n  Checking database connection "
                f"({creds['db_user']}@{db_host}:{db_port}/{creds['db_name']})…"
            )
            ok = check_db_connection(
                db_host=db_host,
                db_port=db_port,
                db_name=creds["db_name"],
                db_user=creds["db_user"],
                db_pass=creds["db_pass"],
            )
            if ok:
                print("  ✓ Database connection successful.")
                # Update cfg so logs show the correct DB info
                if creds["db_name"]:
                    cfg.db_name = creds["db_name"]
                if creds["db_user"]:
                    cfg.db_user = creds["db_user"]
            else:
                print("  ✗ Database connection check failed.")
                print(
                    "  To investigate or repair the database, choose"
                    " 'Database Tools' from the main menu."
                )
                print("  Update has been cancelled.")
                return 1
        else:
            print("  Note: DB credentials not found in .env – skipping database check.")
    else:
        print("  Note: .env not found – skipping database check.")

    # ── Confirm before proceeding ── #
    try:
        answer = input("\n  Continue with update? [y/N]: ").strip().lower()
    except EOFError:
        answer = ""
    if answer != "y":
        print("\nUpdate cancelled – no changes were made.")
        return 0

    cfg = prompt_for_release(cfg)
    is_develop = cfg.selected_release == DEVELOP_BRANCH_TAG

    setup_logging(cfg.install_path, cfg.text_logs_enabled)
    logger = get_logger()
    logger.info(
        "Update started: install_path=%s, release=%s",
        cfg.install_path,
        cfg.selected_release or "(default)",
    )

    print()
    print("Starting update.  This will take a few minutes.")
    print()

    # Put the application into maintenance mode (best-effort)
    print("  Putting application into maintenance mode…")
    if not artisan(install_path, "down"):
        logger.warning("artisan down failed – continuing with update")
        print(
            "  Warning: could not put application into maintenance mode – continuing."
        )

    # Fetch and replace panel files
    if is_develop:
        if not clone_panel(install_path):
            logger.error("Update aborted: file update (clone) failed")
            print("\n✗ Update failed at file download step. See output above.")
            if not artisan(install_path, "up"):
                print(
                    "  Warning: could not bring application back online"
                    " – run `php artisan up` manually."
                )
            return 1
    elif not download_panel(install_path, release_url=cfg.selected_release_url or None):
        logger.error("Update aborted: file download failed")
        print("\n✗ Update failed at file download step. See output above.")
        if not artisan(install_path, "up"):
            print(
                "  Warning: could not bring application back online"
                " – run `php artisan up` manually."
            )
        return 1

    # Minimal Laravel refresh (composer, caches, migrations, chown, artisan up)
    if not update_laravel(install_path):
        logger.error("Update aborted: Laravel refresh failed")
        print("\n✗ Update failed at Laravel refresh step. See output above.")
        return 1

    logger.info("Update completed successfully: install_path=%s", install_path)
    width = 60
    print("\n" + "─" * width)
    print("  M12Labs panel update complete!")
    print("─" * width)
    print(f"  Install path : {install_path}")
    print("─" * width)
    return 0


# ─────────────────────────────────────────────────────── entry point ──── #

def main() -> int:
    """Main entry point – interactive menu-driven installer.

    Returns:
        ``0`` on success / clean exit, ``1`` on failure.
    """
    from setup.config import load_config
    from setup.steps.files import detect_panel_state

    print("=" * 60)
    print("  M12Labs Panel Setup – Interactive Installer")
    print("=" * 60)
    print()

    if not _ensure_linux():
        return 1

    _warn_if_not_privileged()

    # Step 1: Load persisted config, then prompt for the install directory.
    cfg = load_config()
    cfg = _prompt_install_dir(cfg)
    install_path: Path = cfg.install_path

    # Step 2: Detect what already exists at the chosen path.
    state = detect_panel_state(install_path)
    _print_state_banner(install_path, state)

    # Step 3: Menu loop.
    while True:
        choice = _show_menu()

        if choice == "1":
            return _run_install(cfg)

        elif choice == "2":
            if state == "fresh":
                print()
                print("  ⚠  Update requires an existing installation, but none was")
                print(f"  detected at {install_path}.")
                print("  Please use 'Install' (option 1) to set up a new panel.")
            else:
                return _run_update(cfg)

        elif choice == "3":
            print()
            print("  Uninstall is not yet implemented.")
            print("  (This feature is coming in a future release.)")

        elif choice == "4":
            _database_tools(install_path)

        elif choice in ("q", "quit", "exit"):
            print("\nExiting installer. No changes were made.")
            return 0

        else:
            print("  Invalid option. Please enter 1, 2, 3, 4, or q.")


if __name__ == "__main__":
    sys.exit(main())

