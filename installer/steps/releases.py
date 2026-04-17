"""GitHub release fetching and selection for the M12 Labs setup installer."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

_logger = logging.getLogger("m12labs.setup")

_PAGE_SIZE = 10

# Sentinel tag used to represent the develop branch install source.
DEVELOP_BRANCH_TAG = "develop"


@dataclass
class RepoSource:
    """A GitHub repository that can provide panel releases."""

    name: str     # Human-readable display name
    api_url: str  # GitHub releases API URL
    git_url: str  # Git clone URL used when the develop branch is selected


# ---------------------------------------------------------------------------
# Configured release repositories
# ---------------------------------------------------------------------------

#: Default list of repos the installer can install from.  Add or remove entries
#: here to extend multi-repo support.  The first entry is used as the default
#: when no explicit selection has been made.
RELEASE_REPOS: list[RepoSource] = [
    RepoSource(
        name="M12Labs",
        api_url="https://api.github.com/repos/macery12/M12Labs/releases",
        git_url="https://github.com/macery12/M12Labs.git",
    ),
    RepoSource(
        name="Jexactyl",
        api_url="https://api.github.com/repos/Jexactyl/Jexactyl/releases",
        git_url="https://github.com/Jexactyl/Jexactyl.git",
    ),
]

# ---------------------------------------------------------------------------
# Backward-compatibility aliases (kept so existing callers don't break)
# ---------------------------------------------------------------------------

_GITHUB_API_URL = RELEASE_REPOS[0].api_url
# Git repository URL – cloned directly when develop is selected.
DEVELOP_REPO_GIT_URL = RELEASE_REPOS[0].git_url


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

def fetch_releases_from_url(api_url: str) -> list[Release]:
    """Fetch all releases from a specific GitHub releases API URL.

    Raises ``urllib.error.URLError`` on network failures.
    """
    _logger.info("Fetching releases from %s", api_url)
    req = urllib.request.Request(
        api_url,
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


def fetch_releases(api_url: str | None = None) -> list[Release]:
    """Fetch all releases, including pre-releases.

    Uses the first entry in :data:`RELEASE_REPOS` when *api_url* is ``None``.
    Raises ``urllib.error.URLError`` on network failures.
    """
    return fetch_releases_from_url(api_url or _GITHUB_API_URL)


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

def prompt_repo_selection(repos: list[RepoSource]) -> RepoSource | None:
    """Let the user choose which repository to install from.

    Returns the selected :class:`RepoSource`, or ``None`` when the user goes
    back.  Only called when ``len(repos) > 1``.
    """
    print("\nAvailable release sources:\n")
    for i, repo in enumerate(repos, start=1):
        print(f"  {i}. {repo.name}")
    print("  B. Back")

    while True:
        try:
            choice = input("\nSelect a release source: ").strip().lower()
        except EOFError:
            return None

        if choice == "b":
            return None
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(repos):
                return repos[idx - 1]
        print("  Invalid option.")


def prompt_release_selection(
    releases: list[Release],
    repo_name: str = "M12Labs",
) -> Release | None:
    """Display available releases and let the user pick one.

    Args:
        releases:  List of releases fetched from GitHub.
        repo_name: Human-readable name of the source repo, used in the header.

    Returns the selected :class:`Release`, or ``None`` when the user goes back.
    Choosing "D" returns a synthetic Release with :data:`DEVELOP_BRANCH_TAG` so
    the caller can detect that the develop branch was requested.
    """
    page = 0
    total_pages = max(1, (len(releases) - 1) // _PAGE_SIZE + 1)

    while True:
        start = page * _PAGE_SIZE
        page_items = releases[start : start + _PAGE_SIZE]

        print(f"Available {repo_name} versions (page {page + 1}/{total_pages})\n")
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

