#!/usr/bin/env python3
"""Linux-first M12 Labs extension manager launcher template."""

from __future__ import annotations

import platform
import subprocess
import sys
import os
from pathlib import Path

from build import build_only as run_build_only

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
        print("This launcher template currently supports Linux only.")
        return False
    return True


def calculate_total_pages(item_count: int, page_size: int) -> int:
    if item_count <= 0:
        return 1
    return (item_count - 1) // page_size + 1


def install_menu() -> None:
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
            item_index = parsed_choice - 1
            selected = page_items[item_index]
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
            print(f"\nUninstall placeholder for: {selected}")
            print("Real uninstall logic will be added in a future phase.")
        else:
            print("\nInvalid option.")
        wait_for_enter()


def update_menu(installed_extensions: list[str]) -> None:
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
            print("\nUpdate-all placeholder.")
            print("Real update logic will be added in a future phase.")
        elif (
            choice.isdigit()
            and 1 <= (parsed_choice := int(choice)) <= len(installed_extensions)
        ):
            selected = installed_extensions[parsed_choice - 1]
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


def find_project_root(start: Path) -> Path | None:
    for parent in [start] + list(start.parents):
        if (parent / "package.json").exists():
            return parent
    return None


def build_only() -> None:
    clear_screen()
    print("Build only\n")

    if not ensure_linux():
        wait_for_enter()
        return

    start_path = Path(__file__).resolve()
    project_root = find_project_root(start_path)

    if not project_root:
        print("Could not find package.json")
        wait_for_enter()
        return

    run_build_only(project_root)
    wait_for_enter()


def main() -> int:
    if not ensure_linux():
        return 1
    installed_extensions: list[str] = []

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
            uninstall_menu(installed_extensions)
        elif choice == "3":
            update_menu(installed_extensions)
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
