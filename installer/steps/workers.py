"""Step 5 – Configure the cron job and systemd queue worker.

Translates the ``queue-workers.md`` documentation page:

1. Append the artisan schedule:run cron entry (if not already present).
2. Write the ``m12labs.service`` systemd unit file.
3. ``systemctl daemon-reload && systemctl enable --now m12labs.service``.

If the legacy ``jxctl.service`` unit is detected it is disabled and removed
automatically before the new unit is installed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from installer.log import get_logger
from installer.system import run_command, with_privilege

_CRON_ENTRY_TEMPLATE = (
    "* * * * * php {artisan} schedule:run >> /dev/null 2>&1"
)

_SYSTEMD_UNIT_TEMPLATE = """\
[Unit]
Description=M12Labs Queue Worker
After=redis-server.service

[Service]
User=www-data
Group=www-data
Restart=always
ExecStart=/usr/bin/php {artisan} queue:work --sleep=3 --tries=3 --max-time=3600
StartLimitInterval=180
StartLimitBurst=30
RestartSec=5s

[Install]
WantedBy=multi-user.target
"""

_SERVICE_NAME = "m12labs.service"
_LEGACY_SERVICE_NAME = "jxctl.service"  # renamed; migrated on first run
_SYSTEMD_UNIT_DIR = Path("/etc/systemd/system")


def configure_workers(install_path: Path) -> bool:
    """Install the cron job and systemd queue-worker service.

    Args:
        install_path: Root of the installed panel (e.g. ``/var/www/m12labs``).

    Returns:
        ``True`` on success, ``False`` on first failure.
    """
    logger = get_logger()
    logger.info("Step 5: Configuring cron and queue worker for %s", install_path)
    print("\n[5/5] Configuring cron job and queue worker…")

    artisan_bin = str(install_path / "artisan")

    if not _install_cron(artisan_bin):
        return False

    if not _install_systemd_service(artisan_bin):
        return False

    logger.info("Step 5 complete: cron and queue worker configured")
    print("  ✓ Cron job and queue worker configured.")
    return True


def _install_cron(artisan_bin: str) -> bool:
    """Add the artisan schedule:run cron entry for root (idempotent).

    The entry is installed in root's crontab so it is visible when an
    administrator runs ``crontab -e`` (as root).  This matches the documented
    setup procedure:

        * * * * * php /path/to/artisan schedule:run > /dev/null 2>&1
    """
    logger = get_logger()
    entry = _CRON_ENTRY_TEMPLATE.format(artisan=artisan_bin)

    print("  Checking root crontab…")

    # Read current root crontab; empty string if none set yet
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            check=False,
        )
        current = result.stdout if result.returncode == 0 else ""
    except FileNotFoundError:
        print("  WARNING: crontab command not found – skipping cron setup.")
        logger.warning("crontab not found; skipping cron setup")
        return True  # Non-fatal; cron may not be installed yet.

    if entry in current:
        print("  Cron entry already present – skipping.")
        logger.debug("Cron entry already present")
        return True

    new_crontab = (current.rstrip("\n") + "\n" + entry + "\n").lstrip("\n")
    print(f"  Adding cron entry: {entry}")

    try:
        proc = subprocess.run(
            ["crontab", "-"],
            input=new_crontab.encode(),
            check=False,
        )
    except FileNotFoundError:
        print("  WARNING: crontab command not found – skipping cron setup.")
        logger.warning("crontab not found; skipping cron setup")
        return True

    if proc.returncode != 0:
        print("  WARNING: could not update crontab – continuing.")
        logger.warning("crontab update failed (exit %d)", proc.returncode)
        # Non-fatal; the user can add it manually
    else:
        logger.debug("Cron entry added for root")
        print(f"  ✓ Cron entry added.  Verify with: crontab -l")

    return True


def _install_systemd_service(artisan_bin: str) -> bool:
    """Write the m12labs.service unit file and enable it.

    Also migrates the legacy ``jxctl.service`` if it exists: disables and
    removes it so the system doesn't run two conflicting workers.
    """
    logger = get_logger()
    unit_content = _SYSTEMD_UNIT_TEMPLATE.format(artisan=artisan_bin)
    unit_path = _SYSTEMD_UNIT_DIR / _SERVICE_NAME

    # ------------------------------------------------------------------
    # Migrate legacy jxctl.service if present
    # ------------------------------------------------------------------
    legacy_path = _SYSTEMD_UNIT_DIR / _LEGACY_SERVICE_NAME
    if legacy_path.exists():
        print(f"  Migrating legacy service {_LEGACY_SERVICE_NAME} → {_SERVICE_NAME}…")
        disable_cmd = with_privilege(["systemctl", "disable", "--now", _LEGACY_SERVICE_NAME])
        if disable_cmd:
            run_command(disable_cmd)
        try:
            legacy_path.unlink()
            logger.debug("Removed legacy unit file %s", legacy_path)
        except OSError:
            rm_cmd = with_privilege(["rm", "-f", str(legacy_path)])
            if rm_cmd:
                run_command(rm_cmd)

    print(f"  Writing systemd unit: {unit_path}…")

    # Write the unit file using privilege escalation if required
    write_cmd = with_privilege(
        ["tee", str(unit_path)]
    )
    if write_cmd:
        try:
            proc = subprocess.run(
                write_cmd,
                input=unit_content.encode(),
                check=False,
                capture_output=True,
            )
            if proc.returncode != 0:
                print(f"  ERROR: could not write {unit_path}")
                logger.error("tee to %s failed (exit %d)", unit_path, proc.returncode)
                return False
        except FileNotFoundError:
            # Fall back to direct write if tee is unavailable
            try:
                unit_path.write_text(unit_content, encoding="utf-8")
            except PermissionError as exc:
                print(f"  ERROR: permission denied writing {unit_path}: {exc}")
                logger.error("Permission denied writing %s: %s", unit_path, exc)
                return False
    else:
        # No sudo available; attempt direct write
        try:
            unit_path.write_text(unit_content, encoding="utf-8")
        except PermissionError as exc:
            print(f"  ERROR: permission denied writing {unit_path}: {exc}")
            logger.error("Permission denied writing %s: %s", unit_path, exc)
            return False

    # Reload daemon and enable the service
    reload_cmd = with_privilege(["systemctl", "daemon-reload"])
    enable_cmd = with_privilege(["systemctl", "enable", "--now", _SERVICE_NAME])

    if reload_cmd:
        if not run_command(reload_cmd):
            print("  WARNING: systemctl daemon-reload failed.")
            logger.warning("systemctl daemon-reload failed")
    if enable_cmd:
        if not run_command(enable_cmd):
            print(f"  WARNING: systemctl enable --now {_SERVICE_NAME} failed.")
            logger.warning("systemctl enable --now %s failed", _SERVICE_NAME)

    logger.debug("systemd service %s written and enabled", _SERVICE_NAME)
    return True
