"""Uninstall helpers for the M12Labs panel installer.

Provides two public entry-points:

* :func:`uninstall_files_only` – remove panel files without touching the
  database, nginx config, or system services.
* :func:`uninstall_full` – remove panel files **plus** nginx config/symlink,
  database/user, installer-created cron job, and the m12labs systemd service.

Both functions require explicit user confirmation before any destructive
action and offer a backup first.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from installer.log import get_logger
from installer.system import confirm, run_command, with_privilege

# Mirror the constants used by nginx.py and workers.py so we clean up
# exactly what the installer created.
_NGINX_SITES_AVAILABLE = Path("/etc/nginx/sites-available")
_NGINX_SITES_ENABLED = Path("/etc/nginx/sites-enabled")
_NGINX_CONF_NAME = "m12labs"

_SERVICE_NAME = "m12labs.service"
_SYSTEMD_UNIT_DIR = Path("/etc/systemd/system")

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")


# ---------------------------------------------------------------------------
# Component detection
# ---------------------------------------------------------------------------

def _detect_components(install_path: Path, db_name: str, db_user: str) -> dict:
    """Return a dict describing which installer-created components exist.

    Keys and values
    ---------------
    ``panel_files``   – ``True`` when *install_path* contains panel files
                        (artisan or package.json present).
    ``nginx_conf``    – ``True`` when
                        ``/etc/nginx/sites-available/m12labs`` exists.
    ``nginx_symlink`` – ``True`` when
                        ``/etc/nginx/sites-enabled/m12labs`` exists (as a
                        file or symlink).
    ``systemd_service`` – ``True`` when
                          ``/etc/systemd/system/m12labs.service`` exists.
    ``cron_entry``    – ``True`` when root's crontab contains a line that
                        references *install_path*.
    ``mysql_available`` – ``True`` when the ``mysql`` client binary is on PATH.
    ``db_name``       – the db_name string (for display).
    ``db_user``       – the db_user string (for display).
    """
    components: dict = {
        "panel_files": False,
        "nginx_conf": False,
        "nginx_symlink": False,
        "systemd_service": False,
        "cron_entry": False,
        "mysql_available": False,
        "db_name": db_name,
        "db_user": db_user,
    }

    # Panel files
    if install_path.is_dir():
        has_artisan = (install_path / "artisan").exists()
        has_pkg = (install_path / "package.json").exists()
        components["panel_files"] = has_artisan or has_pkg

    # nginx
    nginx_conf = _NGINX_SITES_AVAILABLE / _NGINX_CONF_NAME
    components["nginx_conf"] = nginx_conf.exists()
    nginx_link = _NGINX_SITES_ENABLED / _NGINX_CONF_NAME
    components["nginx_symlink"] = nginx_link.exists() or nginx_link.is_symlink()

    # systemd service
    service_path = _SYSTEMD_UNIT_DIR / _SERVICE_NAME
    components["systemd_service"] = service_path.exists()

    # cron entry (root crontab)
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and str(install_path) in result.stdout:
            components["cron_entry"] = True
    except FileNotFoundError:
        pass  # crontab not available

    # mysql client
    components["mysql_available"] = bool(shutil.which("mysql"))

    return components


# ---------------------------------------------------------------------------
# Summary printers
# ---------------------------------------------------------------------------

def _show_files_only_summary(install_path: Path, components: dict) -> None:
    print()
    print("  ─────────────────────────────────────────────────────")
    print("  Uninstall – Remove Panel Files Only")
    print("  ─────────────────────────────────────────────────────")
    print()
    print("  The following will be removed:")
    if components["panel_files"]:
        print(f"    • Panel files in {install_path}")
    else:
        print(f"    • {install_path} directory (no panel files detected)")
    print()
    print("  The following will NOT be touched:")
    print("    • Database and database user")
    print("    • NGINX configuration")
    print("    • Systemd services and cron jobs")
    print()


def _show_full_summary(
    install_path: Path,
    db_name: str,
    db_user: str,
    components: dict,
) -> None:
    print()
    print("  ─────────────────────────────────────────────────────")
    print("  Full Uninstall")
    print("  ─────────────────────────────────────────────────────")
    print()
    print("  The following will be removed:")
    print(f"    • Panel files in {install_path}")

    nginx_conf = _NGINX_SITES_AVAILABLE / _NGINX_CONF_NAME
    nginx_link = _NGINX_SITES_ENABLED / _NGINX_CONF_NAME
    if components["nginx_conf"]:
        print(f"    • NGINX site config  {nginx_conf}")
    if components["nginx_symlink"]:
        print(f"    • NGINX site symlink {nginx_link}")
    if not components["nginx_conf"] and not components["nginx_symlink"]:
        print("    • NGINX site config/symlink (none detected – will be skipped)")

    if components["mysql_available"] and db_name:
        print(f"    • Database           '{db_name}'")
        print(f"    • Database user      '{db_user}'@'127.0.0.1'")
    else:
        print("    • Database / user    (mysql not available or no db_name – will be skipped)")

    if components["systemd_service"]:
        service_path = _SYSTEMD_UNIT_DIR / _SERVICE_NAME
        print(f"    • Systemd service    {service_path}")
    else:
        print("    • Systemd service    (not found – will be skipped)")

    if components["cron_entry"]:
        print(f"    • Cron entry referencing {install_path}")
    else:
        print("    • Cron entry         (none found – will be skipped)")

    print()


# ---------------------------------------------------------------------------
# Individual removal helpers
# ---------------------------------------------------------------------------

def _remove_panel_files(install_path: Path) -> bool:
    """Delete the panel install directory.

    Returns ``True`` on success, ``False`` on failure.
    """
    logger = get_logger()

    if not install_path.exists():
        print(f"  • {install_path} does not exist – nothing to remove.")
        return True

    print(f"  Removing {install_path} …")
    try:
        shutil.rmtree(install_path)
        logger.info("Removed panel directory: %s", install_path)
        print(f"  ✓ Removed {install_path}")
        return True
    except OSError as exc:
        logger.warning("rmtree failed (%s) – retrying with privilege", exc)
        rm_cmd = with_privilege(["rm", "-rf", str(install_path)])
        if rm_cmd and run_command(rm_cmd):
            logger.info("Removed panel directory (privileged): %s", install_path)
            print(f"  ✓ Removed {install_path}")
            return True
        logger.error("Failed to remove %s: %s", install_path, exc)
        print(f"  ✗ Failed to remove {install_path}: {exc}")
        return False


def _remove_nginx(components: dict) -> bool:
    """Remove the m12labs nginx site config and/or symlink.

    Returns ``True`` when all present items were removed (or none existed),
    ``False`` when at least one removal failed.
    """
    logger = get_logger()
    overall_ok = True

    nginx_link = _NGINX_SITES_ENABLED / _NGINX_CONF_NAME
    nginx_conf = _NGINX_SITES_AVAILABLE / _NGINX_CONF_NAME

    if components["nginx_symlink"]:
        print(f"  Removing NGINX symlink {nginx_link} …")
        try:
            nginx_link.unlink(missing_ok=True)
            logger.info("Removed nginx symlink: %s", nginx_link)
            print("  ✓ Symlink removed.")
        except OSError:
            rm_cmd = with_privilege(["rm", "-f", str(nginx_link)])
            if rm_cmd and run_command(rm_cmd):
                logger.info("Removed nginx symlink (privileged): %s", nginx_link)
                print("  ✓ Symlink removed.")
            else:
                logger.error("Failed to remove nginx symlink: %s", nginx_link)
                print(f"  ✗ Failed to remove nginx symlink {nginx_link}.")
                overall_ok = False

    if components["nginx_conf"]:
        print(f"  Removing NGINX config {nginx_conf} …")
        try:
            nginx_conf.unlink(missing_ok=True)
            logger.info("Removed nginx config: %s", nginx_conf)
            print("  ✓ Config removed.")
        except OSError:
            rm_cmd = with_privilege(["rm", "-f", str(nginx_conf)])
            if rm_cmd and run_command(rm_cmd):
                logger.info("Removed nginx config (privileged): %s", nginx_conf)
                print("  ✓ Config removed.")
            else:
                logger.error("Failed to remove nginx config: %s", nginx_conf)
                print(f"  ✗ Failed to remove nginx config {nginx_conf}.")
                overall_ok = False

    if components["nginx_conf"] or components["nginx_symlink"]:
        # Reload nginx to pick up the removal; a failure here is non-fatal.
        if shutil.which("nginx") or shutil.which("systemctl"):
            print("  Reloading nginx …")
            reload_cmd = with_privilege(["systemctl", "reload", "nginx"])
            if reload_cmd:
                ok, _ = _run_capture(reload_cmd)
                if not ok:
                    print("  ⚠  nginx reload failed – run  sudo systemctl reload nginx  manually.")
                else:
                    print("  ✓ nginx reloaded.")

    return overall_ok


def _drop_database(db_name: str, db_user: str) -> bool:
    """Drop the panel database and revoke/drop the panel DB user.

    Uses root MySQL access (same approach as :func:`~installer.steps.database.setup_database`).

    Returns ``True`` on success, ``False`` on failure.
    """
    logger = get_logger()

    if not shutil.which("mysql"):
        print("  ✗ mysql client not found – cannot drop database.")
        logger.error("_drop_database: mysql client not found")
        return False

    if not db_name or not _SAFE_IDENTIFIER_RE.match(db_name):
        print(f"  ✗ Cannot drop database: invalid or empty db_name '{db_name}'.")
        logger.error("_drop_database: invalid db_name '%s'", db_name)
        return False

    if not db_user or not _SAFE_IDENTIFIER_RE.match(db_user):
        print(f"  ✗ Cannot drop user: invalid or empty db_user '{db_user}'.")
        logger.error("_drop_database: invalid db_user '%s'", db_user)
        return False

    sql = (
        f"DROP DATABASE IF EXISTS `{db_name}`;\n"
        f"DROP USER IF EXISTS '{db_user}'@'127.0.0.1';\n"
        "FLUSH PRIVILEGES;\n"
    )

    print(f"  Dropping database '{db_name}' and user '{db_user}'@'127.0.0.1' …")
    _mysql_commands = [["mysql", "-u", "root"], ["sudo", "mysql"]]
    last_result = None
    for mysql_cmd in _mysql_commands:
        try:
            last_result = subprocess.run(
                mysql_cmd,
                input=sql.encode(),
                check=False,
                capture_output=True,
            )
        except FileNotFoundError:
            print("  ✗ mysql command not found.")
            logger.error("_drop_database: mysql binary not found")
            return False

        if last_result.returncode == 0:
            break

        if mysql_cmd is _mysql_commands[0]:
            logger.debug(
                "_drop_database: mysql -u root failed (exit %d); retrying with sudo mysql",
                last_result.returncode,
            )
    else:
        stderr = (last_result.stderr.decode(errors="replace").strip() if last_result else "")
        print("  ✗ MySQL command failed.  Check that MariaDB is running and that")
        print("    root can connect, or re-run as root / with sudo.")
        if stderr:
            print(f"    {stderr}")
        logger.error(
            "_drop_database: mysql exited with code %d",
            last_result.returncode if last_result else -1,
        )
        return False

    logger.info("Dropped database '%s' and user '%s'", db_name, db_user)
    print(f"  ✓ Database '{db_name}' and user '{db_user}' removed.")
    return True


def _remove_cron(install_path: Path) -> bool:
    """Remove cron entries that reference *install_path* from root's crontab.

    Returns ``True`` (including when no entry was found or crontab is
    unavailable), ``False`` only on an unexpected crontab update failure.
    """
    logger = get_logger()

    if not shutil.which("crontab"):
        print("  • crontab not found – nothing to clean up.")
        return True

    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            check=False,
        )
        current = result.stdout if result.returncode == 0 else ""
    except FileNotFoundError:
        print("  • crontab not found – nothing to clean up.")
        return True

    path_str = str(install_path)
    if path_str not in current:
        print("  • No cron entry referencing the install path – nothing to remove.")
        return True

    # Filter out lines that reference the install path
    new_lines = [
        line for line in current.splitlines(keepends=True)
        if path_str not in line
    ]
    new_crontab = "".join(new_lines)

    print(f"  Removing cron entries referencing {install_path} …")
    try:
        if new_crontab.strip():
            proc = subprocess.run(
                ["crontab", "-"],
                input=new_crontab.encode(),
                check=False,
            )
        else:
            proc = subprocess.run(
                ["crontab", "-r"],
                check=False,
            )
    except FileNotFoundError:
        print("  • crontab not found – skipping cron cleanup.")
        return True

    if proc.returncode != 0:
        print("  ⚠  Could not update crontab – clean it up manually with: crontab -e")
        logger.warning("_remove_cron: crontab update failed (exit %d)", proc.returncode)
        return False

    logger.info("Removed cron entries referencing %s", install_path)
    print("  ✓ Cron entries removed.")
    return True


def _remove_systemd_service() -> bool:
    """Disable, stop, and remove the m12labs.service systemd unit.

    Returns ``True`` when the service was removed (or did not exist),
    ``False`` on failure.
    """
    logger = get_logger()
    service_path = _SYSTEMD_UNIT_DIR / _SERVICE_NAME

    if not service_path.exists():
        print(f"  • {_SERVICE_NAME} not found – nothing to remove.")
        return True

    # Disable and stop the service first
    print(f"  Disabling and stopping {_SERVICE_NAME} …")
    disable_cmd = with_privilege(["systemctl", "disable", "--now", _SERVICE_NAME])
    if disable_cmd:
        ok, _ = _run_capture(disable_cmd)
        if not ok:
            print(f"  ⚠  Could not disable {_SERVICE_NAME} – will still try to remove the unit file.")
            logger.warning("_remove_systemd_service: disable --now %s failed", _SERVICE_NAME)

    # Remove the unit file
    print(f"  Removing unit file {service_path} …")
    try:
        service_path.unlink(missing_ok=True)
        logger.info("Removed systemd unit: %s", service_path)
        print(f"  ✓ {_SERVICE_NAME} removed.")
    except OSError:
        rm_cmd = with_privilege(["rm", "-f", str(service_path)])
        if rm_cmd and run_command(rm_cmd):
            logger.info("Removed systemd unit (privileged): %s", service_path)
            print(f"  ✓ {_SERVICE_NAME} removed.")
        else:
            logger.error("Failed to remove systemd unit: %s", service_path)
            print(f"  ✗ Failed to remove {service_path}.")
            return False

    # Reload daemon
    reload_cmd = with_privilege(["systemctl", "daemon-reload"])
    if reload_cmd:
        ok, _ = _run_capture(reload_cmd)
        if not ok:
            print("  ⚠  systemctl daemon-reload failed – run it manually.")
        else:
            print("  ✓ systemctl daemon-reload complete.")

    return True


# ---------------------------------------------------------------------------
# Backup prompt (shared by both uninstall paths)
# ---------------------------------------------------------------------------

def _offer_backup_before_uninstall(install_path: Path) -> bool:
    """Offer a backup and return ``True`` when the uninstall should proceed.

    Returns ``False`` only when the user explicitly requests a backup but it
    fails AND they decline to continue without one, or when the user changes
    their mind and cancels at the second warning.
    """
    from installer.backup.backup import DEFAULT_BACKUPS_DIR, create_backup

    print()
    print("  ─────────────────────────────────────────────────────")
    print("  ⚠  Backup recommended before uninstalling")
    print("  ─────────────────────────────────────────────────────")
    print("  Creating a backup lets you restore the panel later.")
    print()

    try:
        answer = input("  Create a backup now? [Y/n]: ").strip().lower()
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
                    "  Backup failed. Continue without a backup? [y/N]: "
                ).strip().lower()
            except EOFError:
                proceed = "n"

            if proceed not in ("y", "yes"):
                print("  Uninstall cancelled – please resolve the backup issue first.")
                return False
            print()
            return True

    # User declined backup – warn once more
    print()
    print("  ⚠  Proceeding without a backup.  This action cannot be undone.")
    print()
    try:
        answer2 = input(
            "  Are you sure you want to continue WITHOUT a backup? [y/N]: "
        ).strip().lower()
    except EOFError:
        answer2 = "n"

    if answer2 not in ("y", "yes"):
        print("  Uninstall cancelled.")
        return False

    print()
    return True


# ---------------------------------------------------------------------------
# Internal subprocess helper
# ---------------------------------------------------------------------------

def _run_capture(cmd: list[str]) -> tuple[bool, str]:
    """Run *cmd* capturing stdout+stderr.  Returns ``(success, output)``."""
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0, output


# ---------------------------------------------------------------------------
# Public entry-points
# ---------------------------------------------------------------------------

def uninstall_files_only(install_path: Path) -> bool:
    """Remove panel files at *install_path* without touching any other component.

    Flow
    ----
    1. Detect installed components.
    2. Show summary of what will be removed.
    3. Offer backup.
    4. Confirm the destructive step.
    5. Remove files.

    Returns ``True`` on success, ``False`` on failure or user cancellation.
    """
    logger = get_logger()
    components = _detect_components(install_path, "", "")

    _show_files_only_summary(install_path, components)

    if not install_path.exists():
        print(f"  Nothing to remove – {install_path} does not exist.")
        return True

    if not _offer_backup_before_uninstall(install_path):
        return False

    print("  ─────────────────────────────────────────────────────")
    if not confirm(
        f"Remove all panel files in {install_path}?",
    ):
        print("  Uninstall cancelled – no files were removed.")
        return False

    print()
    ok = _remove_panel_files(install_path)
    if ok:
        logger.info("Files-only uninstall complete: %s", install_path)
        print()
        print("  ✓ Panel files removed.")
        print("  Database, NGINX config, and system services were left untouched.")
    else:
        logger.error("Files-only uninstall failed: %s", install_path)
        print()
        print("  ✗ File removal encountered errors – see output above.")
    return ok


def uninstall_full(install_path: Path, db_name: str, db_user: str) -> bool:
    """Full uninstall: remove panel files, nginx config, database, cron, and service.

    Flow
    ----
    1. Detect installed components.
    2. Show summary of everything that will be removed.
    3. Offer backup.
    4. Single confirmation before proceeding.
    5. Remove components one by one, reporting each result honestly.
       A failure in one step is reported but does not stop subsequent steps
       (so as much as possible is cleaned up), unless the step is file removal.

    Returns ``True`` when all detected components were removed successfully,
    ``False`` when any step failed.
    """
    logger = get_logger()
    components = _detect_components(install_path, db_name, db_user)

    _show_full_summary(install_path, db_name, db_user, components)

    if not install_path.exists() and not any([
        components["nginx_conf"],
        components["nginx_symlink"],
        components["systemd_service"],
        components["cron_entry"],
    ]):
        print("  Nothing to remove – no installer-created components were found.")
        return True

    if not _offer_backup_before_uninstall(install_path):
        return False

    print("  ─────────────────────────────────────────────────────")
    print("  This will permanently remove the panel and all its components.")
    if not confirm("Proceed with full uninstall?"):
        print("  Full uninstall cancelled – no changes were made.")
        return False

    print()

    overall_ok = True

    # --- 1. Panel files --------------------------------------------------------
    print("  [1/5] Removing panel files …")
    if install_path.exists():
        if not _remove_panel_files(install_path):
            print("  ✗ Panel file removal failed – stopping here.")
            logger.error("Full uninstall: file removal failed; aborting remaining steps")
            return False
    else:
        print(f"  • {install_path} does not exist – skipping.")

    # --- 2. NGINX config + symlink ---------------------------------------------
    print()
    print("  [2/5] Removing NGINX config …")
    if components["nginx_conf"] or components["nginx_symlink"]:
        if not _remove_nginx(components):
            print("  ⚠  NGINX cleanup had errors (see above). Continuing.")
            overall_ok = False
    else:
        print("  • No NGINX config or symlink found – skipping.")

    # --- 3. Database -----------------------------------------------------------
    print()
    print("  [3/5] Dropping database …")
    if components["mysql_available"] and db_name:
        if not confirm(
            f"Drop database '{db_name}' and user '{db_user}'@'127.0.0.1'?",
        ):
            print("  Database drop skipped (user declined).")
        else:
            if not _drop_database(db_name, db_user):
                print("  ⚠  Database removal had errors (see above). Continuing.")
                overall_ok = False
    else:
        print("  • mysql not available or no database name configured – skipping.")

    # --- 4. Cron ---------------------------------------------------------------
    print()
    print("  [4/5] Removing cron entry …")
    if not _remove_cron(install_path):
        print("  ⚠  Cron cleanup had errors (see above). Continuing.")
        overall_ok = False

    # --- 5. Systemd service ----------------------------------------------------
    print()
    print("  [5/5] Removing systemd service …")
    if not _remove_systemd_service():
        print("  ⚠  Service removal had errors (see above).")
        overall_ok = False

    print()
    if overall_ok:
        logger.info("Full uninstall complete: install_path=%s, db=%s, user=%s",
                    install_path, db_name, db_user)
        print("  ✓ Full uninstall complete.  All detected panel components have been removed.")
    else:
        logger.warning("Full uninstall completed with errors: install_path=%s", install_path)
        print("  ⚠  Full uninstall completed with some errors.  Review the output above.")

    return overall_ok
