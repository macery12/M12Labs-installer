#!/usr/bin/env python3
"""Linux-first M12 Labs extension installer."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
from pathlib import Path

# Make the repo root available on sys.path so ``setup.*`` modules can be
# imported from within installer/main.py regardless of how Python was invoked.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backup import BackupEntry, create_backup, default_backups_dir, list_backups, restore_backup
from build import build_only as run_build_only
from check import (
    format_results,
    format_results_concise,
    has_failures,
    has_modified_files,
    run_checks,
)
from config import Config, ensure_install_path, load_config, prompt_for_install_path, save_config
from log import get_logger, setup_logging
from releases import (
    DEVELOP_BRANCH_TAG,
    DEVELOP_BRANCH_URL,
    Release,
    download_archive,
    extract_archive,
    fetch_releases,
    get_archive_url,
    prompt_release_selection,
)


def clear_screen() -> None:
    if sys.stdout.isatty() and os.getenv("TERM"):
        subprocess.run(["clear"], check=False)
    else:
        print("\n" * 2, end="")


def wait_for_enter() -> None:
    input("\nPress Enter to continue...")


def ensure_linux() -> bool:
    if platform.system().lower() != "linux":
        print("This installer currently supports Linux only.")
        return False
    return True


def select_release_menu(cfg: Config) -> Config:
    """Fetch GitHub releases, let the user pick one, and save the choice to config.

    Does not download or install anything — only records the selected release
    tag and archive URL so that :func:`install_menu` can use them later.
    """
    logger = get_logger()
    clear_screen()
    print("Select M12 Labs version\n")

    releases: list[Release] = []
    fetch_error: Exception | None = None

    def _fetch() -> None:
        nonlocal releases, fetch_error
        try:
            releases = fetch_releases()
        except (urllib.error.URLError, OSError, ValueError) as exc:
            fetch_error = exc

    thread = threading.Thread(target=_fetch, daemon=True)
    thread.start()

    spinner = ["|", "/", "-", "\\"]
    idx = 0
    while thread.is_alive():
        print(f"\r  {spinner[idx % len(spinner)]}  Fetching available versions…", end="", flush=True)
        idx += 1
        time.sleep(0.15)
    thread.join()
    print("\r" + " " * 50 + "\r", end="", flush=True)

    if fetch_error:
        logger.error("Failed to fetch releases: %s", fetch_error)
        print(f"✗ Could not fetch releases: {fetch_error}")
        wait_for_enter()
        return cfg

    if not releases:
        print("No releases found.")
        wait_for_enter()
        return cfg

    clear_screen()
    print("Select M12 Labs version\n")

    selected = prompt_release_selection(releases)
    if selected is None:
        return cfg

    logger.info("Release selected: '%s'", selected.tag)

    cfg.selected_release = selected.tag
    if selected.tag == DEVELOP_BRANCH_TAG:
        cfg.selected_release_url = DEVELOP_BRANCH_URL
        save_config(cfg)
        print("\n✓ Develop branch selected – will build from source during install.")
    else:
        cfg.selected_release_url = get_archive_url(selected)
        save_config(cfg)
        print(f"\n✓ Release {selected.tag} selected and saved.")
    wait_for_enter()
    return cfg


def _prompt_db_config() -> tuple[str, str, str]:
    """Prompt for database name, user, and password (password never persisted).

    Returns ``(db_name, db_user, db_pass)``.
    """
    from setup.config import DEFAULT_DB_NAME, DEFAULT_DB_USER, generate_db_password

    print("\nDatabase configuration:")
    raw_name = input(f"  DB name   [default: {DEFAULT_DB_NAME}]: ").strip()
    db_name = raw_name if raw_name else DEFAULT_DB_NAME

    raw_user = input(f"  DB user   [default: {DEFAULT_DB_USER}]: ").strip()
    db_user = raw_user if raw_user else DEFAULT_DB_USER

    print("  DB password: leave blank to auto-generate a secure password.")
    raw_pass = input("  DB password [blank = auto-generate]: ").strip()
    if raw_pass:
        db_pass = raw_pass
    else:
        db_pass = generate_db_password()
        print(f"  Generated password: {db_pass}")
        print("  (Save this now – it will not be shown again.)")

    return db_name, db_user, db_pass


def _set_panel_permissions(install_path: Path) -> None:
    """Set storage/bootstrap/cache permissions and www-data ownership."""
    from setup.system import run_command_no_cwd, with_privilege

    for rel_dir in ("storage", "bootstrap/cache"):
        target = install_path / rel_dir
        if target.exists():
            chmod_cmd = with_privilege(["chmod", "-R", "755", str(target)])
            if chmod_cmd:
                run_command_no_cwd(chmod_cmd)

    chown_cmd = with_privilege(["chown", "-R", "www-data:www-data", str(install_path)])
    if chown_cmd:
        run_command_no_cwd(chown_cmd)


def _print_install_summary(install_path: Path, db_name: str, db_user: str) -> None:
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


def install_menu(cfg: Config) -> Config:
    """Full install: download → extract → copy → deps → [build] → DB → Laravel → workers.

    The pnpm build step is only run when the source is the develop branch.
    Release archives (tar.gz / zip) are pre-built and skip that step.
    """
    logger = get_logger()
    clear_screen()
    print("Install M12 Labs\n")

    if not cfg.selected_release or not cfg.selected_release_url:
        print("No release selected.")
        print("Go to Config → Change release version to choose one first.")
        wait_for_enter()
        return cfg

    if not cfg.install_path:
        print("No install path configured.")
        wait_for_enter()
        return cfg

    is_develop = cfg.selected_release == DEVELOP_BRANCH_TAG
    total_steps = 6 if is_develop else 5

    archive_url = cfg.selected_release_url
    filename = Path(urllib.parse.urlparse(archive_url).path).name or f"m12labs-{cfg.selected_release}.tar.gz"
    dest_dir = cfg.install_path.parent / "m12labs-downloads"

    if is_develop:
        print("  Source:   develop branch (will build from source)")
    else:
        print(f"  Release:  {cfg.selected_release}")
    print(f"  Archive:  {filename}")
    print(f"  Save to:  {dest_dir}/")
    print(f"  Install:  {cfg.install_path}/\n")

    confirm = input("Proceed with full installation? [y/N]: ").strip().lower()
    if confirm != "y":
        logger.info("Install: cancelled by user")
        print("Installation cancelled.")
        wait_for_enter()
        return cfg

    # Collect DB config upfront before any long-running work.
    db_name, db_user, db_pass = _prompt_db_config()

    step = 0

    def next_step(label: str) -> str:
        nonlocal step
        step += 1
        return f"\n[{step}/{total_steps}] {label}"

    # --- Download ---
    print(next_step("Downloading archive…"))
    try:
        dest_path = download_archive(archive_url, dest_dir, filename)
        logger.info("Install: archive downloaded to %s", dest_path)
        print(f"✓ Downloaded: {dest_path}")
    except (urllib.error.URLError, OSError) as exc:
        logger.error("Install: download failed: %s", exc)
        print(f"\n✗ Download failed: {exc}")
        db_pass = ""
        wait_for_enter()
        return cfg

    # --- Extract & Copy ---
    print(next_step("Extracting and copying files…"))
    tmp_dir = Path(tempfile.mkdtemp(prefix="m12labs-extract-"))
    try:
        try:
            extracted_root = extract_archive(dest_path, tmp_dir)
            logger.info("Install: extracted to %s", extracted_root)
            print(f"✓ Extracted: {extracted_root.name}")
        except (ValueError, OSError) as exc:
            logger.error("Install: extraction failed: %s", exc)
            print(f"\n✗ Extraction failed: {exc}")
            db_pass = ""
            wait_for_enter()
            return cfg

        cfg.install_path.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copytree(str(extracted_root), str(cfg.install_path), dirs_exist_ok=True)
            logger.info("Install: files copied to %s", cfg.install_path)
            print(f"✓ Files copied to {cfg.install_path}")
        except (OSError, shutil.Error) as exc:
            logger.error("Install: copy failed: %s", exc)
            print(f"\n✗ Copy failed: {exc}")
            db_pass = ""
            wait_for_enter()
            return cfg
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Set permissions before running any commands against the install_path.
    print("  Setting file permissions…")
    _set_panel_permissions(cfg.install_path)

    # --- System dependencies (PHP, MariaDB, NGINX, Redis, Composer) ---
    print(next_step("Installing system dependencies…"))
    logger.info("Install: installing system dependencies")
    from setup.steps.deps import install_dependencies
    if not install_dependencies():
        logger.error("Install aborted: system dependencies failed")
        print("\n✗ Installation failed at system dependencies step.")
        db_pass = ""
        wait_for_enter()
        return cfg

    # --- Frontend build (develop branch only – releases are pre-built) ---
    if is_develop:
        print(next_step("Building frontend assets (develop branch)…"))
        logger.info("Install: starting pnpm build for %s", cfg.install_path)
        run_build_only(cfg.install_path)

    # --- Database ---
    print(next_step("Setting up database…"))
    logger.info("Install: setting up database db_name=%s db_user=%s", db_name, db_user)
    from setup.steps.database import setup_database
    if not setup_database(db_name, db_user, db_pass):
        logger.error("Install aborted: database setup failed")
        print("\n✗ Installation failed at database setup step.")
        db_pass = ""
        wait_for_enter()
        return cfg

    # --- Laravel (composer install, .env, artisan commands, user creation) ---
    print(next_step("Configuring Laravel environment…"))
    logger.info("Install: configuring Laravel at %s", cfg.install_path)
    from setup.steps.laravel import configure_laravel
    if not configure_laravel(cfg.install_path, db_name, db_user, db_pass):
        logger.error("Install aborted: Laravel configuration failed")
        print("\n✗ Installation failed at Laravel configuration step.")
        db_pass = ""
        wait_for_enter()
        return cfg

    # Password no longer needed after Laravel step.
    db_pass = ""

    # --- Workers (cron + systemd queue worker) ---
    print(next_step("Configuring cron job and queue worker…"))
    logger.info("Install: configuring workers for %s", cfg.install_path)
    from setup.steps.workers import configure_workers
    if not configure_workers(cfg.install_path):
        logger.error("Install: workers configuration failed (non-fatal)")
        print("\n⚠  Warning: worker setup failed – you can configure it manually.")

    logger.info("Install completed successfully: install_path=%s", cfg.install_path)
    _print_install_summary(cfg.install_path, db_name, db_user)

    wait_for_enter()
    return cfg


def uninstall_menu(installed_extensions: list[str]) -> None:
    logger = get_logger()
    while True:
        clear_screen()
        print("Uninstall extensions (template)\n")
        if installed_extensions:
            for index, extension_name in enumerate(installed_extensions, start=1):
                print(f"{index}. {extension_name}")
        else:
            print("No tracked installed extensions yet.")
        print("B. Back")

        choice = input("\nSelect an option: ").strip().lower()
        if choice == "b":
            return
        if (
            installed_extensions
            and choice.isdigit()
            and 1 <= (parsed_choice := int(choice)) <= len(installed_extensions)
        ):
            selected = installed_extensions[parsed_choice - 1]
            logger.info("Uninstall action: selected extension '%s'", selected)
            print(f"\nUninstall placeholder for: {selected}")
            print("Real uninstall logic will be added in a future phase.")
        else:
            print("\nInvalid option.")
        wait_for_enter()


def update_menu(installed_extensions: list[str]) -> None:
    logger = get_logger()
    while True:
        clear_screen()
        print("Update extensions (template)\n")
        if installed_extensions:
            for index, extension_name in enumerate(installed_extensions, start=1):
                print(f"{index}. {extension_name}")
            print("A. Update all")
        else:
            print("No tracked installed extensions yet.")
        print("B. Back")

        choice = input("\nSelect an option: ").strip().lower()
        if choice == "b":
            return
        if choice == "a" and installed_extensions:
            logger.info("Update action: update all extensions (%d tracked)", len(installed_extensions))
            print("\nUpdate-all placeholder.")
            print("Real update logic will be added in a future phase.")
        elif (
            choice.isdigit()
            and 1 <= (parsed_choice := int(choice)) <= len(installed_extensions)
        ):
            selected = installed_extensions[parsed_choice - 1]
            logger.info("Update action: selected extension '%s'", selected)
            print(f"\nUpdate placeholder for: {selected}")
            print("Real update logic will be added in a future phase.")
        else:
            print("\nInvalid option.")
        wait_for_enter()


def check_menu(cfg: Config) -> None:
    logger = get_logger()
    install_root = cfg.install_path
    clear_screen()
    print("Check / validation mode\n")
    print(f"Panel install path: {install_root}\n")

    logger.info("Check started for: %s", install_root)

    results = run_checks(install_root)

    if cfg.show_detailed_checks:
        print(format_results(results))
    else:
        print(format_results_concise(results))

    passed = sum(1 for r in results if r.status.value == "PASS")
    warned = sum(1 for r in results if r.status.value == "WARN")
    failed = sum(1 for r in results if r.status.value == "FAIL")
    logger.info(
        "Check complete for %s: %d passed, %d warning(s), %d failure(s)",
        install_root, passed, warned, failed,
    )

    if has_modified_files(results):
        print("\n⚠  WARNING: The panel installation contains modified or missing files.")
        print("   This installation does not appear to be stock/original.")
    elif has_failures(results):
        print("\nSome checks failed. Review the paths above.")
    else:
        print("\nAll checks passed. Panel installation appears to be original.")

    wait_for_enter()


def build_only_menu(install_root: Path) -> None:
    logger = get_logger()
    clear_screen()
    print("Build only\n")

    if not ensure_linux():
        wait_for_enter()
        return

    logger.info("Build only started for: %s", install_root)
    run_build_only(install_root)
    wait_for_enter()


def backup_menu(cfg: Config) -> None:
    logger = get_logger()
    backups_dir = default_backups_dir()

    while True:
        clear_screen()
        print("Backups\n")
        print("1. Create backup")
        print("2. Restore backup")
        print("3. Back")

        choice = input("\nSelect an option: ").strip()
        if choice == "1":
            _create_backup_flow(cfg, backups_dir, logger)
        elif choice == "2":
            _restore_backup_flow(cfg, backups_dir, logger)
        elif choice == "3":
            return
        else:
            print("\nInvalid option.")
            wait_for_enter()


def _create_backup_flow(cfg: Config, backups_dir, logger) -> None:
    clear_screen()
    print("Create backup\n")
    install_path = cfg.install_path
    print(f"Source:  {install_path}")
    print(f"Dest:    {backups_dir}/")

    confirm = input("\nCreate a full backup now? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Backup cancelled.")
        wait_for_enter()
        return

    logger.info("Backup creation started. Source: %s", install_path)
    print("\nNote: For slower systems this may take a minute.")
    print("Compressing backup archive…\n")

    result: dict = {}

    def _run() -> None:
        try:
            result["path"] = create_backup(install_path, backups_dir)
        except Exception as exc:  # noqa: BLE001
            result["error"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    spinner = ["|", "/", "-", "\\"]
    idx = 0
    while thread.is_alive():
        print(f"\r  {spinner[idx % len(spinner)]}  Working…", end="", flush=True)
        idx += 1
        time.sleep(0.15)
    thread.join()
    print("\r" + " " * 20 + "\r", end="", flush=True)  # clear spinner line

    if "error" in result:
        logger.error("Backup creation failed: %s", result["error"])
        print(f"✗ Backup failed: {result['error']}")
    else:
        archive_path = result["path"]
        logger.info("Backup creation complete. Archive: %s", archive_path)
        print(f"✓ Backup saved: {archive_path.name}")
    wait_for_enter()


def _restore_backup_flow(cfg: Config, backups_dir, logger) -> None:
    clear_screen()
    print("Restore backup\n")

    backups = list_backups(backups_dir)
    if not backups:
        print("No backups found.")
        wait_for_enter()
        return

    for idx, entry in enumerate(backups, start=1):
        print(f"{idx}. {entry['filename']}  |  {entry['timestamp']}  |  {entry['size_human']}")
    print("0. Back")

    raw = input("\nSelect a backup to restore: ").strip()
    if raw == "0":
        return
    if not raw.isdigit() or not (1 <= int(raw) <= len(backups)):
        print("\nInvalid selection.")
        wait_for_enter()
        return

    selected: BackupEntry = backups[int(raw) - 1]
    logger.info("Restore: user selected backup '%s'", selected["filename"])

    install_path = cfg.install_path
    print(f"\nSelected:  {selected['filename']}")
    print(f"Timestamp: {selected['timestamp']}")
    print(f"Size:      {selected['size_human']}")
    print()
    print("⚠  WARNING: This operation cannot be undone.")
    print(f"   ALL current contents of the following directory will be deleted")
    print(f"   and replaced with the contents of the selected backup:")
    print(f"     {install_path}")
    print()
    confirm = input("Type 'yes' to confirm the restore, or anything else to cancel: ").strip().lower()
    if confirm != "yes":
        logger.info("Restore cancelled by user.")
        print("Restore cancelled.")
        wait_for_enter()
        return

    logger.info("Restore started. Archive: %s  Target: %s", selected["filename"], install_path)
    print("\nNote: For slower systems this may take a minute.")
    print("Restoring backup…\n")

    result: dict = {}

    def _run_restore() -> None:
        try:
            restore_backup(selected["path"], install_path)
        except Exception as exc:  # noqa: BLE001
            result["error"] = exc

    thread = threading.Thread(target=_run_restore, daemon=True)
    thread.start()

    spinner = ["|", "/", "-", "\\"]
    idx = 0
    while thread.is_alive():
        print(f"\r  {spinner[idx % len(spinner)]}  Working…", end="", flush=True)
        idx += 1
        time.sleep(0.15)
    thread.join()
    print("\r" + " " * 20 + "\r", end="", flush=True)  # clear spinner line

    if "error" in result:
        logger.error("Restore failed: %s", result["error"])
        print(f"✗ Restore failed: {result['error']}")
    else:
        logger.info("Restore complete. Archive: %s", selected["filename"])
        print("✓ Restore complete.")
        print("  Restart the installer to pick up any configuration changes from the restored backup.")
    wait_for_enter()


def config_menu(cfg: Config) -> Config:
    logger = get_logger()
    while True:
        clear_screen()
        print("Config\n")
        print(f"1. Change release version       [{cfg.selected_release or 'not selected'}]")
        print(f"2. Change install path          [{cfg.install_path}]")
        print(f"3. Show detailed checks         [{'on' if cfg.show_detailed_checks else 'off'}]")
        print(f"4. Text log files               [{'on' if cfg.text_logs_enabled else 'off'}]")
        print(f"5. Build on update              [{'on' if cfg.build_on_update else 'off'}]")
        print(f"6. Build on uninstall           [{'on' if cfg.build_on_uninstall else 'off'}]")
        print("0. Back")

        choice = input("\nSelect an option: ").strip()
        if choice == "1":
            cfg = select_release_menu(cfg)
            logger.info("Config changed: selected_release = %s", cfg.selected_release)
        elif choice == "2":
            cfg = prompt_for_install_path(cfg)
            logger.info("Config changed: install_path = %s", cfg.install_path)
            wait_for_enter()
        elif choice == "3":
            cfg.show_detailed_checks = not cfg.show_detailed_checks
            save_config(cfg)
            logger.info("Config changed: show_detailed_checks = %s", cfg.show_detailed_checks)
            print(f"\nShow detailed checks: {'on' if cfg.show_detailed_checks else 'off'}")
            wait_for_enter()
        elif choice == "4":
            cfg.text_logs_enabled = not cfg.text_logs_enabled
            save_config(cfg)
            logger.info("Config changed: text_logs_enabled = %s", cfg.text_logs_enabled)
            print(f"\nText log files: {'on' if cfg.text_logs_enabled else 'off'}")
            wait_for_enter()
        elif choice == "5":
            cfg.build_on_update = not cfg.build_on_update
            save_config(cfg)
            logger.info("Config changed: build_on_update = %s", cfg.build_on_update)
            print(f"\nBuild on update: {'on' if cfg.build_on_update else 'off'}")
            wait_for_enter()
        elif choice == "6":
            cfg.build_on_uninstall = not cfg.build_on_uninstall
            save_config(cfg)
            logger.info("Config changed: build_on_uninstall = %s", cfg.build_on_uninstall)
            print(f"\nBuild on uninstall: {'on' if cfg.build_on_uninstall else 'off'}")
            wait_for_enter()
        elif choice == "0":
            return cfg
        else:
            print("\nInvalid option.")
            wait_for_enter()


def _print_startup_summary(cfg: Config) -> None:
    """Print a concise status summary when the installer starts."""
    from backup import default_backups_dir, list_backups

    backups_dir = default_backups_dir()
    backup_count = len(list_backups(backups_dir))

    # Check whether a manifest is findable without doing a full network fetch.
    manifest_note = "not checked at startup"
    install_root = cfg.install_path
    if install_root is not None and install_root.exists():
        local_manifest = install_root / "manifest.json"
        if local_manifest.exists():
            manifest_note = "local manifest found"
        else:
            manifest_note = "no local manifest (will try remote on check)"

    print("─" * 44)
    print(f"  {'Install path':<15}: {cfg.install_path}")
    print(f"  {'Release':<15}: {cfg.selected_release or 'not selected'}")
    print(f"  {'Text logging':<15}: {'enabled' if cfg.text_logs_enabled else 'disabled'}")
    print(f"  {'Detailed checks':<15}: {'on' if cfg.show_detailed_checks else 'off'}")
    print(f"  {'Backups':<15}: {backup_count} available")
    print(f"  {'Manifest':<15}: {manifest_note}")
    print("─" * 44)
    print()


def main() -> int:
    if not ensure_linux():
        return 1

    cfg = load_config()
    cfg = ensure_install_path(cfg)
    setup_logging(cfg.install_path, cfg.text_logs_enabled)
    logger = get_logger()
    logger.info("Installer started. Panel path: %s", cfg.install_path)

    # Prompt to pick a release version at startup only if one hasn't been selected yet.
    if not cfg.selected_release:
        cfg = select_release_menu(cfg)

    installed_extensions: list[str] = []

    while True:
        clear_screen()
        print("M12 Labs Installer\n")
        _print_startup_summary(cfg)
        print("1. Install")
        print("2. Uninstall")
        print("3. Update")
        print("4. Check")
        print("5. Build only")
        print("6. Backups")
        print("7. Config")
        print("0. Exit")

        choice = input("\nSelect an option: ").strip()
        if choice == "1":
            logger.info("Menu: Install")
            cfg = install_menu(cfg)
        elif choice == "2":
            logger.info("Menu: Uninstall")
            uninstall_menu(installed_extensions)
        elif choice == "3":
            logger.info("Menu: Update")
            update_menu(installed_extensions)
        elif choice == "4":
            logger.info("Menu: Check")
            check_menu(cfg)
        elif choice == "5":
            logger.info("Menu: Build only")
            build_only_menu(cfg.install_path)
        elif choice == "6":
            logger.info("Menu: Backups")
            backup_menu(cfg)
        elif choice == "7":
            logger.debug("Menu: Config")
            cfg = config_menu(cfg)
        elif choice == "0":
            logger.info("Installer exiting.")
            print("Goodbye.")
            return 0
        else:
            print("\nInvalid option.")
            wait_for_enter()


if __name__ == "__main__":
    sys.exit(main())

