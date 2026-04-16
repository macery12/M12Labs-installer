"""Step 1 – Install system dependencies for the M12Labs panel.

Translates the ``install-dependencies.md`` documentation page into
automated commands:

1. Install base tools (software-properties-common, curl, …).
2. Add the ondrej/php PPA (Ubuntu/Debian only).
3. ``apt-get update``
4. Install PHP 8.3, MariaDB, NGINX, Redis, and other required packages.
5. Install Composer globally if not already present.
"""

from __future__ import annotations

import shutil

from installer.log import get_logger
from installer.system import (
    get_package_manager,
    install_packages,
    run_command_no_cwd,
    with_privilege,
)

_PHP_PACKAGES = [
    "php8.3",
    "php8.3-common",
    "php8.3-cli",
    "php8.3-gd",
    "php8.3-mysql",
    "php8.3-mbstring",
    "php8.3-bcmath",
    "php8.3-xml",
    "php8.3-fpm",
    "php8.3-curl",
    "php8.3-zip",
]

_SYSTEM_PACKAGES = [
    "mariadb-server",
    "nginx",
    "tar",
    "unzip",
    "git",
    "redis-server",
    "cron",
]

_BASE_PACKAGES = [
    "software-properties-common",
    "curl",
    "apt-transport-https",
    "ca-certificates",
    "gnupg",
]

_COMPOSER_INSTALLER_URL = "https://getcomposer.org/installer"
_COMPOSER_BIN = "/usr/local/bin/composer"


def install_dependencies() -> bool:
    """Install all system dependencies required by the M12Labs panel.

    Returns ``True`` when every step succeeds, ``False`` on first failure.
    """
    logger = get_logger()
    logger.info("Step 1: Installing system dependencies")
    print("\n[1/5] Installing system dependencies…")

    pm = get_package_manager()
    if not pm:
        print("  ERROR: No supported package manager found.")
        logger.error("No supported package manager found")
        return False

    # Base tools
    print("  Installing base tools…")
    if not install_packages(_BASE_PACKAGES):
        logger.error("Failed to install base packages")
        return False

    # PHP PPA (Ubuntu/Debian only)
    if pm == "apt-get":
        print("  Adding ondrej/php PPA…")
        add_repo_cmd = with_privilege(
            ["add-apt-repository", "-y", "ppa:ondrej/php"]
        )
        if add_repo_cmd:
            env_cmd = ["env", "LC_ALL=C.UTF-8", *add_repo_cmd]
            if not run_command_no_cwd(env_cmd):
                logger.warning("add-apt-repository failed; continuing without PPA")
                print("  Warning: could not add ondrej/php PPA – continuing anyway.")

        # Update package lists after adding PPA
        update_cmd = with_privilege(["apt-get", "update"])
        if update_cmd and not run_command_no_cwd(update_cmd):
            logger.error("apt-get update failed after adding PPA")
            return False

    # PHP 8.3 and system packages
    print("  Installing PHP 8.3 and system packages…")
    if not install_packages(_PHP_PACKAGES + _SYSTEM_PACKAGES):
        logger.error("Failed to install PHP/system packages")
        return False

    # Composer
    if not _ensure_composer():
        logger.error("Failed to install Composer")
        return False

    logger.info("Step 1 complete: all system dependencies installed")
    print("  ✓ System dependencies installed.")
    return True


def _ensure_composer() -> bool:
    """Install Composer globally if it is not already available."""
    if shutil.which("composer"):
        print("  Composer: already installed.")
        return True

    print("  Composer: not found – installing via curl…")
    if not shutil.which("curl"):
        print("  ERROR: curl is required to install Composer.")
        return False
    if not shutil.which("php"):
        print("  ERROR: php is required to install Composer.")
        return False

    # Download installer to a temp file and run it
    download_ok = run_command_no_cwd(
        ["curl", "-sS", "-o", "/tmp/composer-setup.php", _COMPOSER_INSTALLER_URL]
    )
    if not download_ok:
        print("  ERROR: failed to download Composer installer.")
        return False

    install_ok = run_command_no_cwd(
        ["php", "/tmp/composer-setup.php", "--install-dir=/usr/local/bin", "--filename=composer"]
    )
    if not install_ok:
        print("  ERROR: Composer installer script failed.")
        return False

    if not shutil.which("composer"):
        print("  ERROR: composer binary not found after installation.")
        return False

    print("  Composer installed successfully.")
    return True
