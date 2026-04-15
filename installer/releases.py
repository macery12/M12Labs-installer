"""GitHub release fetching, selection, and download for the M12 Labs installer."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

_logger = logging.getLogger("m12labs")

_GITHUB_API_URL = "https://api.github.com/repos/macery12/M12Labs/releases"
_PAGE_SIZE = 10


@dataclass
class Release:
    tag: str
    name: str
    description: str
    prerelease: bool
    assets: list[dict] = field(default_factory=list)
    zipball_url: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_line(text: str, max_len: int = 72) -> str:
    """Return the first non-empty line of *text*, truncated to *max_len*."""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line if len(line) <= max_len else line[:max_len - 3] + "..."
    return ""


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
        body = item.get("body") or ""
        releases.append(
            Release(
                tag=tag,
                name=name,
                description=_first_line(body),
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
    """
    page = 0
    total_pages = max(1, (len(releases) - 1) // _PAGE_SIZE + 1)

    while True:
        start = page * _PAGE_SIZE
        page_items = releases[start : start + _PAGE_SIZE]

        print(f"Available M12 Labs versions (page {page + 1}/{total_pages})\n")
        for i, release in enumerate(page_items, start=1):
            label = "  [pre-release]" if release.prerelease else ""
            print(f"  {i}. {release.name}{label}")
            if release.description:
                print(f"     {release.description}")

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
