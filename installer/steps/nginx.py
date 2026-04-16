"""NGINX configuration helpers for the M12Labs panel installer."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from installer.system import install_packages, with_privilege

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


def _offer_dns01_fallback(domain: str) -> bool:
    """Offer manual ACME DNS-01 validation as a fallback when the nginx
    challenge method fails.

    Explains the Cloudflare TXT-record process in plain language, asks for
    explicit confirmation, then runs certbot in ``--manual`` mode.

    Returns True when a certificate is successfully issued, False otherwise.
    """
    print()
    print("  ─────────────────────────────────────────────────────────")
    print("  Alternative: Manual DNS-01 (Cloudflare TXT record) method")
    print("  ─────────────────────────────────────────────────────────")
    print()
    print("  Instead of proving domain ownership over HTTP, DNS-01 lets")
    print("  you prove it by adding a temporary TXT record to your DNS.")
    print("  This works even when port 80 is blocked or DNS hasn't")
    print("  propagated to this server's IP yet.")
    print()
    print("  How it works:")
    print()
    print("  1. certbot will display a TXT record name and value, e.g.:")
    print(f"       Name:   _acme-challenge.{domain}")
    print("       Value:  <a long random string from Let's Encrypt>")
    print()
    print("  2. You open your Cloudflare dashboard (dash.cloudflare.com),")
    print("     go to  DNS → Records  for your domain, and add:")
    print("       Type:  TXT")
    print(f"       Name:  _acme-challenge.{domain}")
    print("       Content: <paste the value certbot gave you>")
    print("       TTL:   Auto (or 60 seconds)")
    print()
    print("  3. Wait ~30–60 seconds for the record to propagate, then")
    print("     press Enter in this terminal to let certbot verify it.")
    print()
    print("  4. Once verified, certbot issues the certificate and the")
    print("     setup continues automatically.")
    print()
    print("  Note: you can delete the TXT record from Cloudflare after")
    print("  the certificate is issued — it is only needed during this step.")
    print()
    if not _confirm(
        f"Start manual DNS-01 certificate request for {domain}?"
    ):
        print("  Fallback cancelled – no certificate was issued.")
        return False

    print()
    print(f"  Running certbot manual DNS-01 for {domain}…")
    print("  Follow the on-screen instructions to add the TXT record.")
    print()
    cmd = _sudo([
        "certbot", "certonly",
        "--manual",
        "--preferred-challenges", "dns",
        "-d", domain,
    ])
    ok, _ = _run(cmd, capture=False)
    if not ok:
        print()
        print("  ✗ Manual DNS-01 certificate request failed.")
        print("    Check that the TXT record was added correctly and that")
        print("    DNS propagation had enough time before you pressed Enter.")
        return False

    print()
    print(f"  ✓ SSL certificate issued for {domain} via DNS-01.")
    return True


def _request_certificate(domain: str) -> bool:
    """Run certbot to obtain an SSL certificate for *domain*.

    Primary method: ``certonly --nginx`` – uses the already-installed nginx
    (and its default site config) as the ACME challenge handler, without
    permanently modifying any nginx config.  The domain-specific panel.conf
    is written separately after the cert is successfully issued.

    Fallback method: if the nginx challenge fails, the user is offered the
    manual ACME DNS-01 flow (:func:`_offer_dns01_fallback`).  This lets the
    certificate be issued even when port 80 is blocked or the domain's A
    record doesn't point to this server yet.

    Passes stdin/stdout/stderr through so certbot can interact with the user.
    Returns True on success.
    """
    print()
    print(f"  Requesting SSL certificate for {domain} via Let's Encrypt…")
    print()
    cmd = _sudo(["certbot", "certonly", "--nginx", "-d", domain])
    ok, _ = _run(cmd, capture=False)
    if ok:
        print()
        print(f"  ✓ SSL certificate issued for {domain}.")
        return True

    print()
    print("  ✗ certbot (nginx method) failed to obtain a certificate.")
    print("    Common causes:")
    print("    • DNS has not propagated to this server's IP yet.")
    print("    • Port 80 is blocked by a firewall or cloud security group.")
    print("    • The domain's A record does not point to this server.")
    return _offer_dns01_fallback(domain)


def _check_existing_config(install_path: Path, domain: str) -> str:
    """Inspect the existing NGINX panel config (if any) and compare it to
    the requested *domain* and *install_path*.

    Checks ``_NGINX_SITES_AVAILABLE / _CONF_NAME`` (and the corresponding
    sites-enabled symlink).

    Returns
    -------
    ``"none"``
        No existing config file was found.
    ``"match"``
        A config file exists and already references both *domain* and
        *install_path* – it looks like it was created for this installation.
    ``"conflict"``
        A config file exists but references a different domain or install
        path – overwriting without confirmation could break things.
    """
    dest = _NGINX_SITES_AVAILABLE / _CONF_NAME
    if not dest.exists():
        # Also check sites-enabled in case only the symlink exists
        link = _NGINX_SITES_ENABLED / _CONF_NAME
        if not link.exists():
            return "none"
        # Resolve the symlink to read the real file
        dest = link.resolve()

    try:
        content = dest.read_text()
    except OSError:
        # Unreadable config – treat as a conflict so we don't silently
        # overwrite something we couldn't inspect.
        return "conflict"

    domain_match = f"server_name {domain};" in content
    path_match = f"root {install_path}/public;" in content

    if domain_match and path_match:
        return "match"
    return "conflict"


def _write_nginx_config(install_path: Path, domain: str) -> bool:
    """Render panel.conf and write it to sites-available.

    Before writing, checks whether a config already exists and prompts the
    user for confirmation when appropriate:

    * **No existing config** → write directly.
    * **Existing config matches** this domain + install path → offer
      ``[r]euse / [w]rite new / [c]ancel``.  Choosing *reuse* skips
      the write (the existing file is left untouched) and returns True so
      the rest of the setup flow (symlink, nginx -t, restart) can continue.
    * **Existing config conflicts** (different domain or path) → show a
      warning and ask for explicit confirmation before overwriting.  Declining
      returns False.

    Returns True when the config is either successfully written or explicitly
    reused, False otherwise.
    """
    if not _CONF_TEMPLATE.exists():
        print(f"  ✗ Template not found: {_CONF_TEMPLATE}")
        return False

    if not _NGINX_SITES_AVAILABLE.is_dir():
        print(f"  ✗ Directory not found: {_NGINX_SITES_AVAILABLE}")
        print("  Is nginx installed correctly?")
        return False

    # -- Existing config detection -------------------------------------------
    status = _check_existing_config(install_path, domain)

    if status == "match":
        dest = _NGINX_SITES_AVAILABLE / _CONF_NAME
        print()
        print(f"  ⚠  An existing NGINX panel config was found at {dest}.")
        print(f"     It already references domain  {domain}  and")
        print(f"     install path  {install_path}.")
        print()
        print("     What would you like to do?")
        print("       [r] Reuse it  – keep the existing file, continue setup")
        print("       [w] Write new – overwrite it with a freshly rendered config")
        print("       [c] Cancel    – stop here, make no changes")
        print()
        try:
            choice = input("  Your choice [r/w/c]: ").strip().lower()
        except EOFError:
            choice = "c"

        if choice in ("c", ""):
            print("  Setup cancelled – existing config was not changed.")
            return False
        if choice == "r":
            print("  Reusing existing config – no file written.")
            return True
        # Any other input (including 'w') falls through to write below.

    elif status == "conflict":
        dest = _NGINX_SITES_AVAILABLE / _CONF_NAME
        print()
        print(f"  ⚠  WARNING: An existing NGINX panel config was found at {dest},")
        print("     but it references a different domain or install path.")
        print("     Overwriting it could break your current NGINX setup.")
        print()
        if not _confirm("Overwrite the existing config and continue?"):
            print("  Setup cancelled – existing config was not changed.")
            return False

    # -- Render and write the config -----------------------------------------
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
    5.  [3/6] Request SSL certificate via certbot.
              Primary:  ``certonly --nginx`` (HTTP-01 challenge).
              Fallback: if that fails, offer manual ACME DNS-01 via Cloudflare
              TXT record – the user is walked through the process and must
              confirm before the fallback is attempted.
    6.  [4/6] Write the domain-specific nginx config from panel.conf template.
              Before writing, checks whether a config already exists:
              same domain+path → reuse / write new / cancel;
              different domain or path → warn and require explicit confirmation.
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
