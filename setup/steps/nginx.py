"""NGINX configuration helpers for the M12Labs panel installer."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from setup.system import install_packages, with_privilege

_CONF_TEMPLATE = Path(__file__).resolve().parent.parent / "panel.conf"
_NGINX_SITES_AVAILABLE = Path("/etc/nginx/sites-available")
_NGINX_SITES_ENABLED = Path("/etc/nginx/sites-enabled")
_CONF_NAME = "m12labs"

_CERTBOT_PACKAGES = ["certbot", "python3-certbot-nginx"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], *, capture: bool = False) -> tuple[bool, str]:
    """Run *cmd*, optionally capturing output.

    Returns ``(success, combined_output)``.  When *capture* is False,
    stdin/stdout/stderr pass through to the terminal unchanged.
    """
    if capture:
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = (result.stdout or "") + (result.stderr or "")
        return result.returncode == 0, output
    else:
        result = subprocess.run(cmd)
        return result.returncode == 0, ""


def _sudo(cmd: list[str]) -> list[str]:
    """Prefix *cmd* with sudo unless already root."""
    privileged = with_privilege(cmd)
    return privileged if privileged is not None else cmd


def _confirm(prompt: str) -> bool:
    """Ask a yes/no question; return True only for an explicit 'y'/'yes'."""
    try:
        answer = input(f"  {prompt} [y/N]: ").strip().lower()
    except EOFError:
        answer = ""
    return answer in ("y", "yes")


# ---------------------------------------------------------------------------
# Step helpers
# ---------------------------------------------------------------------------

def _show_dns_checklist(domain: str) -> bool:
    """Display DNS/readiness checklist and ask for confirmation.

    Returns False if the user is not ready to proceed.
    """
    print()
    print("  Before continuing, confirm the following:")
    print()
    print(f"  [ ] 1. Your domain  {domain}  has an A/AAAA record")
    print("           pointing to this server's public IP address.")
    print("  [ ] 2. The DNS change has fully propagated")
    print("           (may take a few minutes to several hours).")
    print("  [ ] 3. Port 80 (HTTP) is open in your firewall –")
    print("           Let's Encrypt uses it to verify domain ownership.")
    print("  [ ] 4. Port 443 (HTTPS) is open for future HTTPS traffic.")
    print()
    return _confirm("All of the above are done – proceed with NGINX and SSL setup?")


def _ensure_nginx() -> bool:
    """Make sure nginx is installed; install it if missing.

    Returns True when nginx is available after the check.
    """
    if shutil.which("nginx"):
        print("  nginx: already installed.")
        return True

    print("  nginx not found – installing…")
    if not install_packages(["nginx"]):
        print("  ✗ Failed to install nginx.")
        return False

    if not shutil.which("nginx"):
        print("  ✗ nginx binary not found after installation.")
        return False

    print("  ✓ nginx installed.")
    return True


def _ensure_certbot() -> bool:
    """Make sure certbot and python3-certbot-nginx are installed.

    Returns True when certbot is available after the check.
    """
    if shutil.which("certbot"):
        print("  certbot: already installed.")
        return True

    print("  certbot not found – installing…")
    if not install_packages(_CERTBOT_PACKAGES):
        print("  ✗ Failed to install certbot.")
        return False

    if not shutil.which("certbot"):
        print("  ✗ certbot binary not found after installation.")
        return False

    print("  ✓ certbot installed.")
    return True


def _request_certificate(domain: str) -> bool:
    """Run certbot to obtain an SSL certificate for *domain*.

    Uses ``certonly --nginx`` so certbot leverages the already-installed nginx
    (and its default site config) as the ACME challenge handler, without
    permanently modifying any nginx config itself.  The domain-specific
    panel.conf is written separately after the cert is successfully issued.

    Passes stdin/stdout/stderr through so certbot can interact with the user.
    Returns True on success.
    """
    print()
    print(f"  Requesting SSL certificate for {domain} via Let's Encrypt…")
    print()
    cmd = _sudo(["certbot", "certonly", "--nginx", "-d", domain])
    ok, _ = _run(cmd, capture=False)
    if not ok:
        print()
        print("  ✗ certbot failed to obtain a certificate.")
        print("    Common causes:")
        print("    • DNS has not propagated yet.")
        print("    • Port 80 is blocked by a firewall.")
        print("    • The domain does not resolve to this server.")
        return False
    print()
    print(f"  ✓ SSL certificate issued for {domain}.")
    return True


def _write_nginx_config(install_path: Path, domain: str) -> bool:
    """Render panel.conf and write it to sites-available.

    Returns True on success.
    """
    if not _CONF_TEMPLATE.exists():
        print(f"  ✗ Template not found: {_CONF_TEMPLATE}")
        return False

    if not _NGINX_SITES_AVAILABLE.is_dir():
        print(f"  ✗ Directory not found: {_NGINX_SITES_AVAILABLE}")
        print("  Is nginx installed correctly?")
        return False

    template = _CONF_TEMPLATE.read_text()
    config = template.replace("<domain>", domain)
    config = config.replace(
        "root /var/www/m12labs/public;",
        f"root {install_path / 'public'};",
    )

    dest = _NGINX_SITES_AVAILABLE / _CONF_NAME
    print(f"  Writing config to {dest} …")
    try:
        dest.write_text(config)
    except PermissionError:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False
        ) as tmp:
            tmp.write(config)
            tmp_path = tmp.name
        ok, _ = _run(_sudo(["cp", tmp_path, str(dest)]), capture=True)
        os.unlink(tmp_path)
        if not ok:
            print("  ✗ Failed to write NGINX config.")
            return False

    print("  ✓ Config written.")
    return True


def _enable_site() -> bool:
    """Create a symlink in sites-enabled for the m12labs config.

    Returns True on success (or if the symlink already exists).
    """
    dest = _NGINX_SITES_AVAILABLE / _CONF_NAME
    link = _NGINX_SITES_ENABLED / _CONF_NAME

    if link.exists() or link.is_symlink():
        print("  Site already enabled.")
        return True

    print(f"  Enabling site (symlink {link}) …")
    try:
        link.symlink_to(dest)
        return True
    except PermissionError:
        ok, _ = _run(_sudo(["ln", "-sf", str(dest), str(link)]), capture=True)
        if not ok:
            print("  ✗ Failed to enable NGINX site.")
            return False
        return True


def _test_nginx_config() -> bool:
    """Run ``nginx -t`` and show the full output on failure.

    Returns True when the test passes.
    """
    print("  Testing NGINX configuration …")
    ok, output = _run(_sudo(["nginx", "-t"]), capture=True)
    if not ok:
        print()
        print("  ✗ NGINX config test failed.  Full output:")
        print()
        for line in output.splitlines():
            print(f"    {line}")
        print()
        print("  Fix the config errors above before restarting NGINX.")
        return False
    print("  ✓ NGINX config test passed.")
    return True


def _restart_nginx() -> bool:
    """Prompt the user and restart nginx only on explicit confirmation.

    Returns True when nginx was restarted successfully, or when the user
    declined (no error in that case).
    """
    print()
    if not _confirm("Restart nginx now to apply the new configuration?"):
        print("  nginx not restarted.  Run  sudo systemctl restart nginx  when ready.")
        return True

    print("  Restarting nginx …")
    ok, _ = _run(_sudo(["systemctl", "restart", "nginx"]), capture=True)
    if not ok:
        print("  ✗ nginx restart failed.  Check  sudo systemctl status nginx.")
        return False

    print("  ✓ nginx restarted successfully.")
    return True


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def configure_nginx(install_path: Path) -> bool:
    """Full NGINX + SSL setup flow for the M12Labs panel.

    Order of operations
    -------------------
    1.  Prompt for and validate the domain name.
    2.  Show DNS/readiness checklist and ask for confirmation.
    3.  [1/6] Install / verify nginx.
    4.  [2/6] Install / verify certbot.
    5.  [3/6] Request SSL certificate via certbot (uses the existing nginx
              default config as the ACME challenge handler; the domain-specific
              panel config is written *after* the cert is issued).
    6.  [4/6] Write the domain-specific nginx config from panel.conf template.
    7.  [5/6] Enable the nginx site via symlink.
    8.  [6/6] Run ``nginx -t``; stop immediately and show full errors on failure.
    9.  Prompt user before restarting nginx.

    Returns True on success, False if any required step failed.
    """
    print()
    print("  NGINX Setup")
    print("  ─────────────────────────────")

    # -- 1. Domain input -------------------------------------------------------
    print()
    try:
        domain = input(
            "  Enter your domain name (e.g. panel.example.com): "
        ).strip().lower()
    except EOFError:
        domain = ""

    if not domain or "." not in domain:
        print("  No valid domain entered – NGINX setup cancelled.")
        return False

    # -- 2. DNS checklist + confirmation ----------------------------------------
    if not _show_dns_checklist(domain):
        print("  Setup cancelled – no changes were made.")
        return False

    # -- 3. Install / verify nginx ---------------------------------------------
    print()
    print("  [1/6] Checking nginx …")
    if not _ensure_nginx():
        return False

    # -- 4. Install / verify certbot -------------------------------------------
    print()
    print("  [2/6] Checking certbot …")
    if not _ensure_certbot():
        return False

    # -- 5. Request SSL certificate --------------------------------------------
    print()
    print("  [3/6] Obtaining SSL certificate …")
    if not _request_certificate(domain):
        return False

    # -- 6. Write nginx config -------------------------------------------------
    print()
    print("  [4/6] Writing NGINX config …")
    if not _write_nginx_config(install_path, domain):
        return False

    # -- 7. Enable site --------------------------------------------------------
    print()
    print("  [5/6] Enabling site …")
    if not _enable_site():
        return False

    # -- 8. Test config --------------------------------------------------------
    print()
    print("  [6/6] Testing config …")
    if not _test_nginx_config():
        return False

    # -- 9. Restart prompt -----------------------------------------------------
    ok = _restart_nginx()

    print()
    if ok:
        print(f"  ✓ NGINX setup complete for {domain}.")
    return ok
