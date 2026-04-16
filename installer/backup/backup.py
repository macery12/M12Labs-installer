"""Backup helpers for the M12Labs panel installer."""

from __future__ import annotations

import datetime
import shutil
import tarfile
from pathlib import Path

# Backups are stored inside the repo root under a "backups/" folder so they
# are always in a predictable, easy-to-find location next to the installer.
_INSTALLER_PKG = Path(__file__).resolve().parent   # installer/backup/
_REPO_ROOT = _INSTALLER_PKG.parent.parent           # repo root
DEFAULT_BACKUPS_DIR: Path = _REPO_ROOT / "backups"


def create_backup(install_path: Path, backups_dir: Path | None = None) -> Path:
    """Create a timestamped ``backup.tar.gz`` of *install_path*.

    The archive is written to *backups_dir* (defaults to
    ``<repo_root>/backups/``).  Returns the path of the created archive.
    """
    if backups_dir is None:
        backups_dir = DEFAULT_BACKUPS_DIR

    backups_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"m12labs_backup_{timestamp}.tar.gz"
    archive_path = backups_dir / archive_name

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(install_path, arcname=install_path.name)

    return archive_path


def restore_backup(archive_path: Path, install_path: Path) -> None:
    """Restore *archive_path* over *install_path*.

    The existing contents of *install_path* are removed first so the
    restore produces a clean result that matches the archive exactly.
    """
    if install_path.exists():
        shutil.rmtree(install_path)

    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(path=install_path.parent)


def list_backups(backups_dir: Path | None = None) -> list[Path]:
    """Return a sorted list of backup archives in *backups_dir*."""
    if backups_dir is None:
        backups_dir = DEFAULT_BACKUPS_DIR

    if not backups_dir.exists():
        return []

    return sorted(backups_dir.glob("m12labs_backup_*.tar.gz"))


def delete_backup(archive_path: Path) -> None:
    """Delete a single backup archive."""
    archive_path.unlink()
