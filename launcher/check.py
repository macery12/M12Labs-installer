"""Read-only panel installation validator for the M12 Labs launcher.

Validates installed panel files against a SHA-256 hash manifest.  The
manifest is resolved in priority order:

  1. Remote release manifest for the version declared in ``config/app.php``
     (https://github.com/macery12/M12Labs/releases/download/v{ver}/manifest.json)
  2. Local ``<panel_root>/manifest.json`` as a fallback

This module only reads the filesystem and the network.  It never installs
packages, modifies project files, or makes any persistent changes.  Every
public function is safe to call at any time without side effects.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import urllib.request
import urllib.error
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

_logger = logging.getLogger("m12labs")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RELEASE_MANIFEST_URL = (
    "https://github.com/macery12/M12Labs/releases/download/v{version}/manifest.json"
)
MANIFEST_TIMEOUT = 10  # seconds

# Safe release-tag pattern accepted for remote manifest URL construction.
# Allows semantic versions like X.Y.Z plus optional prerelease/build suffixes
# such as ``2.0.0-m12-rc2.6`` while still rejecting slashes and other URL-
# significant characters that could be abused via a manipulated config/app.php
# version string.
_VERSION_RE = re.compile(
    r"^[0-9]{1,5}\.[0-9]{1,5}\.[0-9]{1,5}"
    r"(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?"
    r"(?:\+[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$"
)

# Directories/files scanned when looking for extra (untracked) files.
# Add new entries here to widen the scope of the extra-file search.
TRACKED_PATHS: list[str] = [
    "package.json",
    "composer.json",
    "artisan",
    "resources/scripts",
    "app",
    "config",
    "routes",
    "database",
]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class FileStatus(Enum):
    ORIGINAL = "ORIGINAL"  # hash matches manifest
    MODIFIED = "MODIFIED"  # hash differs from manifest
    MISSING  = "MISSING"   # listed in manifest but absent from disk
    EXTRA    = "EXTRA"     # present on disk but not listed in manifest


@dataclass
class FileResult:
    status: FileStatus
    path: str


# Legacy types kept so that main.py's import surface does not change.
class Status(Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class CheckResult:
    status: Status
    label: str
    message: str
    # Set for results that represent individual file checks; None for
    # infrastructure results (e.g. "Install root", "Manifest").
    file_status: FileStatus | None = None


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

def get_panel_version(install_root: Path) -> str | None:
    """Read the panel version string from ``config/app.php``.

    Returns ``None`` when the file is missing or the version key is absent.
    """
    app_php = install_root / "config" / "app.php"
    try:
        content = app_php.read_text(encoding="utf-8", errors="replace")
    except OSError:
        _logger.debug("Version lookup: config/app.php not found at %s", app_php)
        return None
    match = re.search(r"""['"]version['"]\s*=>\s*['"]([^'"]+)['"]""", content)
    version = match.group(1).strip() if match else None
    if version:
        _logger.debug("Version lookup: found version %r in %s", version, app_php)
    else:
        _logger.debug("Version lookup: no version key found in %s", app_php)
    return version


def _fetch_remote_manifest(version: str) -> dict | None:
    """Download the release manifest for *version* from GitHub.

    *version* must already be validated against ``_VERSION_RE`` by the caller
    (see :func:`load_manifest`) before being interpolated into the URL, which
    prevents SSRF via a manipulated ``config/app.php`` version string.
    Returns the parsed JSON dict, or ``None`` on any error.

    Prints live progress (URL, HTTP status, or error reason) to stdout so the
    user is not left waiting at a blank screen during the network call.
    """
    # Defense-in-depth: reject versions that did not pass the caller's gate.
    if not _VERSION_RE.match(version):
        print(f"  Skipping remote manifest – version {version!r} failed format check")
        return None

    _MAX_MANIFEST_BYTES = 1 * 1024 * 1024  # 1 MiB – guards against oversized responses

    url = RELEASE_MANIFEST_URL.format(version=version)
    _logger.debug("Fetching remote manifest from %s", url)
    print(f"  Fetching manifest from {url} ...", end=" ", flush=True)
    try:
        with urllib.request.urlopen(url, timeout=MANIFEST_TIMEOUT) as resp:  # noqa: S310
            status = resp.status
            if status == 200:
                try:
                    raw = resp.read(_MAX_MANIFEST_BYTES)
                    if len(raw) == _MAX_MANIFEST_BYTES:
                        _logger.debug("Remote manifest HTTP %s but response too large – skipping", status)
                        print(f"HTTP {status} OK (response too large – skipping)")
                        return None
                    data = json.loads(raw.decode("utf-8"))
                    _logger.debug("Remote manifest fetched successfully (HTTP %s)", status)
                    print(f"HTTP {status} OK")
                    return data
                except json.JSONDecodeError as exc:
                    _logger.debug("Remote manifest parse error (HTTP %s): %s", status, exc)
                    print(f"HTTP {status} OK (parse error: {exc})")
                    return None
            else:
                _logger.debug("Remote manifest unexpected HTTP status %s – skipping", status)
                print(f"HTTP {status} (unexpected – skipping remote manifest)")
                return None
    except urllib.error.HTTPError as exc:
        _logger.debug("Remote manifest HTTP error: %s %s", exc.code, exc.reason)
        print(f"HTTP {exc.code} {exc.reason}")
        return None
    except urllib.error.URLError as exc:
        _logger.debug("Remote manifest network error: %s", exc.reason)
        print(f"network error: {exc.reason}")
        return None
    except OSError as exc:
        _logger.debug("Remote manifest OS error: %s", exc)
        print(f"OS error: {exc}")
        return None


def _load_local_manifest(install_root: Path) -> dict | None:
    """Load ``manifest.json`` from the panel root directory.

    Returns the parsed JSON dict, or ``None`` when absent or malformed.
    """
    manifest_path = install_root / "manifest.json"
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_manifest(install_root: Path) -> tuple[dict | None, str]:
    """Resolve the hash manifest, trying the remote release URL first.

    Returns ``(manifest_dict, source_description)``.  When no manifest can be
    found, ``manifest_dict`` is ``None``.

    Progress and fallback notices are printed to stdout so the user can follow
    what is happening without enabling detailed mode.
    """
    version = get_panel_version(install_root)
    if version and _VERSION_RE.match(version):
        remote = _fetch_remote_manifest(version)
        if remote is not None:
            url = RELEASE_MANIFEST_URL.format(version=version)
            source = f"release manifest v{version} ({url})"
            _logger.info("Manifest source: %s", source)
            return remote, source
        print("  Remote manifest unavailable – falling back to local manifest")
        _logger.debug("Remote manifest unavailable – falling back to local manifest")
    elif version:
        # Version string exists but did not match the allowed release-tag pattern.
        print(f"  Version string {version!r} is not a supported release tag – skipping remote manifest")
        _logger.debug("Version string %r is not a supported release tag – skipping remote manifest", version)
    else:
        print("  No version found in config/app.php – skipping remote manifest")
        _logger.debug("No version found in config/app.php – skipping remote manifest")

    local = _load_local_manifest(install_root)
    if local is not None:
        source = f"local manifest ({install_root / 'manifest.json'})"
        _logger.info("Manifest source: %s", source)
        return local, source

    print("  No local manifest.json found either")
    _logger.debug("No manifest available for %s", install_root)
    return None, "no manifest available"


def _extract_files(manifest: dict) -> dict[str, str]:
    """Return a ``{relative_path: sha256_hex}`` mapping from a manifest dict.

    Supports both a flat ``{"path": "hash"}`` format and a nested
    ``{"files": {"path": "hash"}}`` format.  All hashes are normalized to
    lowercase for consistent comparison.
    """
    if "files" in manifest and isinstance(manifest["files"], dict):
        source = manifest["files"]
    else:
        source = manifest
    return {k: v.lower() for k, v in source.items() if isinstance(v, str)}


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    """Return the lowercase hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Hash-based file checks
# ---------------------------------------------------------------------------

def run_hash_checks(install_root: Path, manifest_files: dict[str, str]) -> list[FileResult]:
    """Compare installed files against the SHA-256 hashes in *manifest_files*.

    Returns one :class:`FileResult` per path in the manifest (ORIGINAL /
    MODIFIED / MISSING), plus one EXTRA result for every file found under
    :data:`TRACKED_PATHS` that is not listed in the manifest.

    This function is strictly read-only.
    """
    results: list[FileResult] = []

    # --- Check every path listed in the manifest ---
    for rel_path, expected_hash in sorted(manifest_files.items()):
        target = install_root / rel_path
        if not target.exists():
            _logger.debug("File %s: MISSING – not found on disk", rel_path)
            results.append(FileResult(FileStatus.MISSING, rel_path))
            continue
        if not target.is_file():
            # Directories are not individually hashed; skip silently.
            continue
        try:
            actual = _sha256_file(target)
        except OSError:
            _logger.debug("File %s: MISSING – could not read (OSError)", rel_path)
            results.append(FileResult(FileStatus.MISSING, rel_path))
            continue
        if actual == expected_hash:
            _logger.debug("File %s: ORIGINAL (hash matched: %s)", rel_path, actual)
            results.append(FileResult(FileStatus.ORIGINAL, rel_path))
        else:
            _logger.debug(
                "File %s: MODIFIED – expected %s, got %s", rel_path, expected_hash, actual
            )
            results.append(FileResult(FileStatus.MODIFIED, rel_path))

    # --- Detect extra files in tracked paths ---
    for tracked in TRACKED_PATHS:
        target = install_root / tracked
        if not target.exists():
            continue
        candidate_files: list[Path] = (
            [target] if target.is_file()
            else sorted(p for p in target.rglob("*") if p.is_file())
        )
        for file_path in candidate_files:
            rel = str(file_path.relative_to(install_root))
            if rel not in manifest_files:
                _logger.debug("File %s: EXTRA – untracked file not in manifest", rel)
                results.append(FileResult(FileStatus.EXTRA, rel))

    return results


# ---------------------------------------------------------------------------
# Public interface consumed by main.py
# ---------------------------------------------------------------------------

def run_checks(install_root: Path) -> list[CheckResult]:
    """Run all validation checks against *install_root*.

    Loads the appropriate manifest and compares every listed file's SHA-256
    hash against what is present on disk.  Falls back to existence-only checks
    when no manifest is available.

    This function is strictly read-only.  It performs no installs, builds,
    deletions, or writes to the project tree.
    """
    results: list[CheckResult] = []

    if not install_root.exists():
        _logger.error("Check failed: install root not found: %s", install_root)
        results.append(
            CheckResult(Status.FAIL, "Install root", f"Directory not found: {install_root}")
        )
        return results

    if not install_root.is_dir():
        _logger.error("Check failed: install root is not a directory: %s", install_root)
        results.append(
            CheckResult(Status.FAIL, "Install root", f"Not a directory: {install_root}")
        )
        return results

    # Try to load a hash manifest.
    manifest, source = load_manifest(install_root)

    if manifest is None:
        _logger.warning("Check: no manifest available for %s – falling back to existence checks", install_root)
        results.append(
            CheckResult(Status.WARN, "Manifest", f"Could not load manifest – {source}")
        )
        # Fallback: existence-only checks for the important paths.
        for tracked in TRACKED_PATHS:
            target = install_root / tracked
            if not target.exists():
                _logger.debug("Existence check: MISSING – %s", target)
                results.append(CheckResult(Status.FAIL, tracked, f"Not found: {target}"))
            else:
                _logger.debug("Existence check: present – %s", target)
                results.append(CheckResult(Status.PASS, tracked, f"Present: {target}"))
        return results

    results.append(CheckResult(Status.PASS, "Manifest", f"Loaded from {source}"))

    # Hash-based validation.
    manifest_files = _extract_files(manifest)
    _logger.debug("Hash check: comparing %d files from manifest", len(manifest_files))
    for fr in run_hash_checks(install_root, manifest_files):
        if fr.status == FileStatus.ORIGINAL:
            results.append(CheckResult(Status.PASS, fr.path, "original", file_status=fr.status))
        elif fr.status == FileStatus.MODIFIED:
            results.append(CheckResult(Status.FAIL, fr.path, "MODIFIED – hash mismatch", file_status=fr.status))
        elif fr.status == FileStatus.MISSING:
            results.append(CheckResult(Status.FAIL, fr.path, "MISSING – not found on disk", file_status=fr.status))
        elif fr.status == FileStatus.EXTRA:
            results.append(CheckResult(Status.WARN, fr.path, "extra / untracked file", file_status=fr.status))

    return results


def format_results(results: list[CheckResult]) -> str:
    """Return a human-readable summary of check results."""
    symbols = {Status.PASS: "[PASS]", Status.WARN: "[WARN]", Status.FAIL: "[FAIL]"}
    lines = [f"  {symbols[r.status]} {r.label}: {r.message}" for r in results]
    return "\n".join(lines)


def format_results_concise(results: list[CheckResult]) -> str:
    """Return a summary with counts and the path of every non-passing file.

    In non-debug mode this is the default view.  It always names modified,
    missing, or extra files so the user can act without enabling detailed mode.
    """
    total = len(results)
    passed = sum(1 for r in results if r.status == Status.PASS)
    warned = sum(1 for r in results if r.status == Status.WARN)
    failed = sum(1 for r in results if r.status == Status.FAIL)

    parts = [f"{passed}/{total} checks passed"]
    if warned:
        parts.append(f"{warned} warning(s)")
    if failed:
        parts.append(f"{failed} failure(s)")

    lines: list[str] = []

    # Always surface the manifest source so users know what was checked against.
    manifest_result = next((r for r in results if r.label == "Manifest"), None)
    if manifest_result is not None:
        prefix = "  ✓" if manifest_result.status == Status.PASS else "  !"
        lines.append(f"{prefix} Manifest: {manifest_result.message}")
        lines.append("")

    lines.append("  " + ", ".join(parts))

    # List every non-passing file with its full relative path and reason.
    symbols = {Status.FAIL: "[FAIL]", Status.WARN: "[WARN]"}
    non_passing = [
        r for r in results
        if r.status in (Status.FAIL, Status.WARN) and r.label != "Manifest"
    ]
    if non_passing:
        lines.append("")
        for r in non_passing:
            lines.append(f"  {symbols[r.status]} {r.label}  –  {r.message}")

    return "\n".join(lines)


def has_failures(results: list[CheckResult]) -> bool:
    """Return True if any check resulted in FAIL status."""
    return any(r.status == Status.FAIL for r in results)


def has_modified_files(results: list[CheckResult]) -> bool:
    """Return True if any file was detected as MODIFIED or MISSING."""
    return any(
        r.file_status in (FileStatus.MODIFIED, FileStatus.MISSING)
        for r in results
    )
