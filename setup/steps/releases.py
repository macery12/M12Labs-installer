"""GitHub release fetching, selection, and download for the M12 Labs setup installer."""

from __future__ import annotations

import json
import logging
import tarfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

_logger = logging.getLogger("m12labs.setup")

_GITHUB_API_URL = "https://api.github.com/repos/macery12/M12Labs/releases"
_PAGE_SIZE = 10

# Sentinel tag used to represent the develop branch install source.
DEVELOP_BRANCH_TAG = "develop"
# Git repository URL – cloned directly when develop is selected.
DEVELOP_REPO_GIT_URL = "https://github.com/macery12/M12Labs.git"


@dataclass
class Release:
    tag: str
    name: str
    prerelease: bool
    assets: list[dict] = field(default_factory=list)
    zipball_url: str = ""


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_releases() -> list[Release]:
    """Fetch all releases from GitHub, including pre-releases.

    Raises ``urllib.error.URLError`` on network failures.
    """
    _logger.info("Fetching releases from %s", _GITHUB_API_URL)
    req = urllib.request.Request(
        _GITHUB_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "M12Labs-installer",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data: list[dict] = json.loads(resp.read().decode("utf-8"))

    releases: list[Release] = []
    for item in data:
        tag = item.get("tag_name", "")
        name = (item.get("name") or tag).strip()
        releases.append(
            Release(
                tag=tag,
                name=name,
                prerelease=bool(item.get("prerelease", False)),
                assets=item.get("assets", []),
                zipball_url=item.get("zipball_url", ""),
            )
        )

    _logger.info("Fetched %d release(s)", len(releases))
    return releases


# ---------------------------------------------------------------------------
# Archive URL
# ---------------------------------------------------------------------------

def get_archive_url(release: Release) -> str:
    """Return the best download URL for a release's panel archive.

    Prefers the first ``.zip`` or ``.tar.gz`` asset attached to the release.
    Falls back to the GitHub-generated source-code zipball.
    """
    for asset in release.assets:
        name: str = asset.get("name", "")
        if name.endswith(".zip") or name.endswith(".tar.gz"):
            url = asset.get("browser_download_url", "")
            if url:
                return url
    return release.zipball_url


# ---------------------------------------------------------------------------
# Interactive selection
# ---------------------------------------------------------------------------

def prompt_release_selection(releases: list[Release]) -> Release | None:
    """Display available releases and let the user pick one.

    Returns the selected :class:`Release`, or ``None`` when the user goes back.
    Choosing "D" returns a synthetic Release with :data:`DEVELOP_BRANCH_TAG` so
    the caller can detect that the develop branch was requested.
    """
    page = 0
    total_pages = max(1, (len(releases) - 1) // _PAGE_SIZE + 1)

    while True:
        start = page * _PAGE_SIZE
        page_items = releases[start : start + _PAGE_SIZE]

        print(f"Available M12 Labs versions (page {page + 1}/{total_pages})\n")
        print("  D. Develop branch (latest source – will be cloned via git)")
        print()
        for i, release in enumerate(page_items, start=1):
            label = "  [pre-release]" if release.prerelease else ""
            print(f"  {i}. {release.name}{label}")

        print()
        options: list[str] = []
        if page < total_pages - 1:
            print("  N. Next page")
            options.append("n")
        if page > 0:
            print("  P. Previous page")
            options.append("p")
        print("  B. Back")

        choice = input("\nSelect a version: ").strip().lower()

        if choice == "b":
            return None
        if choice == "d":
            return Release(
                tag=DEVELOP_BRANCH_TAG,
                name="develop branch",
                prerelease=True,
            )
        if choice == "n" and "n" in options:
            page += 1
            continue
        if choice == "p" and "p" in options:
            page -= 1
            continue
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(page_items):
                return page_items[idx - 1]

        print("\nInvalid option.")


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_archive(url: str, dest_dir: Path, filename: str) -> Path:
    """Download *url* to *dest_dir/filename*, printing a live progress line.

    Returns the full path to the saved file.
    Raises ``urllib.error.URLError`` on network failures.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename

    _logger.info("Downloading %s -> %s", url, dest_path)
    req = urllib.request.Request(url, headers={"User-Agent": "M12Labs-installer"})

    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        chunk_size = 8192
        with dest_path.open("wb") as fh:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                fh.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    kb_done = downloaded // 1024
                    kb_total = total // 1024
                    print(
                        f"\r  Downloading… {pct}%  ({kb_done} KB / {kb_total} KB)   ",
                        end="",
                        flush=True,
                    )
                else:
                    print(
                        f"\r  Downloading… {downloaded // 1024} KB   ",
                        end="",
                        flush=True,
                    )

    print()  # newline after progress line
    _logger.info("Download complete: %s (%d bytes)", dest_path, downloaded)
    return dest_path


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_archive(archive_path: Path, dest_dir: Path) -> Path:
    """Extract a ``.zip`` or ``.tar.gz`` archive into *dest_dir*.

    Returns the path to the top-level content directory inside the archive
    (GitHub source archives always contain a single top-level folder).  If
    the archive has no single top-level directory, *dest_dir* itself is
    returned.

    Raises ``ValueError`` for unrecognised formats, ``OSError`` / ``tarfile``
    / ``zipfile`` exceptions on corrupt archives.
    """
    name = archive_path.name
    _logger.info("Extracting %s -> %s", archive_path, dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    if name.endswith(".tar.gz") or name.endswith(".tgz"):
        with tarfile.open(archive_path, "r:gz") as tf:
            tf.extractall(dest_dir)
    elif name.endswith(".zip") or zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(dest_dir)
    else:
        raise ValueError(f"Unrecognised archive format: {name!r}")

    # GitHub archives always extract to a single top-level directory.
    entries = [p for p in dest_dir.iterdir() if p.is_dir()]
    if len(entries) == 1:
        _logger.debug("Extracted top-level directory: %s", entries[0])
        return entries[0]

    _logger.debug("Archive has no single top-level directory; using %s", dest_dir)
    return dest_dir
