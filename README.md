# M12 Labs Installer

Linux‑only interactive installer for the [M12 Labs panel](https://github.com/macery12/M12Labs).

Handles the full lifecycle of a panel install: system dependencies, panel files, database setup, Laravel configuration, cron jobs, and workers.  Future releases will extend support to additional panels.

---

## Quick start

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-installer/main/setup.sh)
```

Non‑interactive (skip confirmation prompt):

```bash
curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-installer/main/setup.sh | sudo bash -s -- -y
```

---

## What `setup.sh` does

1. Verifies `git` and `python3` are available.
2. Clones or updates this repo under `/opt/m12labs-installer`.
3. Asks for confirmation before performing any privileged work.
4. Re‑executes itself with `sudo` if not already root.
5. Launches the interactive Python installer (`python3 -m installer.main`).

### Install steps

1. **System dependencies** – installs PHP 8.3, MariaDB, NGINX, Redis, Composer, and base tools.
2. **Panel files** – downloads the M12 Labs panel release from [`macery12/M12Labs`](https://github.com/macery12/M12Labs) and extracts it.
3. **Database** – creates the MySQL/MariaDB database and user.
4. **Laravel config** – writes `.env`, runs `composer install`, `key:generate`, migrations, seeds, and admin user creation.
5. **Cron + workers** – adds a `www-data` cron entry and installs a `jxctl.service` systemd worker.

> **Note:** `setup.sh` performs privileged operations (apt packages, system users, cron, systemd) and is intended for server‑style installs.

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
└── setup.sh            ← Bootstrap: clones repo and runs installer/main.py
```

---

## Future extensibility

The installer is structured to support additional panels in future releases.  New panel targets can be added as step modules under `installer/steps/` or as separate top‑level installer modules.
