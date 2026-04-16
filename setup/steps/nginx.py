"""NGINX configuration helpers for the M12Labs panel installer."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_CONF_TEMPLATE = Path(__file__).resolve().parent.parent / "panel.conf"
_NGINX_SITES_AVAILABLE = Path("/etc/nginx/sites-available")
_NGINX_SITES_ENABLED = Path("/etc/nginx/sites-enabled")
_CONF_NAME = "m12labs"


def _run(cmd: list[str]) -> bool:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Command failed: {' '.join(cmd)}")
        if result.stderr:
            for line in result.stderr.splitlines()[:10]:
                print(f"    {line}")
    return result.returncode == 0


def configure_nginx(install_path: Path) -> bool:
    """Write an NGINX server block for the panel and enable it.

    Steps:
    1. Prompt for domain name.
    2. Generate /etc/nginx/sites-available/m12labs from panel.conf template.
    3. Symlink into sites-enabled.
    4. Test and reload NGINX.

    Returns True on success, False if any step failed.
    """
    # -- domain prompt ---------------------------------------------------------
    print()
    print("  NGINX Setup")
    print("  ─────────────────────────────")
    print()
    print("  This will create an NGINX server block for the M12Labs panel.")
    print("  You will need a domain name pointing to this server.")
    print()
    try:
        domain = input("  Enter your domain name (e.g. panel.example.com): ").strip()
    except EOFError:
        domain = ""

    if not domain:
        print("  No domain entered – NGINX setup cancelled.")
        return False

    # -- sanity checks ---------------------------------------------------------
    if not shutil.which("nginx"):
        print("  nginx is not installed or not in PATH.")
        print("  Run 'Install' first to install dependencies (includes nginx).")
        return False

    if not _CONF_TEMPLATE.exists():
        print(f"  Template file not found: {_CONF_TEMPLATE}")
        return False

    if not _NGINX_SITES_AVAILABLE.is_dir():
        print(f"  Directory not found: {_NGINX_SITES_AVAILABLE}")
        print("  Is nginx installed correctly?")
        return False

    # -- write config ----------------------------------------------------------
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
        # try with sudo
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False
        ) as tmp:
            tmp.write(config)
            tmp_path = tmp.name
        if not _run(["sudo", "cp", tmp_path, str(dest)]):
            os.unlink(tmp_path)
            print("  ✗ Failed to write NGINX config.")
            return False
        os.unlink(tmp_path)

    # -- symlink ---------------------------------------------------------------
    link = _NGINX_SITES_ENABLED / _CONF_NAME
    if not link.exists():
        print(f"  Enabling site (symlink {link}) …")
        try:
            link.symlink_to(dest)
        except PermissionError:
            if not _run(["sudo", "ln", "-sf", str(dest), str(link)]):
                print("  ✗ Failed to enable NGINX site.")
                return False

    # -- nginx -t + reload -----------------------------------------------------
    print("  Testing NGINX configuration …")
    if not _run(["sudo", "nginx", "-t"]):
        print("  ✗ NGINX config test failed – please check the config above.")
        return False

    print("  Reloading NGINX …")
    if not _run(["sudo", "systemctl", "reload", "nginx"]):
        print("  ✗ NGINX reload failed.")
        return False

    print()
    print(f"  ✓ NGINX configured successfully for {domain}.")
    print()
    print("  Next steps:")
    print("  1. Set up SSL (Let's Encrypt recommended):")
    print("       sudo apt-get install certbot python3-certbot-nginx")
    print(f"       sudo certbot --nginx -d {domain}")
    print()
    return True
