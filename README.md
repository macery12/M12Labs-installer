# M12Labs Extensions (WIP)

This repo will eventually host multiple M12 Labs extensions.

For now it includes a small **Linux-only launcher** that helps work with a M12 Labs panel install (check files, run a build, etc.).

---

## Launcher (Linux)

### Install

Requirements: Linux, `python3`, `git`, `curl`.

```bash
curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-Extensions/main/install.sh | sh
```

This will:

- clone/update the repo under `~/.local/share/m12extensions`
- install a `m12extensions` command into `~/.local/bin`
- add that bin dir to your shell `PATH` for future terminals

After install, open a new terminal and run:

```bash
m12extensions
```

On first run the launcher will ask for your panel path (for example `/var/www/m12labs`) and remember it in `launcher/config.toml`.

### What the launcher does (current phase)

The menu is intentionally simple and mostly scaffolding:

- **Check**: read‑only validation that key panel files/dirs exist (Laravel backend + frontend layout).
- **Build only**: Linux‑only helper that ensures Node.js + pnpm are available, then runs `pnpm install` and `pnpm build` in the panel.

Other menu options (Install / Uninstall / Update) are placeholders for future real extension management.

### Uninstall

To remove the launcher using a script (similar to the installation process), run:

```bash
curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-Extensions/main/uninstall.sh | sh
```

This command will delete the launcher and all associated data from your home directory.

---
