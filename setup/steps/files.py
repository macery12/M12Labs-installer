"""Step 2 – Download and extract the M12Labs panel release.

Translates the ``download-files.md`` documentation page:

1. Create the install directory if it does not exist.
2. Download the release tarball via ``curl``.
3. Extract it in-place.
4. Set correct permissions and ownership (``www-data:www-data``).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from setup.log import get_logger
from setup.system import run_command, run_command_no_cwd, with_privilege

# Fixed release URL for v2.0.0-m12-rc2.6.
# Update this constant when a new panel version is released.
DEFAULT_RELEASE_URL = (
    "https://github.com/macery12/M12Labs/releases/download/"
    "v2.0.0-m12-rc2.6/panel.tar.gz"
)

_TARBALL_NAME = "panel.tar.gz"


def download_panel(
    install_path: Path,
    release_url: str = DEFAULT_RELEASE_URL,
) -> bool:
    """Download and extract the M12Labs panel into *install_path*.

    Steps:
        1. Create *install_path* if it does not exist (prints what it does).
        2. Download the tarball from *release_url* via ``curl``.
        3. Extract the tarball into *install_path*.
        4. Remove the downloaded tarball.
        5. Set ``755`` permissions on ``storage/`` and ``bootstrap/cache/``.
        6. Set ``www-data:www-data`` ownership on *install_path*.

    Returns ``True`` on success, ``False`` on the first failure.
    """
    logger = get_logger()
    logger.info("Step 2: Downloading panel from %s to %s", release_url, install_path)
    print("\n[2/5] Downloading panel files…")

    # --- Create install directory ---
    if not install_path.exists():
        print(f"  Creating install directory: {install_path}")
        logger.debug("Creating install directory: %s", install_path)
        try:
            install_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            # Fall back to privileged mkdir if permissions block us.
            logger.warning("mkdir failed (%s) – trying with privilege", exc)
            mkdir_cmd = with_privilege(["mkdir", "-p", str(install_path)])
            if not mkdir_cmd or not run_command_no_cwd(mkdir_cmd):
                print(f"  ERROR: could not create {install_path}")
                logger.error("Failed to create install directory: %s", install_path)
                return False
    else:
        print(f"  Install directory already exists: {install_path}")

    if not shutil.which("curl"):
        print("  ERROR: curl is required to download the panel.")
        logger.error("curl not found")
        return False

    tarball_path = install_path / _TARBALL_NAME

    # --- Download tarball ---
    print(f"  Downloading {release_url} …")
    if not run_command(
        ["curl", "-Lo", str(tarball_path), release_url],
        cwd=install_path,
    ):
        print("  ERROR: download failed.")
        logger.error("curl download failed for %s", release_url)
        return False

    # --- Extract ---
    print("  Extracting panel archive…")
    if not run_command(["tar", "-xzf", str(tarball_path)], cwd=install_path):
        print("  ERROR: extraction failed.")
        logger.error("tar extraction failed for %s", tarball_path)
        return False

    # Clean up tarball.
    try:
        tarball_path.unlink()
    except OSError:
        logger.debug("Could not remove tarball %s – skipping", tarball_path)

    # --- Permissions ---
    print("  Setting file permissions…")
    for rel_dir in ("storage", "bootstrap/cache"):
        target = install_path / rel_dir
        if target.exists():
            chmod_cmd = with_privilege(["chmod", "-R", "755", str(target)])
            if chmod_cmd:
                run_command_no_cwd(chmod_cmd)

    # --- Ownership ---
    print("  Setting ownership to www-data:www-data…")
    chown_cmd = with_privilege(
        ["chown", "-R", "www-data:www-data", str(install_path)]
    )
    if chown_cmd:
        if not run_command_no_cwd(chown_cmd):
            logger.warning("chown failed – continuing")
            print("  Warning: could not set www-data ownership.")

    logger.info("Step 2 complete: panel files extracted to %s", install_path)
    print("  ✓ Panel files downloaded and extracted.")
    return True
