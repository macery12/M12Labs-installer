"""Read-only panel installation validator for the M12 Labs launcher.

This module only reads the filesystem.  It never installs packages, modifies
project files, or makes any persistent changes.  Every public function is
safe to call at any time without side effects.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Status(Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class CheckResult:
    status: Status
    label: str
    message: str


# Each entry: (display label, path relative to install root, "file"|"dir", check_writable)
# Add new items here to extend the validator without changing any other function.
REQUIRED_ITEMS: list[tuple[str, str, str, bool]] = [
    ("package.json",       "package.json",       "file", False),
    ("composer.json",      "composer.json",       "file", False),
    ("artisan",            "artisan",             "file", False),
    ("resources/scripts/", "resources/scripts",   "dir",  False),
    ("app/",               "app",                 "dir",  False),
    ("config/",            "config",              "dir",  False),
    ("routes/",            "routes",              "dir",  False),
    ("database/",          "database",            "dir",  False),
]


def _check_item(
    root: Path,
    label: str,
    relative_path: str,
    expected_type: str,
    check_writable: bool,
) -> CheckResult:
    """Validate a single file or directory entry under the install root."""
    target = root / relative_path

    if not target.exists():
        return CheckResult(Status.FAIL, label, f"Not found: {target}")

    if expected_type == "file" and not target.is_file():
        return CheckResult(Status.FAIL, label, f"Expected a file: {target}")

    if expected_type == "dir" and not target.is_dir():
        return CheckResult(Status.FAIL, label, f"Expected a directory: {target}")

    if not os.access(target, os.R_OK):
        return CheckResult(Status.FAIL, label, f"Not readable: {target}")

    if check_writable and not os.access(target, os.W_OK):
        return CheckResult(Status.WARN, label, f"Not writable: {target}")

    return CheckResult(Status.PASS, label, f"OK: {target}")


def run_checks(install_root: Path) -> list[CheckResult]:
    """Run all validation checks against the given install root.

    This function is strictly read-only.  It performs no installs, builds,
    deletions, or writes to the project tree.

    Returns a list of CheckResult objects, one per checked item.  When the
    install root itself cannot be accessed, a single FAIL result is returned
    immediately and no further checks are attempted.
    """
    results: list[CheckResult] = []

    if not install_root.exists():
        results.append(
            CheckResult(Status.FAIL, "Install root", f"Directory not found: {install_root}")
        )
        return results

    if not install_root.is_dir():
        results.append(
            CheckResult(Status.FAIL, "Install root", f"Not a directory: {install_root}")
        )
        return results

    for label, rel_path, expected_type, check_writable in REQUIRED_ITEMS:
        results.append(_check_item(install_root, label, rel_path, expected_type, check_writable))

    return results


def format_results(results: list[CheckResult]) -> str:
    """Return a human-readable summary of check results."""
    symbols = {Status.PASS: "[PASS]", Status.WARN: "[WARN]", Status.FAIL: "[FAIL]"}
    lines = [f"  {symbols[r.status]} {r.label}: {r.message}" for r in results]
    return "\n".join(lines)


def has_failures(results: list[CheckResult]) -> bool:
    """Return True if any check resulted in FAIL status."""
    return any(r.status == Status.FAIL for r in results)
