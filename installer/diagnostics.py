"""Diagnostic reporting for the M12Labs panel installer.

Collects troubleshooting data from all relevant sources and prints a
formatted report.  The caller is responsible for any post-display UI work
(e.g. calling ``_pause_and_clear()``).

Public API::

    run_diagnostics(install_path, cfg) -> None
"""

from __future__ import annotations

import io
import platform
import re
import shutil
import stat as _stat
import subprocess
from pathlib import Path

from installer.system import fmt_size as _fmt_size

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Directory (relative to install_path) where Laravel writes daily log files.
_PANEL_LOGS_DIR = Path("storage") / "logs"
# Number of lines to tail from the panel log.
_PANEL_LOG_TAIL_LINES = 50

# paste.rs upload endpoint
_PASTE_RS_URL = "https://paste.rs/"

# Regex matching KEY=VALUE (env) or key: value (YAML) patterns whose values
# should be redacted in diagnostic output to prevent accidental secret leakage.
_SECRET_REDACT_RE = re.compile(
    r"(?i)"
    r"("
    r"[A-Z_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|KEY|AUTH|CREDENTIAL)[A-Z_]*\s*=\s*"  # ENV
    r"|[\w]*(?:password|passwd|token|secret|key|auth|credential)[\w]*\s*:\s*"      # YAML
    r")"
    r"""('[^']*'|"[^"]*"|\S+)""",  # value: single-quoted, double-quoted, or bare token
)

# Well-known Wings daemon config paths.
_WINGS_CONFIG_PATHS = (
    Path("/etc/pterodactyl/config.yml"),
    Path("/etc/wings/config.yml"),
)

# Well-known Wings log paths (in addition to journalctl).
_WINGS_LOG_PATHS = (
    Path("/var/log/wings/wings.log"),
    Path("/var/log/pterodactyl/wings.log"),
)

# Number of log/journal lines to tail in each service section.
_SERVICE_LOG_TAIL_LINES = 30


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

def _redact_line(line: str) -> str:
    """Replace secret values in *line* with ``[REDACTED]``."""
    return _SECRET_REDACT_RE.sub(r"\1[REDACTED]", line)


