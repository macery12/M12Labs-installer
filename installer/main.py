#!/usr/bin/env python3
"""M12Labs panel setup – interactive menu-driven installer."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# platform helpers

def _ensure_linux() -> bool:
    if platform.system().lower() != "linux":
        print("This installer supports Linux only.")
        print(f"Detected platform: {platform.system()}")
        return False
    return True


def _warn_if_not_privileged() -> None:
    try:
        is_root = os.geteuid() == 0
    except AttributeError:
        is_root = False
    if not is_root and not shutil.which("sudo"):
        print(
            "\nWarning: you are not running as root and sudo is not available."
            "\nSome steps (package installation, systemd, chown) may fail."
        )


def _pause_and_clear() -> None:
    try:
        input("\n  Press Enter to continue…")
    except EOFError:
        pass
    os.system("clear")


# directory prompt

def _prompt_install_dir(cfg):
    from installer.config import DEFAULT_INSTALL_PATH, save_config

    default = cfg.install_path or DEFAULT_INSTALL_PATH
    print(f"\nPanel install directory (default: {default}):")
    try:
        raw = input(f"  Enter path [press Enter for {default}]: ").strip()
    except EOFError:
        raw = ""
    cfg.install_path = Path(raw) if raw else default
    save_config(cfg)
    return cfg


# state detection

def _print_state_banner(install_path: Path, state: str) -> None:
    print()
    if state == "existing":
        from installer.steps.files import read_installed_version
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


# main menu

def _show_menu() -> str:
    print()
    print("  Main Menu:")
    print("  ─────────────────────────────")
    print("  1) Install")
    print("  2) Update")
    print("  3) Uninstall  (coming soon)")
    print("  4) Database Tools")
    print("  5) Webserver")
    print("  q) Quit")
    print()
    try:
        choice = input("  Select an option [1/2/3/4/5/q]: ").strip().lower()
    except EOFError:
        choice = "q"
    return choice


# database tools sub-menu

def _db_test_connection(install_path: Path) -> None:
    from installer.config import read_db_credentials_from_env
    from installer.steps.database import check_db_connection
    from installer.system import read_env_value

    env_path = install_path / ".env"
    if not env_path.exists():
        print("  .env file not found – cannot load database credentials.")
        _pause_and_clear()
        return

    creds = read_db_credentials_from_env(env_path)
    db_host = read_env_value(env_path, "DB_HOST") or "127.0.0.1"
    db_port = read_env_value(env_path, "DB_PORT") or "3306"

    if not creds["db_pass"]:
        print("  DB_PASSWORD not found in .env – cannot test connection.")
        _pause_and_clear()
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
    _pause_and_clear()


def _db_check_service() -> None:
    print("  Checking MariaDB service status…")
    if not shutil.which("systemctl"):
        print("  systemctl not found – cannot check service status.")
        _pause_and_clear()
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
    lines = (result.stdout or result.stderr or "").splitlines()
    for line in lines[:10]:
        print(f"    {line}")
    _pause_and_clear()


def _database_tools(install_path: Path) -> None:
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


# webserver sub-menu

def _webserver_menu(install_path: Path) -> None:
    while True:
        print()
        print("  Webserver:")
        print("  ─────────────────────────────")
        print("  1) NGINX")
        print("  0) Back")
        print()
        try:
            choice = input("  Select an option [1/0]: ").strip().lower()
        except EOFError:
            break

        if choice == "1":
            from installer.steps.nginx import configure_nginx
            configure_nginx(install_path)
            _pause_and_clear()
        elif choice in ("0", "b", "back", "q"):
            break
        else:
            print("  Invalid option. Please enter 1 or 0.")


# backup prompt

def _prompt_backup_before_update(install_path: Path) -> bool:
    """Prompt the user to create a backup before updating.

    Returns True if the update should proceed, False if it should be
    aborted.
    """
    from installer.backup.backup import create_backup

    print()
    print("  ─────────────────────────────────────────────────────")
    print("  ⚠  Backup recommended")
    print("  ─────────────────────────────────────────────────────")
    print("  It is strongly recommended to create a backup of the")
    print("  panel before updating, in case something goes wrong.")
    print()

    try:
        answer = input(
            "  Would you like to back up now? [Y/n]: "
        ).strip().lower()
    except EOFError:
        answer = "y"

    wants_backup = answer in ("", "y", "yes")

    if wants_backup:
        backups_dir = install_path.parent / "m12labs_backups"
        print(f"\n  Creating backup in {backups_dir} …")
        try:
            archive = create_backup(install_path, backups_dir)
            print(f"  ✓ Backup created: {archive}")
            print()
            return True
        except NotImplementedError:
            print()
            print("  ℹ  Automatic backup is not yet available in this version.")
            print("  Please back up the panel manually before continuing.")
            print(f"  (Panel directory: {install_path})")
            print()
        except Exception as exc:  # pylint: disable=broad-except
            print()
            print(f"  ✗ Backup failed: {exc}")
            print()
            try:
                proceed = input(
                    "  The backup could not be created. Continue without a backup? [y/N]: "
                ).strip().lower()
            except EOFError:
                proceed = "n"

            if proceed not in ("y", "yes"):
                print("  Update cancelled. Please resolve the backup issue first.")
                return False
            print()
            return True

    # User declined or backup not available – ask for explicit confirmation
    print("  Continuing without a backup may be risky.")
    print("  If the update fails you may not be able to roll back easily.")
    print()
    try:
        confirm = input(
            "  Are you sure you want to continue WITHOUT a backup? [y/N]: "
        ).strip().lower()
    except EOFError:
        confirm = "n"

    if confirm not in ("y", "yes"):
        print("\n  Update cancelled.")
        return False

    print()
    return True


# install / update

def _print_final_summary(install_path: Path, db_name: str, db_user: str) -> None:
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
    from installer.config import prompt_for_db_config, prompt_for_release
    from installer.log import get_logger, setup_logging
    from installer.steps.deps import install_dependencies
    from installer.steps.files import clone_panel, download_panel
    from installer.steps.releases import DEVELOP_BRANCH_TAG
    from installer.steps.database import setup_database
    from installer.steps.laravel import configure_laravel
    from installer.steps.workers import configure_workers

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

    if not install_dependencies():
        logger.error("Install aborted: Step 1 (dependencies) failed")
        print("\n✗ Installation failed at Step 1. See output above.")
        return 1

    if is_develop:
        if not clone_panel(install_path):
            logger.error("Install aborted: Step 2 (clone) failed")
            print("\n✗ Installation failed at Step 2. See output above.")
            return 1
    elif not download_panel(install_path, release_url=cfg.selected_release_url or None):
        logger.error("Install aborted: Step 2 (download) failed")
        print("\n✗ Installation failed at Step 2. See output above.")
        return 1

    if not setup_database(cfg.db_name, cfg.db_user, db_pass):
        logger.error("Install aborted: Step 3 (database) failed")
        print("\n✗ Installation failed at Step 3. See output above.")
        return 1

    if not configure_laravel(install_path, cfg.db_name, cfg.db_user, db_pass):
        logger.error("Install aborted: Step 4 (Laravel) failed")
        print("\n✗ Installation failed at Step 4. See output above.")
        db_pass = ""
        return 1

    db_pass = ""

    if not configure_workers(install_path):
        logger.error("Install aborted: Step 5 (workers) failed")
        print("\n✗ Installation failed at Step 5. See output above.")
        return 1

    logger.info("Install completed successfully: install_path=%s", install_path)
    _print_final_summary(install_path, cfg.db_name, cfg.db_user)
    return 0


def _run_update(cfg) -> int:
    from installer.config import read_db_credentials_from_env, prompt_for_release
    from installer.log import get_logger, setup_logging
    from installer.steps.files import clone_panel, download_panel, read_installed_version
    from installer.steps.laravel import artisan, update_laravel
    from installer.steps.releases import DEVELOP_BRANCH_TAG
    from installer.steps.database import check_db_connection
    from installer.system import read_env_value

    install_path: Path = cfg.install_path
    env_path = install_path / ".env"

    # db check before touching anything
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
                _pause_and_clear()
                return 1
        else:
            print("  Note: DB credentials not found in .env – skipping database check.")
    else:
        print("  Note: .env not found – skipping database check.")

    # pause after db check so the user can read the result
    _pause_and_clear()

    # backup prompt
    if not _prompt_backup_before_update(install_path):
        return 0

    # release selection
    old_ver = read_installed_version(install_path)
    cfg = prompt_for_release(cfg)
    is_develop = cfg.selected_release == DEVELOP_BRANCH_TAG
    new_ver_label = "develop branch" if is_develop else (cfg.selected_release or "latest")

    # confirmation screen
    width = 60
    print()
    print("─" * width)
    print("  Update confirmation")
    print("─" * width)
    print(f"  Install path    : {install_path}")
    print(f"  Current version : {f'v{old_ver}' if old_ver else 'unknown'}")
    print(f"  New version     : {new_ver_label}")
    print("─" * width)
    print()
    print("  Press Enter to start the update, or Ctrl+C to cancel.")
    try:
        input("  > ")
    except (EOFError, KeyboardInterrupt):
        print("\n\nUpdate cancelled – no changes were made.")
        return 0

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

    # maintenance mode
    print("  Putting application into maintenance mode…")
    if not artisan(install_path, "down"):
        logger.warning("artisan down failed – continuing with update")
        print(
            "  Warning: could not put application into maintenance mode – continuing."
        )

    # fetch and replace panel files
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

    # laravel refresh
    if not update_laravel(install_path):
        logger.error("Update aborted: Laravel refresh failed")
        print("\n✗ Update failed at Laravel refresh step. See output above.")
        return 1

    # read the version now on disk to confirm the update landed
    installed_ver = read_installed_version(install_path)
    installed_label = f"v{installed_ver}" if installed_ver else "unknown"

    logger.info("Update completed successfully: install_path=%s", install_path)
    print("\n" + "─" * width)
    print("  M12Labs panel update complete!")
    print("─" * width)
    print(f"  Install path      : {install_path}")
    print(f"  Installed version : {installed_label}")
    print("─" * width)
    return 0


# entry point

def main() -> int:
    from installer.config import load_config
    from installer.steps.files import detect_panel_state

    print("=" * 60)
    print("  M12Labs Panel Setup – Interactive Installer")
    print("=" * 60)
    print()

    if not _ensure_linux():
        return 1

    _warn_if_not_privileged()

    cfg = load_config()
    cfg = _prompt_install_dir(cfg)
    install_path: Path = cfg.install_path

    state = detect_panel_state(install_path)
    _print_state_banner(install_path, state)

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

        elif choice == "5":
            _webserver_menu(install_path)

        elif choice in ("q", "quit", "exit"):
            print("\nExiting installer. No changes were made.")
            return 0

        else:
            print("  Invalid option. Please enter 1, 2, 3, 4, 5, or q.")


if __name__ == "__main__":
    sys.exit(main())
