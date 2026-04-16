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
    print("  6) Manage Backups")
    print("  q) Quit")
    print()
    try:
        choice = input("  Select an option [1/2/3/4/5/6/q]: ").strip().lower()
    except EOFError:
        choice = "q"
    return choice


# database tools sub-menu

def _db_test_connection(install_path: Path) -> None:
    from installer.config import read_db_credentials_from_env
    from installer.steps.database import check_credentials, database_exists, setup_database
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

    db_name = creds["db_name"]
    db_user = creds["db_user"]
    db_pass = creds["db_pass"]

    # Step 1: validate credentials without requiring the database to exist.
    print(f"  Checking credentials: {db_user}@{db_host}:{db_port} …")
    auth_ok = check_credentials(
        db_host=db_host,
        db_port=db_port,
        db_user=db_user,
        db_pass=db_pass,
    )
    if not auth_ok:
        print("  ✗ Authentication failed.")
        print("    Check that MariaDB/MySQL is running and that the")
        print("    credentials in .env are correct.")
        _pause_and_clear()
        return

    # Step 2: check whether the target database actually exists (read-only).
    print(f"  ✓ Credentials valid. Checking database '{db_name}' …")
    exists = database_exists(
        db_host=db_host,
        db_port=db_port,
        db_name=db_name,
        db_user=db_user,
        db_pass=db_pass,
    )
    if exists:
        print("  ✓ Database connection successful.")
        _pause_and_clear()
        return

    # Database is missing – inform the user and ask whether to create it.
    print(f"  Database '{db_name}' does not exist under these credentials.")
    print("  Would you like to create it?")
    try:
        answer = input("  Create database? [y/N]: ").strip().lower()
    except EOFError:
        answer = "n"

    if answer in ("y", "yes"):
        if setup_database(db_name, db_user, db_pass):
            print("  ✓ Database created successfully.")
        else:
            print("  ✗ Database creation failed. See output above.")
    else:
        print("  No changes made.")
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
    from installer.backup.backup import create_backup, DEFAULT_BACKUPS_DIR

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
        print(f"\n  Creating backup in {DEFAULT_BACKUPS_DIR} …")
        try:
            archive = create_backup(install_path)
            print(f"  ✓ Backup created: {archive}")
            print()
            return True
        except Exception as exc:  # pylint: disable=broad-except
            print()
            print(f"  ✗ Backup failed: {exc}")
            print("    (Check disk space, permissions, and that the install path exists.)")
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

    # User declined – ask for explicit confirmation
    print("  Continuing without a backup may be risky.")
    print("  If the update fails you may not be able to rollback easily.")
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


# manage backups sub-menu