def _tail_file(path: Path, n: int) -> list[str]:
    """Return the last *n* lines of *path*, or an empty list when unreadable."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = text.splitlines()
    return lines[-n:] if len(lines) > n else lines


def _journalctl_tail(service: str, n: int) -> list[str]:
    """Return the last *n* journal lines for *service* (secrets redacted).

    Returns an empty list when ``journalctl`` is unavailable or the unit has
    no log entries.
    """
    if not shutil.which("journalctl"):
        return []
    try:
        r = subprocess.run(
            ["journalctl", "-u", service, f"-n{n}", "--no-pager", "--output=short"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return [_redact_line(line) for line in (r.stdout or "").splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return []


# ---------------------------------------------------------------------------
# Wings helpers
# ---------------------------------------------------------------------------

def _find_wings_config() -> Path | None:
    """Return the first Wings config file found, or ``None``."""
    for p in _WINGS_CONFIG_PATHS:
        if p.exists():
            return p
    return None


def _wings_config_summary(config_path: Path) -> list[str]:
    """Return key (non-secret) fields from the Wings YAML config.

    Reads the file as plain text and extracts interesting fields without
    using a YAML parser (keeping the dependency footprint zero).  Secret
    fields are shown as ``[REDACTED]``.
    """
    try:
        text = config_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ["(could not read config)"]

    # Fields we want to surface; everything else is omitted.
    interesting = {
        "debug", "uuid", "token_id", "token", "remote",
        "listen", "port", "ssl", "enabled",
        "log_directory", "timezone",
    }
    lines_out: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Capture YAML key (word chars or hyphens): value at top-level and one level of indent
        m = re.match(r"^(\s*)([\w-]+)\s*:\s*(.*)", raw_line)
        if m:
            key = m.group(2).lower()
            if key in interesting:
                lines_out.append(_redact_line(raw_line.rstrip()))
    return lines_out or ["(no relevant fields found)"]


# ---------------------------------------------------------------------------
# Panel log helper
# ---------------------------------------------------------------------------

def _find_latest_panel_log(install_path: Path) -> Path | None:
    """Return the most recent Laravel log file under *install_path*/storage/logs/.

    Laravel writes daily log files named ``laravel-YYYY-MM-DD.log``.  This
    function finds the most recent one by filename (lexicographic sort is
    correct for ISO-date filenames).  Falls back to ``laravel.log`` when no
    dated files are present.  Returns ``None`` when the logs directory does
    not exist or contains no recognisable log file.
    """
    log_dir = install_path / _PANEL_LOGS_DIR
    if not log_dir.is_dir():
        return None

    # Collect dated log files: laravel-YYYY-MM-DD.log
    dated = sorted(
        log_dir.glob("laravel-????-??-??.log"),
        key=lambda p: p.name,
        reverse=True,
    )
    if dated:
        return dated[0]

    # Fall back to the non-dated file if it exists
    fallback = log_dir / "laravel.log"
    return fallback if fallback.exists() else None


# ---------------------------------------------------------------------------
# paste.rs upload
# ---------------------------------------------------------------------------

def _upload_to_paste_rs(content: str) -> tuple[bool, str]:
    """Upload *content* to paste.rs and return ``(success, url_or_error)``.

    Returns ``(True, url)`` on HTTP 201 (created) or 206 (partial upload).
    Returns ``(False, error_message)`` on any other response or network error.
    """
    import urllib.request
    import urllib.error

    data = content.encode("utf-8")
    req = urllib.request.Request(
        _PASTE_RS_URL,
        data=data,
        method="POST",
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            url = resp.read().decode("utf-8").strip()
            if status in (201, 206):
                return True, url
            return False, f"Unexpected HTTP {status}: {url}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        return False, f"Network error: {exc.reason}"
    except OSError as exc:
        return False, f"Error: {exc}"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_diagnostics(install_path: Path, cfg) -> None:
    """Gather and display diagnostic information for support / debugging.

    Information is presented in this order so the most actionable details
    appear first:

     1. Panel status & version
     2. Panel log (last :data:`_PANEL_LOG_TAIL_LINES` lines of the most recent
        ``laravel-YYYY-MM-DD.log`` file)
     3. Key directory permissions
     4. Service status (PHP-FPM, MariaDB, Nginx, Wings, Redis, jxctl worker)
     5. Wings details (config summary + recent log/journal lines)
     6. Nginx details (config test + error log tail)
     7. MariaDB details (version + connection probe)
     8. PHP / Runtime (version, key extensions, Composer)
     9. System overview (OS, uptime, load, disk, RAM)
    10. Installer configuration summary
    11. Installer log file locations

    All output is captured simultaneously so the full report can be uploaded
    to paste.rs for easy sharing.  Secrets are redacted in every section.

    The caller is responsible for any post-display UI work (e.g.
    ``_pause_and_clear()``).
    """
    from installer.steps.files import detect_panel_state, read_installed_version

    width = 60
    sep = "─" * width

    # Capture all output so we can offer a paste.rs upload at the end.
    _buf = io.StringIO()

    def _p(*args, **kwargs) -> None:
        """print() that writes to both the terminal and the capture buffer."""
        print(*args, **kwargs)
        print(*args, file=_buf)

    _p()
    _p("=" * width)
    _p("  M12Labs Diagnostics")
    _p("=" * width)

    # ------------------------------------------------------------------ #
    # 1. Panel status
    # ------------------------------------------------------------------ #
    _p()
    _p(sep)
    _p("  Panel Status")
    _p(sep)

    state = detect_panel_state(install_path)
    state_label = {
        "existing": "Installed (panel + .env found)",
        "partial":  "Partial (panel files present, .env missing)",
        "fresh":    "Not installed (no panel files found)",
    }.get(state, state)
    _p(f"  Install path : {install_path}")
    _p(f"  State        : {state_label}")

    version = read_installed_version(install_path)
    _p(f"  Version      : {f'v{version}' if version else 'unknown / not installed'}")

    env_path = install_path / ".env"
    _p(f"  .env present : {'Yes' if env_path.exists() else 'No'}")

    # ------------------------------------------------------------------ #
    # 2. Panel log
    # ------------------------------------------------------------------ #
    _p()
    _p(sep)
    _p("  Panel Log  (storage/logs/laravel-YYYY-MM-DD.log)")
    _p(sep)

    panel_log = _find_latest_panel_log(install_path)
    if panel_log is not None:
        _p(f"  Log file : {panel_log}")
        try:
            size = panel_log.stat().st_size
            _p(f"  Size     : {_fmt_size(size)}")
        except OSError:
            pass
        lines = _tail_file(panel_log, _PANEL_LOG_TAIL_LINES)
        if lines:
            _p(f"  Last {_PANEL_LOG_TAIL_LINES} lines:")
            _p()
            for line in lines:
                _p(f"    {_redact_line(line)}")
        else:
            _p("  (log file is empty)")
    else:
        _p(f"  No panel log found under {install_path / _PANEL_LOGS_DIR}")
        _p("  (Panel may not be installed or has never produced log output.)")

    # ------------------------------------------------------------------ #
    # 3. Key directory permissions
    # ------------------------------------------------------------------ #
    _p()
    _p(sep)
    _p("  Key Directory / File Permissions")
    _p(sep)

    check_paths = [
        install_path,
        install_path / "storage",
        install_path / "storage" / "logs",
        install_path / "bootstrap" / "cache",
        install_path / ".env",
    ]
    for p in check_paths:
        if p.exists():
            try:
                st = p.stat()
                mode_str = _stat.filemode(st.st_mode)
                try:
                    import pwd as _pwd, grp as _grp
                    owner = _pwd.getpwuid(st.st_uid).pw_name
                    group = _grp.getgrgid(st.st_gid).gr_name
                except Exception:
                    owner = str(st.st_uid)
                    group = str(st.st_gid)
                _p(f"  {mode_str}  {owner}:{group}  {p}")
            except OSError:
                _p(f"  (could not stat {p})")
        else:
            _p(f"  (not found) {p}")

    # ------------------------------------------------------------------ #
    # 4. Service status
    # ------------------------------------------------------------------ #
    _p()
    _p(sep)
    _p("  Service Status")
    _p(sep)

    def _service_status(service: str) -> str:
        if not shutil.which("systemctl"):
            return "systemctl not available"
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() or result.stderr.strip() or "unknown"
        except subprocess.TimeoutExpired:
            return "timeout"

    # PHP CLI version
    php_ver = "not found"
    if shutil.which("php"):
        try:
            r = subprocess.run(
                ["php", "--version"], capture_output=True, text=True, timeout=5,
            )
            php_output_lines = (r.stdout or r.stderr or "").splitlines()
            php_ver = php_output_lines[0].strip() if php_output_lines else "unknown"
        except subprocess.TimeoutExpired:
            php_ver = "timeout"
    _p(f"  PHP CLI          : {php_ver}")

    # PHP-FPM – try common service names
    for fpm_svc in ("php8.3-fpm", "php8.2-fpm", "php8.1-fpm", "php-fpm"):
        fpm_status = _service_status(fpm_svc)
        if fpm_status not in ("inactive", "unknown", "systemctl not available"):
            _p(f"  PHP-FPM          : {fpm_status} ({fpm_svc})")
            break
    else:
        fpm_status = _service_status("php8.3-fpm")
        _p(f"  PHP-FPM          : {fpm_status} (php8.3-fpm)")

    _p(f"  MariaDB          : {_service_status('mariadb')}")
    _p(f"  MySQL            : {_service_status('mysql')}")
    _p(f"  Nginx            : {_service_status('nginx')}")
    _p(f"  Wings            : {_service_status('wings')}")
    _p(f"  Redis            : {_service_status('redis-server')}")
    _p(f"  jxctl worker     : {_service_status('jxctl')} (legacy)")
    _p(f"  m12labs worker   : {_service_status('m12labs')}")

    # ------------------------------------------------------------------ #
    # 5. Wings details
    # ------------------------------------------------------------------ #
    _p()
    _p(sep)
    _p("  Wings Details")
    _p(sep)

    wings_bin = shutil.which("wings")
    if wings_bin:
        try:
            wv = subprocess.run(
                [wings_bin, "version"],
                capture_output=True, text=True, timeout=5,
            )
            wings_ver = (wv.stdout or wv.stderr or "").strip().splitlines()
            _p(f"  Binary           : {wings_bin}")
            _p(f"  Version          : {wings_ver[0] if wings_ver else 'unknown'}")
        except subprocess.TimeoutExpired:
            _p(f"  Binary           : {wings_bin}")
            _p("  Version          : (timeout)")
    else:
        _p("  Binary           : not found on PATH")

    wings_cfg = _find_wings_config()
    if wings_cfg:
        _p(f"  Config           : {wings_cfg}")
        summary = _wings_config_summary(wings_cfg)
        for line in summary:
            _p(f"    {line}")
    else:
        search_paths = ", ".join(str(p) for p in _WINGS_CONFIG_PATHS)
        _p(f"  Config           : not found (checked {search_paths})")

    # Wings log file
    wings_log: Path | None = None
    for wlp in _WINGS_LOG_PATHS:
        if wlp.exists():
            wings_log = wlp
            break
    if wings_log:
        _p(f"  Log file         : {wings_log}")
        try:
            _p(f"  Log size         : {_fmt_size(wings_log.stat().st_size)}")
        except OSError:
            pass
        wlines = _tail_file(wings_log, _SERVICE_LOG_TAIL_LINES)
        if wlines:
            _p(f"  Last {_SERVICE_LOG_TAIL_LINES} lines:")
            for line in wlines:
                _p(f"    {_redact_line(line)}")
        else:
            _p("  (log file is empty)")
    else:
        _p("  Log file         : not found — falling back to journalctl")
        journal_lines = _journalctl_tail("wings", _SERVICE_LOG_TAIL_LINES)
        if journal_lines:
            _p(f"  Last {_SERVICE_LOG_TAIL_LINES} journal lines:")
            for line in journal_lines:
                _p(f"    {line}")
        else:
            _p("  (no journal entries found for wings)")

    # ------------------------------------------------------------------ #
    # 6. Nginx details
    # ------------------------------------------------------------------ #
    _p()
    _p(sep)
    _p("  Nginx Details")
    _p(sep)

    if shutil.which("nginx"):
        try:
            nt = subprocess.run(
                ["nginx", "-t"], capture_output=True, text=True, timeout=10,
            )
            # nginx -t writes to stderr
            nt_out = (nt.stdout + nt.stderr).strip()
            ok_label = "passed" if nt.returncode == 0 else "FAILED"
            _p(f"  Config test      : {ok_label}")
            for line in nt_out.splitlines():
                _p(f"    {line}")
        except subprocess.TimeoutExpired:
            _p("  Config test      : timeout")
    else:
        _p("  nginx binary     : not found on PATH")

    nginx_error_log = Path("/var/log/nginx/error.log")
    if nginx_error_log.exists():
        _p(f"  Error log        : {nginx_error_log}")
        try:
            _p(f"  Size             : {_fmt_size(nginx_error_log.stat().st_size)}")
        except OSError:
            pass
        nlines = _tail_file(nginx_error_log, _SERVICE_LOG_TAIL_LINES)
        if nlines:
            _p(f"  Last {_SERVICE_LOG_TAIL_LINES} lines:")
            for line in nlines:
                _p(f"    {_redact_line(line)}")
        else:
            _p("  (error log is empty)")
    else:
        _p("  Error log        : /var/log/nginx/error.log not found")
        journal_lines = _journalctl_tail("nginx", _SERVICE_LOG_TAIL_LINES)
        if journal_lines:
            _p(f"  Last {_SERVICE_LOG_TAIL_LINES} journal lines:")
            for line in journal_lines:
                _p(f"    {line}")
        else:
            _p("  (no journal entries found for nginx)")

    # ------------------------------------------------------------------ #
    # 7. MariaDB / MySQL details
    # ------------------------------------------------------------------ #
    _p()
    _p(sep)
    _p("  MariaDB / MySQL Details")
    _p(sep)

    for mysql_bin in ("mariadb", "mysql"):
        if shutil.which(mysql_bin):
            try:
                mv = subprocess.run(
                    [mysql_bin, "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                db_ver = (mv.stdout or mv.stderr or "").strip().splitlines()
                _p(f"  Version          : {db_ver[0] if db_ver else 'unknown'}")
            except subprocess.TimeoutExpired:
                _p(f"  Version          : timeout ({mysql_bin})")
            break
    else:
        _p("  Client binary    : mariadb / mysql not found on PATH")

    # Socket/connection probe (no password — only tests if the unix socket
    # is accessible without credentials, which is common for root/sudo installs)
    sock_found = False
    for sock_path in (
        Path("/var/run/mysqld/mysqld.sock"),
        Path("/var/lib/mysql/mysql.sock"),
        Path("/tmp/mysql.sock"),
    ):
        try:
            if sock_path.exists():
                _p(f"  Socket           : {sock_path} (found)")
                sock_found = True
                break
        except OSError:
            pass
    if not sock_found:
        _p("  Socket           : not found at common paths")

    # journalctl fallback for mariadb
    journal_lines = _journalctl_tail("mariadb", _SERVICE_LOG_TAIL_LINES)
    if not journal_lines:
        journal_lines = _journalctl_tail("mysql", _SERVICE_LOG_TAIL_LINES)
    if journal_lines:
        _p(f"  Last {_SERVICE_LOG_TAIL_LINES} journal lines:")
        for line in journal_lines:
            _p(f"    {line}")
    else:
        _p("  (no journal entries found for mariadb/mysql)")

    # ------------------------------------------------------------------ #
    # 8. PHP / Runtime
    # ------------------------------------------------------------------ #
    _p()
    _p(sep)
    _p("  PHP / Runtime")
    _p(sep)

    if shutil.which("php"):
        # Full version string
        try:
            r = subprocess.run(
                ["php", "--version"], capture_output=True, text=True, timeout=5,
            )
            for line in (r.stdout or "").splitlines()[:3]:
                _p(f"  {line}")
        except subprocess.TimeoutExpired:
            _p("  php --version    : timeout")

        # Loaded php.ini files
        try:
            r = subprocess.run(
                ["php", "--ini"], capture_output=True, text=True, timeout=5,
            )
            for line in (r.stdout or "").splitlines():
                _p(f"  {line}")
        except subprocess.TimeoutExpired:
            pass

        # Key extensions
        _p()
        _p("  Key extension status:")
        required_exts = [
            "bcmath", "ctype", "curl", "dom", "fileinfo",
            "gd", "mbstring", "openssl", "pdo", "pdo_mysql",
            "tokenizer", "xml", "zip",
        ]
        try:
            r = subprocess.run(
                ["php", "-m"], capture_output=True, text=True, timeout=5,
            )
            loaded = {e.strip().lower() for e in (r.stdout or "").splitlines()}
            for ext in required_exts:
                status = "✓ loaded" if ext.lower() in loaded else "✗ MISSING"
                _p(f"    {ext:<15} {status}")
        except subprocess.TimeoutExpired:
            _p("    (php -m timed out)")
    else:
        _p("  PHP              : not found on PATH")

    # Composer
    if shutil.which("composer"):
        try:
            r = subprocess.run(
                ["composer", "--version", "--no-ansi"],
                capture_output=True, text=True, timeout=10,
            )
            comp_ver = (r.stdout or r.stderr or "").strip().splitlines()
            _p(f"  Composer         : {comp_ver[0] if comp_ver else 'unknown'}")
        except subprocess.TimeoutExpired:
            _p("  Composer         : timeout")
    else:
        _p("  Composer         : not found on PATH")

    # ------------------------------------------------------------------ #
    # 9. System overview
    # ------------------------------------------------------------------ #
    _p()
    _p(sep)
    _p("  System Overview")
    _p(sep)

    _p(f"  OS               : {platform.platform()}")
    _p(f"  Python           : {platform.python_version()}")

    # Uptime
    try:
        r = subprocess.run(
            ["uptime", "-p"], capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            _p(f"  Uptime           : {r.stdout.strip()}")
    except (OSError, subprocess.TimeoutExpired):
        pass

    # Load average
    try:
        load_fields = Path("/proc/loadavg").read_text(encoding="utf-8").split()
        _p(f"  Load (1/5/15m)   : {load_fields[0]} / {load_fields[1]} / {load_fields[2]}")
    except (OSError, IndexError):
        pass

    # Disk usage for install_path (or its parent when it doesn't exist)
    disk_target = install_path if install_path.exists() else install_path.parent
    try:
        disk = shutil.disk_usage(disk_target)
        _p(
            f"  Disk ({disk_target}) : "
            f"{_fmt_size(disk.free)} free / {_fmt_size(disk.total)} total"
        )
    except OSError:
        _p("  Disk             : (could not determine)")

    # Memory (Linux /proc/meminfo)
    try:
        meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
        def _meminfo_kb(key: str) -> int | None:
            m = re.search(rf"^{re.escape(key)}:\s+(\d+)", meminfo, re.MULTILINE)
            return int(m.group(1)) * 1024 if m else None
        mem_total = _meminfo_kb("MemTotal")
        mem_avail = _meminfo_kb("MemAvailable")
        if mem_total and mem_avail:
            _p(
                f"  RAM              : "
                f"{_fmt_size(mem_avail)} available / {_fmt_size(mem_total)} total"
            )
    except OSError:
        pass

    # ------------------------------------------------------------------ #
    # 10. Installer configuration summary
    # ------------------------------------------------------------------ #
    _p()
    _p(sep)
    _p("  Installer Configuration")
    _p(sep)
    _p(f"  Install path     : {cfg.install_path}")
    _p(f"  DB name          : {cfg.db_name}")
    _p(f"  DB user          : {cfg.db_user}")
    _p(f"  Selected release : {cfg.selected_release or '(none – use default)'}")
    _p(f"  Text logs        : {cfg.text_logs_enabled}")

    # ------------------------------------------------------------------ #
    # 11. Installer log files
    # ------------------------------------------------------------------ #
    _p()
    _p(sep)
    _p("  Installer Log Files")
    _p(sep)

    from installer.log import LOG_DIR_NAME
    log_dir = cfg.install_path / LOG_DIR_NAME
    if log_dir.is_dir():
        log_files = sorted(log_dir.glob("*.txt"), reverse=True)
        if log_files:
            _p(f"  Logs directory : {log_dir}")
            for lf in log_files[:5]:
                try:
                    sz = _fmt_size(lf.stat().st_size)
                except OSError:
                    sz = "?"
                _p(f"    {lf.name}  ({sz})")
            if len(log_files) > 5:
                _p(f"    … and {len(log_files) - 5} more")
        else:
            _p(f"  Logs directory exists but contains no log files: {log_dir}")
    else:
        _p(f"  No installer logs found (expected at {log_dir})")

    _p()
    _p("=" * width)

    # ------------------------------------------------------------------ #
    # paste.rs upload
    # ------------------------------------------------------------------ #
    print()
    try:
        answer = input("  Upload diagnostics to paste.rs for easy sharing? [y/N]: ").strip().lower()
    except EOFError:
        answer = "n"

    if answer in ("y", "yes"):
        print("  Uploading to paste.rs …")
        ok, result = _upload_to_paste_rs(_buf.getvalue())
        if ok:
            print("  ✓ Uploaded! Share this link with support:")
            print(f"    {result}")
        else:
            print(f"  ✗ Upload failed: {result}")
    else:
        print("  (Skipping upload.)")
