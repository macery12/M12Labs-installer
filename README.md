# M12 Labs Installer (WIP)

This repo hosts the **M12 Labs installer** — a Linux-only tool for managing M12 Labs extensions on a panel install (check files, run a build, etc.).

---

## Installer (Linux)

### Install

Requirements: Linux, `python3`, `git`, `curl`.

```bash
curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-installer/main/install.sh | sh
```

This will:

- clone/update the repo under `~/.local/share/m12labs-installer`
- install a `m12labs-installer` command into `~/.local/bin`
- add that bin dir to your shell `PATH` for future terminals

After install, open a new terminal and run:

```bash
m12labs-installer
```

On first run the installer will ask for your panel path (for example `/var/www/m12labs`) and remember it in `installer/config.toml`.

### What the installer does (current phase)

The menu is intentionally simple and mostly scaffolding:

- **Check**: read‑only validation that key panel files/dirs exist (Laravel backend + frontend layout).
- **Build only**: Linux‑only helper that ensures Node.js + pnpm are available, then runs `pnpm install` and `pnpm build` in the panel.

Other menu options (Install / Uninstall / Update) are placeholders for future real extension management.

### Uninstall

To remove the installer using a script (similar to the installation process), run:

```bash
curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-installer/main/uninstall.sh | sh
```

This command will delete the installer and all associated data from your home directory.

---
