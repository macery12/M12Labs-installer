"""Backup helpers for the M12Labs panel installer."""

from __future__ import annotations

import datetime
import shutil
import sys
import tarfile
import tempfile
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

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_name = f"m12labs_backup_{timestamp}.tar.gz"
    archive_path = backups_dir / archive_name

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(install_path, arcname=install_path.name)

    return archive_path


def _safe_extractall(tar: tarfile.TarFile, dest: Path) -> None:
    """Extract *tar* into *dest* with path-traversal protection."""
    if sys.version_info >= (3, 12):
        tar.extractall(path=dest, filter="data")
    else:
        import os
        real_dest = os.path.realpath(str(dest))
        for member in tar.getmembers():
            member_path = os.path.realpath(
                os.path.join(real_dest, member.name)
            )
            if not member_path.startswith(real_dest + os.sep) and member_path != real_dest:
                raise ValueError(
                    f"Path traversal attempt detected in archive: {member.name}"
                )
        tar.extractall(path=dest)


def restore_backup(archive_path: Path, install_path: Path) -> None:
    """Restore *archive_path* over *install_path*.

    The archive is first extracted into a temporary directory next to
    *install_path*.  Only once that succeeds is the existing installation
    removed and replaced, so a failed extraction never leaves the user
    without an installation.
    """
    tmp_dir = Path(tempfile.mkdtemp(dir=install_path.parent))
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            _safe_extractall(tar, tmp_dir)

        extracted = tmp_dir / install_path.name
        if not extracted.exists():
            raise FileNotFoundError(
                f"Expected '{install_path.name}' inside archive but it was not found."
            )

        if install_path.exists():
            shutil.rmtree(install_path)
        shutil.move(str(extracted), str(install_path))
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


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
