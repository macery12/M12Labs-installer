# M12 Labs Installer

This repo hosts the **M12 Labs installer** — a Linux‑only, interactive panel installer for [M12 Labs](https://github.com/macery12/M12Labs).

It handles the full lifecycle of a panel install: system dependencies, panel files, database setup, Laravel configuration, cron jobs, and workers.  Future releases will extend support to additional panels.

---

## Overview

| Script / Directory | Purpose |
|--------------------|---------|
| `setup.sh` | Bootstrap: clones this repo under `/opt/m12labs-installer` and launches the interactive installer. |
| `install.sh` | Installs the `m12labs-installer` command into `$HOME` for repeated use. |
| `uninstall.sh` | Removes the `m12labs-installer` command and its local clone. |
| `installer/` | Active panel installer (Python, menu‑driven). |
| `archive/installer/` | Legacy TUI extension installer – kept for reference, not active. |

---

## Panel Install (`setup.sh`)

The primary way to install the M12 Labs panel on a fresh Linux server.

### Quick start

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-installer/main/setup.sh)
```

Non‑interactive (skip confirmation prompt):

```bash
curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-installer/main/setup.sh | sudo bash -s -- -y
```

### What `setup.sh` does

1. Verifies `git` and `python3` are available.
2. Clones or updates this repo under `/opt/m12labs-installer`.
3. Asks for confirmation before performing any privileged work.
4. Re‑executes itself with `sudo` if not already root.
5. Launches the interactive Python installer (`python3 -m installer.main`).

### What the Python installer does

1. **System dependencies** – installs PHP 8.3, MariaDB, NGINX, Redis, Composer, and base tools.
2. **Panel files** – downloads the M12 Labs panel release from [`macery12/M12Labs`](https://github.com/macery12/M12Labs) and extracts it.
3. **Database** – creates the MySQL/MariaDB database and user.
4. **Laravel config** – writes `.env`, runs `composer install`, `key:generate`, migrations, seeds, and admin user creation.
5. **Cron + workers** – adds a `www-data` cron entry and installs a `jxctl.service` systemd worker.

> **Note:** `setup.sh` performs privileged operations (apt packages, system users, cron, systemd) and is intended for server‑style installs.

---

## Install the CLI command (`install.sh`)

If you prefer to keep the `m12labs-installer` command handy in your home directory:

Requirements: Linux, `python3`, `git`, `curl`.

```bash
curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-installer/main/install.sh | sh
```

This will:

- clone/update this repo under `~/.local/share/m12labs-installer`
- install a `m12labs-installer` command into `~/.local/bin`
- add that directory to your shell `PATH` for future terminals

After install, open a new terminal and run:

```bash
m12labs-installer
```

### Uninstall the command

```bash
curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-installer/main/uninstall.sh | sh
```

This removes the command wrapper and the cloned repo from your home directory.  It does **not** touch your panel install.

---

## Repo structure

```
M12Labs-installer/
├── installer/          ← Active panel installer (Python, menu-driven)
│   ├── main.py         ← Entry point / interactive menu
│   ├── config.py       ← Config management (TOML)
│   ├── log.py          ← File logger
│   ├── system.py       ← Command execution and privilege helpers
│   ├── steps/          ← Install steps (deps, files, database, laravel, workers, nginx)
│   └── backup/         ← Backup helpers
├── archive/
│   └── installer/      ← Legacy TUI extension installer (archived, not active)
├── setup.sh            ← Panel install bootstrap (runs installer/main.py)
├── install.sh          ← Installs m12labs-installer CLI command
└── uninstall.sh        ← Removes m12labs-installer CLI command
```

---

## Future extensibility

The installer is designed around the M12 Labs panel but is structured to support additional panels in future releases.  New panel targets can be added as additional step modules under `installer/steps/` or as separate top‑level installer modules.
