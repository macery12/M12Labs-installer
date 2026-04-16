"""Backup helpers for the M12Labs panel installer – skeleton (optional in v1).

Full implementation is deferred to a future iteration.  The module
currently exposes placeholder stubs so that ``setup/backup/`` can be
imported without errors.
"""

from __future__ import annotations

from pathlib import Path


def create_backup(install_path: Path, backups_dir: Path) -> Path:
    """Create a backup of *install_path* into *backups_dir*.

    .. note::
        Not yet implemented in v1.  Raises :class:`NotImplementedError`.
    """
    raise NotImplementedError("Backup support is not yet implemented in v1.")


def restore_backup(archive_path: Path, install_path: Path) -> None:
    """Restore *archive_path* into *install_path*.

    .. note::
        Not yet implemented in v1.  Raises :class:`NotImplementedError`.
    """
    raise NotImplementedError("Restore support is not yet implemented in v1.")
