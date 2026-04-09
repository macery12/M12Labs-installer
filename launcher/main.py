#!/usr/bin/env python3
"""Linux-first M12 Labs extension manager launcher."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

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

PLACEHOLDER_EXTENSION_COUNT = 12
EXTENSION_CATALOG = [
    f"Extension {i}" for i in range(1, PLACEHOLDER_EXTENSION_COUNT + 1)
]
PAGE_SIZE = 6


def clear_screen() -> None:
    if sys.stdout.isatty() and os.getenv("TERM"):
        subprocess.run(["clear"], check=False)
    else:
        print("\n" * 2, end="")


def wait_for_enter() -> None:
    input("\nPress Enter to continue...")


def ensure_linux() -> bool:
    if platform.system().lower() != "linux":
        print("This launcher currently supports Linux only.")
        return False
    return True


def calculate_total_pages(item_count: int, page_size: int) -> int:
    if item_count <= 0:
        return 1
    return (item_count - 1) // page_size + 1


def install_menu() -> None:
    logger = get_logger()
    page = 0
    while True:
        clear_screen()
        start = page * PAGE_SIZE
        end = start + PAGE_SIZE
        page_items = EXTENSION_CATALOG[start:end]
        total_pages = calculate_total_pages(len(EXTENSION_CATALOG), PAGE_SIZE)
        next_option_number = len(page_items) + 1
        back_option_number = len(page_items) + 2

        print("Install extensions (template)")
        print(f"Page {page + 1}/{total_pages}\n")
        for index, extension_name in enumerate(page_items, start=1):
            print(f"{index}. {extension_name}")
        print(f"{next_option_number}. Next page")
        print(f"{back_option_number}. Back")

        choice = input("\nSelect an option: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(page_items):
            parsed_choice = int(choice)
            selected = page_items[parsed_choice - 1]
            logger.info("Install action: selected extension '%s'", selected)
            print(f"\nInstall placeholder for: {selected}")
            print("Real install logic will be added in a future phase.")
            wait_for_enter()
        elif choice == str(next_option_number):
            page = (page + 1) % total_pages
        elif choice == str(back_option_number):
            return
        else:
            print("\nInvalid option.")
            wait_for_enter()


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
    print("\nCreating backup archive…")
    try:
        archive_path = create_backup(install_path, backups_dir)
        logger.info("Backup creation complete. Archive: %s", archive_path)
        print(f"\n✓ Backup saved: {archive_path.name}")
    except Exception as exc:  # noqa: BLE001
        logger.error("Backup creation failed: %s", exc)
        print(f"\n✗ Backup failed: {exc}")
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
    print(f"\nThis will REPLACE the contents of:\n  {install_path}")
    confirm = input("\nRestore this backup? [y/N]: ").strip().lower()
    if confirm != "y":
        logger.info("Restore cancelled by user.")
        print("Restore cancelled.")
        wait_for_enter()
        return

    logger.info("Restore started. Archive: %s  Target: %s", selected["filename"], install_path)
    print("\nRestoring backup…")
    try:
        restore_backup(selected["path"], install_path)
        logger.info("Restore complete. Archive: %s", selected["filename"])
        print("\n✓ Restore complete.")
        print("  Restart the launcher to pick up any configuration changes from the restored backup.")
    except Exception as exc:  # noqa: BLE001
        logger.error("Restore failed: %s", exc)
        print(f"\n✗ Restore failed: {exc}")
    wait_for_enter()


def config_menu(cfg: Config) -> Config:
    logger = get_logger()
    while True:
        clear_screen()
        print("Config\n")
        print(f"2. Change install path          [{cfg.install_path}]")
        print(f"3. Show detailed checks         [{'on' if cfg.show_detailed_checks else 'off'}]")
        print(f"4. Text log files               [{'on' if cfg.text_logs_enabled else 'off'}]")
        print(f"5. Build on update              [{'on' if cfg.build_on_update else 'off'}]")
        print(f"6. Build on uninstall           [{'on' if cfg.build_on_uninstall else 'off'}]")
        print("0. Back")

        choice = input("\nSelect an option: ").strip()
        if choice == "2":
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


def main() -> int:
    if not ensure_linux():
        return 1

    cfg = load_config()
    cfg = ensure_install_path(cfg)
    setup_logging(cfg.install_path, cfg.text_logs_enabled)
    logger = get_logger()
    logger.info("Launcher started. Panel path: %s", cfg.install_path)
    installed_extensions: list[str] = []

    while True:
        clear_screen()
        print("M12 Labs Linux Extension Manager\n")
        print(f"Panel path: {cfg.install_path}\n")
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
            install_menu()
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
            logger.info("Launcher exiting.")
            print("Goodbye.")
            return 0
        else:
            print("\nInvalid option.")
            wait_for_enter()


if __name__ == "__main__":
    sys.exit(main())