def _fmt_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _fmt_backup_label(path: "Path") -> str:
    """Return a human-readable label for a backup archive.

    Parses the ``YYYYMMDD_HHMMSS`` stamp embedded in the filename and
    formats it as ``YYYY-MM-DD HH:MM:SS UTC``.  Falls back to the raw
    filename if the stamp cannot be parsed.
    """
    import re, datetime as _dt
    m = re.search(r"(\d{8})_(\d{6})", path.stem)
    if m:
        try:
            dt = _dt.datetime.strptime(
                f"{m.group(1)}_{m.group(2)}", "%Y%m%d_%H%M%S"
            ).replace(tzinfo=_dt.timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except ValueError:
            pass
    return path.name


def _manage_backups_menu(install_path: Path) -> None:
    from installer.backup.backup import (
        DEFAULT_BACKUPS_DIR,
        delete_backup,
        list_backups,
        restore_backup,
    )

    while True:
        backups = list_backups()

        print()
        print("  Manage Backups:")
        print("  ─────────────────────────────")

        if not backups:
            print(f"  No backups found in {DEFAULT_BACKUPS_DIR}")
        else:
            print(f"  Stored in: {DEFAULT_BACKUPS_DIR}")
            print()
            for idx, path in enumerate(backups, start=1):
                size = _fmt_size(path.stat().st_size)
                label = _fmt_backup_label(path)
                print(f"  {idx}) {label}  ({size})")

        print()
        print("  d) Delete a backup")
        print("  r) Restore a backup")
        print("  b) Back to main menu")
        print()

        try:
            choice = input("  Select an option: ").strip().lower()
        except EOFError:
            break

        if choice in ("b", "back", "q"):
            break

        elif choice == "d":
            if not backups:
                print("  No backups to delete.")
                continue
            try:
                raw = input(
                    f"  Enter backup number to delete [1-{len(backups)}]: "
                ).strip()
            except EOFError:
                continue
            if not raw.isdigit() or not (1 <= int(raw) <= len(backups)):
                print("  Invalid selection.")
                continue
            target = backups[int(raw) - 1]
            try:
                confirm = input(
                    f"  Delete {target.name}? [y/N]: "
                ).strip().lower()
            except EOFError:
                confirm = "n"
            if confirm in ("y", "yes"):
                delete_backup(target)
                print(f"  ✓ Deleted {target.name}")
            else:
                print("  Deletion cancelled.")

        elif choice == "r":
            if not backups:
                print("  No backups available to restore.")
                continue
            try:
                raw = input(
                    f"  Enter backup number to restore [1-{len(backups)}]: "
                ).strip()
            except EOFError:
                continue
            if not raw.isdigit() or not (1 <= int(raw) <= len(backups)):
                print("  Invalid selection.")
                continue
            target = backups[int(raw) - 1]
            print()
            print(f"  ⚠  This will overwrite the current panel at {install_path}")
            print(f"     with the contents of {target.name}.")
            print()
            try:
                confirm = input(
                    "  Are you sure you want to restore this backup? [y/N]: "
                ).strip().lower()
            except EOFError:
                confirm = "n"
            if confirm not in ("y", "yes"):
                print("  Restore cancelled.")
                continue
            print(f"\n  Restoring {target.name} …")
            try:
                restore_backup(target, install_path)
                print("  ✓ Restore complete.")
            except Exception as exc:  # pylint: disable=broad-except
                print(f"  ✗ Restore failed: {exc}")
                print("    (Check permissions and available disk space.)")
            _pause_and_clear()

        else:
            print("  Invalid option. Please enter d, r, or b.")


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


def _run_install_manual(cfg) -> int | None:
    """Manual install: numbered stage list – the user picks stages to run one at a time.

    Returns an exit code (0 = success, 1 = failure) or ``None`` when the
    user goes back to the install submenu without completing the install.
    """
    from installer.config import prompt_for_db_config, prompt_for_release
    from installer.log import get_logger, setup_logging
    from installer.steps.deps import install_dependencies
    from installer.steps.files import clone_panel, download_panel
    from installer.steps.releases import DEVELOP_BRANCH_TAG
    from installer.steps.database import check_credentials, database_exists, setup_database
    from installer.steps.laravel import configure_laravel
    from installer.steps.workers import configure_workers
    from installer.system import read_env_value

    cfg = prompt_for_release(cfg)
    cfg, db_pass, reused_creds = prompt_for_db_config(cfg)

    is_develop = cfg.selected_release == DEVELOP_BRANCH_TAG
    setup_logging(cfg.install_path, cfg.text_logs_enabled)
    logger = get_logger()
    install_path: Path = cfg.install_path

    logger.info(
        "Manual install started: install_path=%s, release=%s",
        install_path,
        cfg.selected_release or "(default)",
    )

    STAGES = [
        "Install system dependencies",
        "Download panel files",
        "Set up database",
        "Configure Laravel",
        "Configure workers",
    ]
    completed = [False] * len(STAGES)

    while True:
        print()
        print("  Manual Install – select a stage to run:")
        print("  ─────────────────────────────────────────")
        for i, (label, done) in enumerate(zip(STAGES, completed), start=1):
            mark = "✓" if done else " "
            print(f"  {i}) [{mark}] {label}")
        print("  0) Done / Back")
        print()
        try:
            choice = input(f"  Select stage [1-{len(STAGES)}/0]: ").strip()
        except EOFError:
            db_pass = ""
            return None

        if choice == "0":
            db_pass = ""
            if all(completed):
                logger.info("Manual install completed: install_path=%s", install_path)
                _print_final_summary(install_path, cfg.db_name, cfg.db_user)
                return 0
            return None

        if not choice.isdigit() or not (1 <= int(choice) <= len(STAGES)):
            print(f"  Invalid option. Please enter 1–{len(STAGES)} or 0.")
            continue

        stage_idx = int(choice) - 1
        stage_num = stage_idx + 1
        print(f"\n  ─── Stage {stage_num}: {STAGES[stage_idx]} ───")

        if stage_idx == 0:
            if install_dependencies():
                completed[0] = True
                print("  ✓ Stage 1 complete.")
            else:
                logger.error("Manual install: Stage 1 (dependencies) failed")
                print("  ✗ Stage 1 failed. See output above.")

        elif stage_idx == 1:
            if is_develop:
                ok = clone_panel(install_path)
            else:
                ok = download_panel(install_path, release_url=cfg.selected_release_url or None)
            if ok:
                completed[1] = True
                print("  ✓ Stage 2 complete.")
            else:
                logger.error("Manual install: Stage 2 (files) failed")
                print("  ✗ Stage 2 failed. See output above.")

        elif stage_idx == 2:
            if reused_creds:
                # Existing credentials chosen – verify credentials then confirm DB exists.
                env_path = install_path / ".env"
                db_host = read_env_value(env_path, "DB_HOST") or "127.0.0.1"
                db_port = read_env_value(env_path, "DB_PORT") or "3306"
                print(
                    f"  Reusing existing credentials – checking "
                    f"{cfg.db_user}@{db_host}:{db_port} …"
                )
                auth_ok = check_credentials(
                    db_host=db_host,
                    db_port=db_port,
                    db_user=cfg.db_user,
                    db_pass=db_pass,
                )
                if not auth_ok:
                    logger.error("Manual install: Stage 3 credential check failed")
                    print("  ✗ Authentication failed.")
                    print(
                        "    Check that MariaDB is running and the credentials"
                        " in .env are correct."
                    )
                elif not database_exists(
                    db_host=db_host,
                    db_port=db_port,
                    db_name=cfg.db_name,
                    db_user=cfg.db_user,
                    db_pass=db_pass,
                ):
                    logger.error(
                        "Manual install: Stage 3 – database '%s' not found", cfg.db_name
                    )
                    print(f"  ✗ Database '{cfg.db_name}' does not exist.")
                    print(
                        "    Run 'Set up database' without reusing credentials"
                        " to create it."
                    )
                else:
                    completed[2] = True
                    print("  ✓ Database connected.")
            else:
                if setup_database(cfg.db_name, cfg.db_user, db_pass):
                    completed[2] = True
                    print("  ✓ Stage 3 complete.")
                else:
                    logger.error("Manual install: Stage 3 (database) failed")
                    print("  ✗ Stage 3 failed. See output above.")

        elif stage_idx == 3:
            if configure_laravel(install_path, cfg.db_name, cfg.db_user, db_pass):
                completed[3] = True
                db_pass = ""  # written to .env; clear from memory
                print("  ✓ Stage 4 complete.")
            else:
                logger.error("Manual install: Stage 4 (Laravel) failed")
                print("  ✗ Stage 4 failed. See output above.")

        elif stage_idx == 4:
            if configure_workers(install_path):
                completed[4] = True
                print("  ✓ Stage 5 complete.")
            else:
                logger.error("Manual install: Stage 5 (workers) failed")
                print("  ✗ Stage 5 failed. See output above.")

        _pause_and_clear()


def _install_submenu(cfg) -> int | None:
    """Show the Install submenu (Automatic / Manual / Back).

    Returns an exit code when the install completes, or ``None`` when the
    user selects Back so the caller can return to the main menu.
    """
    while True:
        print()
        print("  Install:")
        print("  ─────────────────────────────")
        print("  1) Automatic")
        print("  2) Manual")
        print("  0) Back")
        print()
        try:
            choice = input("  Select an option [1/2/0]: ").strip().lower()
        except EOFError:
            return None

        if choice == "1":
            return _run_install(cfg)
        elif choice == "2":
            result = _run_install_manual(cfg)
            if result is None:
                # User quit from within the manual flow; go back to this submenu.
                continue
            return result
        elif choice in ("0", "b", "back", "q"):
            return None
        else:
            print("  Invalid option. Please enter 1, 2, or 0.")


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
    cfg, db_pass, _ = prompt_for_db_config(cfg)

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


def _prompt_manual_db_creds_for_update() -> dict[str, str]:
    """Prompt the user to enter database connection credentials manually.

    Used during the update flow when the user declines to use existing
    ``.env`` credentials or when no credentials are available.

    Returns a dict with keys ``db_host``, ``db_port``, ``db_name``,
    ``db_user``, and ``db_pass``.
    """
    print("\n  Enter database credentials for the connection check:")
    try:
        db_host = input("  DB host   [default: 127.0.0.1]: ").strip() or "127.0.0.1"
        db_port = input("  DB port   [default: 3306]:      ").strip() or "3306"
        db_name = input("  DB name:  ").strip()
        db_user = input("  DB user:  ").strip()
        db_pass = input("  DB pass:  ").strip()
    except EOFError:
        print("\n  (Input closed – skipping credential entry.)")
        db_host, db_port, db_name, db_user, db_pass = "127.0.0.1", "3306", "", "", ""
    return {
        "db_host": db_host,
        "db_port": db_port,
        "db_name": db_name,
        "db_user": db_user,
        "db_pass": db_pass,
    }


def _run_update(cfg) -> int:
    from installer.config import read_db_credentials_from_env, prompt_for_release
    from installer.log import get_logger, setup_logging
    from installer.steps.files import clone_panel, download_panel, read_installed_version
    from installer.steps.laravel import artisan, update_laravel
    from installer.steps.releases import DEVELOP_BRANCH_TAG
    from installer.steps.database import check_credentials, database_exists
    from installer.system import read_env_value

    install_path: Path = cfg.install_path
    env_path = install_path / ".env"

    # db check before touching anything
    if env_path.exists():
        creds = read_db_credentials_from_env(env_path)
        db_host = read_env_value(env_path, "DB_HOST") or "127.0.0.1"
        db_port = read_env_value(env_path, "DB_PORT") or "3306"

        if creds["db_pass"]:
            # Show the existing credentials and ask the user whether to use them.
            print(f"\n  Existing DB credentials found in {env_path}:")
            print(f"    DB name : {creds['db_name'] or '(empty)'}")
            print(f"    DB user : {creds['db_user'] or '(empty)'}")
            print(f"    DB host : {db_host}:{db_port}")
            print("    DB pass : (hidden)")
            try:
                answer = input("  Use these DB credentials? [Y/n]: ").strip().lower()
            except EOFError:
                answer = ""

            if answer not in ("n", "no"):
                # Use credentials from .env
                check_host = db_host
                check_port = db_port
                check_name = creds["db_name"]
                check_user = creds["db_user"]
                check_pass = creds["db_pass"]
                if check_name:
                    cfg.db_name = check_name
                if check_user:
                    cfg.db_user = check_user
            else:
                # User declined – allow manual entry before the check
                manual = _prompt_manual_db_creds_for_update()
                check_host = manual["db_host"]
                check_port = manual["db_port"]
                check_name = manual["db_name"]
                check_user = manual["db_user"]
                check_pass = manual["db_pass"]
        else:
            print("  Note: DB credentials not found in .env.")
            print("  Please enter credentials manually for the connection check.")
            manual = _prompt_manual_db_creds_for_update()
            check_host = manual["db_host"]
            check_port = manual["db_port"]
            check_name = manual["db_name"]
            check_user = manual["db_user"]
            check_pass = manual["db_pass"]

        if check_pass:
            print(
                f"\n  Checking credentials: "
                f"{check_user}@{check_host}:{check_port} …"
            )
            auth_ok = check_credentials(
                db_host=check_host,
                db_port=check_port,
                db_user=check_user,
                db_pass=check_pass,
            )
            if not auth_ok:
                check_pass = ""  # clear from memory
                print("  ✗ Authentication failed.")
                print(
                    "  To investigate or repair the database, choose"
                    " 'Database Tools' from the main menu."
                )
                print("  Update has been cancelled.")
                _pause_and_clear()
                return 1
            db_exists = database_exists(
                db_host=check_host,
                db_port=check_port,
                db_name=check_name,
                db_user=check_user,
                db_pass=check_pass,
            )
            check_pass = ""  # clear from memory
            if db_exists:
                print("  ✓ Database connection successful.")
            else:
                print(f"  ✗ Database '{check_name}' does not exist.")
                print(
                    "  To investigate or repair the database, choose"
                    " 'Database Tools' from the main menu."
                )
                print("  Update has been cancelled.")
                _pause_and_clear()
                return 1
        else:
            print("  Note: no DB password provided – skipping database check.")
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
        logger.error("Update aborted: could not put application into maintenance mode")
        print(
            "\n✗ Update aborted: could not put application into maintenance mode."
        )
        print(
            "  The application may already be down or PHP/artisan is unavailable."
        )
        print(
            "  Resolve the issue and try again, or run `php artisan down` manually"
            " before retrying."
        )
        return 1

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
            result = _install_submenu(cfg)
            if result is not None:
                return result
            # None means Back – redisplay the main menu.

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

        elif choice == "6":
            _manage_backups_menu(install_path)

        elif choice in ("q", "quit", "exit"):
            print("\nExiting installer. No changes were made.")
            return 0

        else:
            print("  Invalid option. Please enter 1, 2, 3, 4, 5, 6, or q.")


if __name__ == "__main__":
    sys.exit(main())
