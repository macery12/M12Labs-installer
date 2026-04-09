"""Backup and restore helpers for the M12 Labs launcher.

Creates and restores ``.tar.gz`` archives of the full panel install directory.
Archives are stored in ``launcher/backups/`` with timestamped filenames so they
never overwrite each other.

Usage::

    from backup import create_backup, list_backups, restore_backup
    from pathlib import Path

    backups_dir = Path(__file__).parent / "backups"

    # Create
    archive = create_backup(install_path, backups_dir)

    # List (newest first)
    for entry in list_backups(backups_dir):
        print(entry["filename"], entry["timestamp"], entry["size_human"])

    # Restore
    restore_backup(archive, install_path)
"""

from __future__ import annotations

import tarfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import TypedDict

# Directory that stores backup archives, relative to this file.
_DEFAULT_BACKUPS_DIR = Path(__file__).parent / "backups"

_ARCHIVE_PREFIX = "backup-"
_TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"


class BackupEntry(TypedDict):
    path: Path
    filename: str
    timestamp: str
    size_bytes: int
    size_human: str


def _human_size(size_bytes: int) -> str:
    """Return a human-readable file size string."""
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def default_backups_dir() -> Path:
    """Return the default backups directory path (``launcher/backups/``)."""
    return _DEFAULT_BACKUPS_DIR


def create_backup(install_path: Path, backups_dir: Path | None = None) -> Path:
    """Create a ``.tar.gz`` archive of *install_path* inside *backups_dir*.

    Args:
        install_path: Root directory of the panel installation to back up.
        backups_dir:  Directory in which to save the archive.  Defaults to
                      ``launcher/backups/``.

    Returns:
        Path to the newly created archive file.

    Raises:
        FileNotFoundError: If *install_path* does not exist.
        OSError:            If the archive cannot be created.
    """
    if backups_dir is None:
        backups_dir = _DEFAULT_BACKUPS_DIR

    if not install_path.exists():
        raise FileNotFoundError(f"Install path does not exist: {install_path}")

    backups_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime(_TIMESTAMP_FORMAT)
    archive_name = f"{_ARCHIVE_PREFIX}{timestamp}.tar.gz"
    archive_path = backups_dir / archive_name

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(install_path, arcname=install_path.name)

    return archive_path


def list_backups(backups_dir: Path | None = None) -> list[BackupEntry]:
    """Return metadata for all backup archives in *backups_dir*, newest first.

    Args:
        backups_dir: Directory to scan.  Defaults to ``launcher/backups/``.

    Returns:
        List of :class:`BackupEntry` dicts sorted by modification time
        (descending).  An empty list is returned when the directory does not
        exist or contains no matching archives.
    """
    if backups_dir is None:
        backups_dir = _DEFAULT_BACKUPS_DIR

    if not backups_dir.exists():
        return []

    entries: list[BackupEntry] = []
    for archive in sorted(backups_dir.glob(f"{_ARCHIVE_PREFIX}*.tar.gz"), reverse=True):
        stat = archive.stat()
        # Extract the timestamp portion from the filename for display.
        stem = archive.stem  # e.g. "backup-2026-04-09_14-22-31.tar"
        # Remove the extra ".tar" suffix that Path.stem leaves for .tar.gz.
        if stem.endswith(".tar"):
            stem = stem[:-4]
        ts_part = stem[len(_ARCHIVE_PREFIX):]  # "2026-04-09_14-22-31"
        try:
            dt = datetime.strptime(ts_part, _TIMESTAMP_FORMAT)
            timestamp_display = dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            timestamp_display = ts_part

        entries.append(
            BackupEntry(
                path=archive,
                filename=archive.name,
                timestamp=timestamp_display,
                size_bytes=stat.st_size,
                size_human=_human_size(stat.st_size),
            )
        )

    return entries


def restore_backup(archive_path: Path, install_path: Path) -> None:
    """Restore *archive_path* to *install_path*, replacing current contents.

    The restore procedure:
    1. Remove all current contents of *install_path*.
    2. Extract the archive into ``install_path.parent`` so that the top-level
       directory inside the archive lands at *install_path*.

    Args:
        archive_path: Path to the ``.tar.gz`` backup file.
        install_path: Root directory of the panel installation to overwrite.

    Raises:
        FileNotFoundError: If *archive_path* does not exist.
        tarfile.TarError:  If the archive cannot be read.
        OSError:           If the filesystem operations fail.
    """
    if not archive_path.exists():
        raise FileNotFoundError(f"Backup archive not found: {archive_path}")

    # Clear current install directory contents.
    if install_path.exists():
        shutil.rmtree(install_path)
    install_path.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_path, "r:gz") as tar:
        # The archive was created with arcname=install_path.name, so the
        # top-level entry in the tar matches the directory name.  Extracting
        # into install_path.parent recreates that directory at the right place.
        #
        # Validate members before extraction to prevent path traversal attacks.
        _validate_tar_members(tar, install_path.name)
        try:
            # Python 3.12+ supports filter='data' which strips dangerous paths.
            tar.extractall(path=install_path.parent, filter="data")
        except TypeError:
            tar.extractall(path=install_path.parent)  # noqa: S202


def _validate_tar_members(tar: tarfile.TarFile, expected_root: str) -> None:
    """Raise ValueError if any tar member could escape the expected root directory.

    Checks that every member path starts with *expected_root* and contains no
    absolute paths or ``..`` components.
    """
    for member in tar.getmembers():
        member_path = Path(member.name)
        if member_path.is_absolute():
            raise ValueError(f"Unsafe archive: absolute path found: {member.name}")
        parts = member_path.parts
        if ".." in parts:
            raise ValueError(f"Unsafe archive: path traversal found: {member.name}")
        if parts and parts[0] != expected_root:
            raise ValueError(
                f"Unsafe archive: unexpected root '{parts[0]}' (expected '{expected_root}')"
            )
