"""Step 2 – Download and extract the M12Labs panel release.

Translates the ``download-files.md`` documentation page:

1. Create the install directory if it does not exist.
2. Download the release tarball via ``curl``.
3. Extract it in-place.
4. Set correct permissions and ownership (``www-data:www-data``).

For the develop channel, ``clone_panel`` is used instead; git creates the
target directory itself so only the *parent* must be pre-created.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from setup.log import get_logger
from setup.system import run_command, run_command_no_cwd, with_privilege

# Fixed release URL for v2.0.0-m12-rc2.6.
# Update this constant when a new panel version is released.
DEFAULT_RELEASE_URL = (
    "https://github.com/macery12/M12Labs/releases/download/"
    "v2.0.0-m12-rc2.6/panel.tar.gz"
)

DEVELOP_REPO_GIT_URL = "https://github.com/macery12/M12Labs.git"

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

    # Create install directory
    if not install_path.exists():
        print(f"  Creating install directory: {install_path}")
        logger.debug("Creating install directory: %s", install_path)
        try:
            install_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            # Fall back to privileged mkdir if permissions block us
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

    # Download tarball
    print(f"  Downloading {release_url} …")
    if not run_command(
        ["curl", "-Lo", str(tarball_path), release_url],
        cwd=install_path,
    ):
        print("  ERROR: download failed.")
        logger.error("curl download failed for %s", release_url)
        return False

    # Extract
    print("  Extracting panel archive…")
    if not run_command(["tar", "-xzf", str(tarball_path)], cwd=install_path):
        print("  ERROR: extraction failed.")
        logger.error("tar extraction failed for %s", tarball_path)
        return False

    # Clean up tarball
    try:
        tarball_path.unlink()
    except OSError:
        logger.debug("Could not remove tarball %s – skipping", tarball_path)

    # Permissions
    print("  Setting file permissions…")
    for rel_dir in ("storage", "bootstrap/cache"):
        target = install_path / rel_dir
        if target.exists():
            chmod_cmd = with_privilege(["chmod", "-R", "755", str(target)])
            if chmod_cmd:
                run_command_no_cwd(chmod_cmd)

    # Ownership
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


def clone_panel(
    install_path: Path,
    repo_url: str = DEVELOP_REPO_GIT_URL,
    branch: str = "develop",
) -> bool:
    """Clone the M12Labs panel repository into *install_path* (develop channel).

    ``git clone`` creates the target directory itself, so only the *parent*
    must exist beforehand.  Pre-creating *install_path* would cause git to
    refuse with "destination path already exists and is not an empty directory".

    Steps:
        1. Ensure the parent of *install_path* exists.
        2. ``git clone --depth 1 --branch <branch> <repo_url> <install_path>``.
        3. Set ``755`` permissions on ``storage/`` and ``bootstrap/cache/``.
        4. Set ``www-data:www-data`` ownership on *install_path*.

    Returns ``True`` on success, ``False`` on the first failure.
    """
    logger = get_logger()
    logger.info("Step 2: git clone %s (branch: %s) -> %s", repo_url, branch, install_path)
    print("\n[2/5] Cloning panel repository (develop branch)…")

    if not shutil.which("git"):
        print("  ERROR: git is required to clone the panel.")
        logger.error("git not found")
        return False

    # Only the parent needs to exist; git clone owns the target directory.
    try:
        install_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("parent mkdir failed (%s) – trying with privilege", exc)
        mkdir_cmd = with_privilege(["mkdir", "-p", str(install_path.parent)])
        if not mkdir_cmd or not run_command_no_cwd(mkdir_cmd):
            print(f"  ERROR: could not create parent directory {install_path.parent}")
            logger.error("Failed to create parent directory: %s", install_path.parent)
            return False

    print(f"  Cloning {repo_url} (branch: {branch}) into {install_path} …")
    try:
        result = subprocess.run(
            [
                "git", "clone", "--depth", "1",
                "--branch", branch,
                repo_url,
                str(install_path),
            ],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        logger.error("git not found: %s", exc)
        print("  ERROR: git not found.")
        return False

    if result.returncode != 0:
        msg = result.stderr.strip() or "git clone failed"
        logger.error("git clone failed: %s", msg)
        print(f"  ERROR: Git clone failed: {msg}")
        return False

    logger.info("git clone complete: %s", install_path)
    print(f"  ✓ Cloned {branch} branch to {install_path}")

    # Permissions
    print("  Setting file permissions…")
    for rel_dir in ("storage", "bootstrap/cache"):
        target = install_path / rel_dir
        if target.exists():
            chmod_cmd = with_privilege(["chmod", "-R", "755", str(target)])
            if chmod_cmd:
                run_command_no_cwd(chmod_cmd)

    # Ownership
    print("  Setting ownership to www-data:www-data…")
    chown_cmd = with_privilege(
        ["chown", "-R", "www-data:www-data", str(install_path)]
    )
    if chown_cmd:
        if not run_command_no_cwd(chown_cmd):
            logger.warning("chown failed – continuing")
            print("  Warning: could not set www-data ownership.")

    logger.info("Step 2 complete: panel cloned to %s", install_path)
    print("  ✓ Panel repository cloned.")
    return True
