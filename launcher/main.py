#!/usr/bin/env python3
"""Linux-first M12 Labs extension manager launcher template."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

AVAILABLE_MODS = [f"Mod {i}" for i in range(1, 13)]
PAGE_SIZE = 6
INSTALLED_MODS: list[str] = []


def clear_screen() -> None:
    print("\033c", end="")


def wait_for_enter() -> None:
    input("\nPress Enter to continue...")


def run_command(command: Sequence[str], cwd: Path) -> bool:
    print(f"\n$ {' '.join(command)}")
    try:
        completed = subprocess.run(command, cwd=cwd, check=False)
        return completed.returncode == 0
    except FileNotFoundError:
        return False


def ensure_linux() -> bool:
    if platform.system().lower() != "linux":
        print("This launcher template currently supports Linux only.")
        return False
    return True


def install_menu() -> None:
    page = 0
    while True:
        clear_screen()
        start = page * PAGE_SIZE
        end = start + PAGE_SIZE
        page_items = AVAILABLE_MODS[start:end]
        total_pages = max((len(AVAILABLE_MODS) - 1) // PAGE_SIZE + 1, 1)

        print("Install extensions (template)")
        print(f"Page {page + 1}/{total_pages}\n")
        for index, mod in enumerate(page_items, start=1):
            print(f"{index}. {mod}")
        print("7. Next page")
        print("8. Back")

        choice = input("\nSelect an option: ").strip()
        if choice in {"1", "2", "3", "4", "5", "6"}:
            item_index = int(choice) - 1
            if item_index < len(page_items):
                selected = page_items[item_index]
                print(f"\nInstall placeholder for: {selected}")
                print("Real install logic will be added in a future phase.")
            else:
                print("\nNo mod is mapped to that number on this page.")
            wait_for_enter()
        elif choice == "7":
            page = (page + 1) % total_pages
        elif choice == "8":
            return
        else:
            print("\nInvalid option.")
            wait_for_enter()


def uninstall_menu() -> None:
    while True:
        clear_screen()
        print("Uninstall extensions (template)\n")
        if INSTALLED_MODS:
            for index, mod in enumerate(INSTALLED_MODS, start=1):
                print(f"{index}. {mod}")
        else:
            print("No tracked installed mods yet.")
        print("B. Back")

        choice = input("\nSelect an option: ").strip().lower()
        if choice == "b":
            return
        if choice.isdigit() and 1 <= int(choice) <= len(INSTALLED_MODS):
            selected = INSTALLED_MODS[int(choice) - 1]
            print(f"\nUninstall placeholder for: {selected}")
            print("Real uninstall logic will be added in a future phase.")
        else:
            print("\nInvalid option.")
        wait_for_enter()


def update_menu() -> None:
    while True:
        clear_screen()
        print("Update extensions (template)\n")
        if INSTALLED_MODS:
            for index, mod in enumerate(INSTALLED_MODS, start=1):
                print(f"{index}. {mod}")
            print("A. Update all")
        else:
            print("No tracked installed mods yet.")
        print("B. Back")

        choice = input("\nSelect an option: ").strip().lower()
        if choice == "b":
            return
        if choice == "a" and INSTALLED_MODS:
            print("\nUpdate-all placeholder.")
            print("Real update logic will be added in a future phase.")
        elif choice.isdigit() and 1 <= int(choice) <= len(INSTALLED_MODS):
            selected = INSTALLED_MODS[int(choice) - 1]
            print(f"\nUpdate placeholder for: {selected}")
            print("Real update logic will be added in a future phase.")
        else:
            print("\nInvalid option.")
        wait_for_enter()


def check_menu() -> None:
    clear_screen()
    print("Check / validation mode (template)\n")
    print(f"Platform check: {'OK' if ensure_linux() else 'FAILED'}")
    print("State check: placeholder")
    print("Dependency check: placeholder")
    print("\nFull validation checks will be added in a future phase.")
    wait_for_enter()


def build_only() -> None:
    clear_screen()
    print("Build only\n")
    if not ensure_linux():
        wait_for_enter()
        return

    node_bin = shutil.which("node")
    pnpm_bin = shutil.which("pnpm")
    print(f"Node: {'FOUND' if node_bin else 'NOT FOUND'}")
    print(f"pnpm: {'FOUND' if pnpm_bin else 'NOT FOUND'}")

    if not node_bin or not pnpm_bin:
        print("\nInstall missing dependencies and try again.")
        wait_for_enter()
        return

    project_root = Path(__file__).resolve().parent.parent
    if not (project_root / "package.json").exists():
        print(f"\nNo package.json found in: {project_root}")
        print("Build template cannot continue without a Node project root.")
        wait_for_enter()
        return

    install_ok = run_command(["pnpm", "install"], cwd=project_root)
    build_ok = run_command(["pnpm", "build"], cwd=project_root) if install_ok else False

    if install_ok and build_ok:
        print("\nBuild flow completed successfully.")
    else:
        print("\nBuild flow failed. Check command output above.")
    wait_for_enter()


def main() -> int:
    if not ensure_linux():
        return 1

    while True:
        clear_screen()
        print("M12 Labs Linux Extension Manager (template)\n")
        print("1. Install")
        print("2. Uninstall")
        print("3. Update")
        print("4. Check")
        print("5. Build only")
        print("0. Exit")

        choice = input("\nSelect an option: ").strip()
        if choice == "1":
            install_menu()
        elif choice == "2":
            uninstall_menu()
        elif choice == "3":
            update_menu()
        elif choice == "4":
            check_menu()
        elif choice == "5":
            build_only()
        elif choice == "0":
            print("Goodbye.")
            return 0
        else:
            print("\nInvalid option.")
            wait_for_enter()


if __name__ == "__main__":
    sys.exit(main())
