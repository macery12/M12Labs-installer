"""Build flow helpers for the launcher."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Sequence

INSTALL_NOTICE_DELAY_SECONDS = 2
DEFAULT_PROJECT_ROOT = Path("/root/M12Labs-Extension")
PROJECT_ROOT_ENV = "M12LABS_PROJECT_ROOT"


def run_command(command: Sequence[str], cwd: Path) -> bool:
    print(f"\n$ {' '.join(command)}")
    try:
        completed = subprocess.run(command, cwd=cwd, check=False)
        return completed.returncode == 0
    except FileNotFoundError:
        print(f"Command not found: {command[0]}")
        return False


def run_command_no_cwd(command: Sequence[str]) -> bool:
    print(f"\n$ {' '.join(command)}")
    try:
        completed = subprocess.run(command, check=False)
        return completed.returncode == 0
    except FileNotFoundError:
        print(f"Command not found: {command[0]}")
        return False


def get_package_manager() -> str | None:
    if shutil.which("apt-get"):
        return "apt-get"
    if shutil.which("dnf"):
        return "dnf"
    if shutil.which("yum"):
        return "yum"
    if shutil.which("pacman"):
        return "pacman"
    if shutil.which("zypper"):
        return "zypper"
    if shutil.which("apk"):
        return "apk"
    return None


def with_privilege(command: Sequence[str]) -> list[str] | None:
    try:
        is_root = os.geteuid() == 0
    except AttributeError:
        is_root = False

    if is_root:
        return list(command)
    if shutil.which("sudo"):
        return ["sudo", *command]
    return None


def install_packages(packages: Sequence[str]) -> bool:
    package_manager = get_package_manager()
    if not package_manager:
        print("No supported package manager found (apt-get/dnf/yum/pacman/zypper/apk).")
        return False

    if package_manager == "apt-get":
        update_cmd = with_privilege(["apt-get", "update"])
        install_cmd = with_privilege(["apt-get", "install", "-y", *packages])
    elif package_manager == "dnf":
        update_cmd = None
        install_cmd = with_privilege(["dnf", "install", "-y", *packages])
    elif package_manager == "yum":
        update_cmd = None
        install_cmd = with_privilege(["yum", "install", "-y", *packages])
    elif package_manager == "pacman":
        update_cmd = with_privilege(["pacman", "-Sy"])
        install_cmd = with_privilege(["pacman", "--noconfirm", "-S", *packages])
    elif package_manager == "zypper":
        update_cmd = None
        install_cmd = with_privilege(["zypper", "--non-interactive", "install", *packages])
    else:
        update_cmd = None
        install_cmd = with_privilege(["apk", "add", *packages])

    if not install_cmd:
        print("Missing root privileges and `sudo` is unavailable; cannot install packages.")
        return False

    print(f"Installing packages via {package_manager}: {', '.join(packages)}")
    if update_cmd and not run_command_no_cwd(update_cmd):
        return False
    return run_command_no_cwd(install_cmd)


def ensure_node_installed() -> bool:
    if shutil.which("node"):
        print("Node.js: already installed.")
        return True

    print("Node.js: not found, attempting automatic installation...")
    package_manager = get_package_manager()
    if package_manager in {"apt-get", "dnf", "yum", "zypper"}:
        package_sets = [["nodejs", "npm"], ["nodejs"]]
    elif package_manager == "pacman":
        package_sets = [["nodejs", "npm"], ["nodejs"]]
    elif package_manager == "apk":
        package_sets = [["nodejs", "npm"], ["nodejs-lts", "npm"], ["nodejs"]]
    else:
        package_sets = [["nodejs", "npm"], ["nodejs"]]

    for package_set in package_sets:
        if install_packages(package_set) and shutil.which("node"):
            break

    if not shutil.which("node"):
        print("Failed to install Node.js automatically.")
        return False

    print("Node.js installation completed.")
    return True


def ensure_pnpm_installed() -> bool:
    if shutil.which("pnpm"):
        print("pnpm: already installed.")
        return True

    print("pnpm: not found, attempting automatic installation...")

    if shutil.which("corepack"):
        if run_command_no_cwd(["corepack", "enable"]) and run_command_no_cwd(
            ["corepack", "prepare", "pnpm@latest", "--activate"]
        ):
            if shutil.which("pnpm"):
                print("pnpm installation completed via corepack.")
                return True

    if shutil.which("npm") and run_command_no_cwd(["npm", "install", "-g", "pnpm@latest"]):
        if shutil.which("pnpm"):
            print("pnpm installation completed via npm.")
            return True

    if install_packages(["pnpm"]) and shutil.which("pnpm"):
        print("pnpm installation completed via system package manager.")
        return True

    print("Failed to install pnpm automatically.")
    return False


def show_install_notice() -> None:
    print("\nPreparing required build dependencies.")
    print("This may take 1–2 minutes.")
    print("Please wait while installation completes...")
    time.sleep(INSTALL_NOTICE_DELAY_SECONDS)


def build_only(project_root: Path | None = None) -> None:
    if project_root:
        resolved_project_root = project_root
    else:
        env_project_root = os.getenv(PROJECT_ROOT_ENV)
        resolved_project_root = Path(env_project_root) if env_project_root else DEFAULT_PROJECT_ROOT
    package_json = resolved_project_root / "package.json"
    try:
        package_json_exists = package_json.exists()
    except OSError as error:
        print(f"Failed to check package.json in: {resolved_project_root}")
        print("Unable to access path. Verify the directory exists and you have read permissions.")
        print(f"You can override the default path with {PROJECT_ROOT_ENV}.")
        print(f"Path access error: {error}")
        return

    if not package_json_exists:
        print(f"No package.json found in: {resolved_project_root}")
        return

    missing_dependencies = not shutil.which("node") or not shutil.which("pnpm")
    if missing_dependencies:
        show_install_notice()

    if not ensure_node_installed():
        print("\nBuild flow failed: Node.js is required but could not be prepared.")
        return

    if not ensure_pnpm_installed():
        print("\nBuild flow failed: pnpm is required but could not be prepared.")
        return

    install_ok = run_command(["pnpm", "install"], cwd=resolved_project_root)
    if not install_ok:
        print("\nBuild flow failed. `pnpm install` did not complete successfully.")
        return

    build_ok = run_command(["pnpm", "build"], cwd=resolved_project_root)
    if build_ok:
        print("\nBuild flow completed successfully.")
    else:
        print("\nBuild flow failed. Check command output above.")
