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
    release_url: str | None = None,
) -> bool:
    """Download and extract the M12Labs panel into *install_path*.

    Steps:
        1. Create *install_path* if it does not exist (prints what it does).
        2. Download the tarball from *release_url* via ``curl``
           (falls back to :data:`DEFAULT_RELEASE_URL` when *release_url* is
           ``None`` or empty).
        3. Extract the tarball into *install_path*.
        4. Remove the downloaded tarball.
        5. Set ``755`` permissions on ``storage/`` and ``bootstrap/cache/``.
        6. Set ``www-data:www-data`` ownership on *install_path*.

    Returns ``True`` on success, ``False`` on the first failure.
    """
    if not release_url:
        release_url = DEFAULT_RELEASE_URL
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

    _set_permissions(install_path, logger)
    logger.info("Step 2 complete: panel files extracted to %s", install_path)
    print("  ✓ Panel files downloaded and extracted.")
    return True


def _is_git_repo(path: Path) -> bool:
    """Return ``True`` if *path* contains an initialised git repository."""
    return (path / ".git").exists()


def _dir_is_empty(path: Path) -> bool:
    """Return ``True`` if *path* exists but contains no entries."""
    try:
        return not any(True for _ in path.iterdir())
    except OSError:
        return False


def _remove_dir(path: Path, logger) -> bool:
    """Remove *path* recursively, trying sudo if a plain rmtree fails."""
    try:
        shutil.rmtree(path)
        logger.debug("Removed directory: %s", path)
        return True
    except OSError as exc:
        logger.warning("rmtree failed (%s) – trying with privilege", exc)
        rm_cmd = with_privilege(["rm", "-rf", str(path)])
        if rm_cmd and run_command_no_cwd(rm_cmd):
            logger.debug("Removed directory (privileged): %s", path)
            return True
        logger.error("Could not remove directory: %s", path)
        return False


def _set_permissions(install_path: Path, logger) -> None:
    """Apply ``755`` permissions on storage dirs and ``www-data`` ownership."""
    print("  Setting file permissions…")
    for rel_dir in ("storage", "bootstrap/cache"):
        target = install_path / rel_dir
        if target.exists():
            chmod_cmd = with_privilege(["chmod", "-R", "755", str(target)])
            if chmod_cmd:
                run_command_no_cwd(chmod_cmd)

    print("  Setting ownership to www-data:www-data…")
    chown_cmd = with_privilege(
        ["chown", "-R", "www-data:www-data", str(install_path)]
    )
    if chown_cmd:
        if not run_command_no_cwd(chown_cmd):
            logger.warning("chown failed – continuing")
            print("  Warning: could not set www-data ownership.")


def clone_panel(
    install_path: Path,
    repo_url: str = DEVELOP_REPO_GIT_URL,
    branch: str = "develop",
) -> bool:
    """Clone the M12Labs panel repository into *install_path* (develop channel).

    Handles all install-path pre-flight cases so ``git clone`` never sees a
    non-empty destination:

    * **Does not exist** – normal clone (git creates the directory).
    * **Exists, empty** – directory is removed so git creates it cleanly.
    * **Exists, non-empty, already a git repo** – ``git fetch`` + ``git reset
      --hard`` to bring it to the latest state of *branch* without re-cloning.
    * **Exists, non-empty, not a git repo** – the user is prompted to confirm
      wiping the directory before cloning.  If they decline, the step is
      aborted gracefully.

    Returns ``True`` on success, ``False`` on the first failure.
    """
    logger = get_logger()
    logger.info("Step 2: git clone %s (branch: %s) -> %s", repo_url, branch, install_path)
    print("\n[2/5] Cloning panel repository (develop branch)…")

    if not shutil.which("git"):
        print("  ERROR: git is required to clone the panel.")
        logger.error("git not found")
        return False

    # ------------------------------------------------------------------ #
    # Pre-flight: handle existing install_path
    # ------------------------------------------------------------------ #
    if install_path.exists():
        if _dir_is_empty(install_path):
            # git clone still refuses an empty directory on some versions;
            # remove it so git can create it itself.
            logger.debug("install_path exists but is empty – removing before clone")
            if not _remove_dir(install_path, logger):
                print(f"  ERROR: could not clear empty directory {install_path}")
                return False

        elif _is_git_repo(install_path):
            # Already cloned – pull to latest instead of re-cloning.
            print(f"  Directory {install_path} already contains a git repository.")
            print(f"  Updating to latest {branch} branch instead of re-cloning…")
            logger.info("install_path already a git repo – updating in place")

            fetch_result = subprocess.run(
                ["git", "fetch", "--depth", "1", "origin", branch],
                cwd=install_path,
                capture_output=True,
                text=True,
            )
            if fetch_result.returncode != 0:
                msg = fetch_result.stderr.strip() or "git fetch failed"
                logger.error("git fetch failed: %s", msg)
                print(f"  ERROR: {msg}")
                return False

            reset_result = subprocess.run(
                ["git", "reset", "--hard", f"origin/{branch}"],
                cwd=install_path,
                capture_output=True,
                text=True,
            )
            if reset_result.returncode != 0:
                msg = reset_result.stderr.strip() or "git reset failed"
                logger.error("git reset failed: %s", msg)
                print(f"  ERROR: {msg}")
                return False

            logger.info("git update complete: %s", install_path)
            print(f"  ✓ Updated {branch} branch at {install_path}")
            _set_permissions(install_path, logger)
            logger.info("Step 2 complete: panel updated at %s", install_path)
            print("  ✓ Panel repository updated.")
            return True

        else:
            # Non-empty directory that is NOT a git repo – ask the user.
            print(f"\n  WARNING: {install_path} already exists and is not empty.")
            print("  Continuing will PERMANENTLY DELETE all files in that directory.")
            try:
                answer = input("  Wipe directory and re-clone? [y/N]: ").strip().lower()
            except EOFError:
                answer = ""
            if answer != "y":
                print("  Aborted – install_path was not modified.")
                logger.warning("User declined to wipe %s – aborting clone", install_path)
                return False
            print(f"  Removing {install_path} …")
            if not _remove_dir(install_path, logger):
                print(f"  ERROR: could not remove {install_path}")
                return False
            logger.info("Removed existing install_path: %s", install_path)

    # ------------------------------------------------------------------ #
    # Ensure the parent directory exists; git clone creates install_path.
    # ------------------------------------------------------------------ #
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
    _set_permissions(install_path, logger)
    logger.info("Step 2 complete: panel cloned to %s", install_path)
    print("  ✓ Panel repository cloned.")
    return True
