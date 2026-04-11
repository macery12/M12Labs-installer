# M12 Labs Installer (WIP)

This repo hosts the **M12 Labs installer** — a Linux‑only tool for managing M12 Labs extensions on a panel install (check files, run a build, etc.).

It also includes a separate **panel setup script** (`setup.sh`) that performs a full interactive install of the main M12 Labs panel from the [`macery12/M12Labs`](https://github.com/macery12/M12Labs) repository.

---

## Overview of scripts

There are two main flows in this repo:

1. **Installer for extensions (this repo)**
   - `install.sh` – installs or updates the *M12 Labs installer* itself as a `m12labs-installer` command in your `$HOME`.
   - `uninstall.sh` – completely removes the `m12labs-installer` command and its clone under `$HOME`.

2. **Panel setup (separate panel repo)**
   - `setup.sh` – root‑level bootstrap script that directly installs and configures the **M12 Labs panel** under `/opt/m12labs-installer` and then runs the interactive Python setup (`python3 -m setup.main`).

Use **`install.sh`/`uninstall.sh`** when you want the **extension installer CLI** (`m12labs-installer`) in your home directory.

Use **`setup.sh`** when you want to **install the panel itself** from `macery12/M12Labs` on a Linux server (including system dependencies, database, Laravel config, cron + workers, etc.).

---

## 1. M12 Labs Installer (extensions, CLI in `$HOME`)

### Install the installer

Requirements: Linux, `python3`, `git`, `curl`.

```bash
curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-installer/main/install.sh | sh
```

This will:

- clone/update this repo under `~/.local/share/m12labs-installer`
- install a `m12labs-installer` command into `~/.local/bin`
- add that bin dir to your shell `PATH` for future terminals

After install, open a new terminal and run:

```bash
m12labs-installer
```

On first run the installer will ask for your **panel path** (for example `/var/www/m12labs`) and remember it in `installer/config.toml`.

### What the installer does (current phase)

The menu is intentionally simple and mostly scaffolding:

- **Check**: read‑only validation that key panel files/dirs exist (Laravel backend + frontend layout).
- **Build only**: Linux‑only helper that ensures Node.js + pnpm are available, then runs `pnpm install` and `pnpm build` in the panel.

Other menu options (Install / Uninstall / Update) are placeholders for future real extension management.

### Uninstall the installer

To remove the installer using a script (similar to the installation process), run:

```bash
curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-installer/main/uninstall.sh | sh
```

This command will delete the installer command and the cloned installer repository from your home directory (it does **not** touch your panel install).

---

## 2. M12 Labs Panel Setup (`setup.sh` for macery12/M12Labs)

The `setup.sh` script in this repo is a **bootstrap for installing the main M12 Labs panel** itself (from [`macery12/M12Labs`](https://github.com/macery12/M12Labs)), not just the extension installer.

### What `setup.sh` does

When you run `setup.sh` it will:

1. Verify required tools (`git`, `python3`) are available.
2. Clone or update the `macery12/M12Labs-installer` repo under `/opt/m12labs-installer`.
3. Ask for confirmation before doing any privileged work.
4. Re‑execute itself with `sudo` if not already root.
5. Launch the interactive Python installer:

   ```bash
   python3 -m setup.main
   ```

The Python installer (`setup/main.py`) then:

1. Verifies the platform is Linux.
2. Loads or creates `setup/config.toml` with defaults.
3. Prompts for:
   - panel install path (e.g. `/var/www/m12labs`)
   - database name
   - database user
   - database password (kept in memory only; written once into the panel’s `.env`).
4. Runs the five setup steps:

   1. **System dependencies** (`setup/steps/deps.py`)
      - Installs base tools, PHP 8.3, MariaDB, NGINX, Redis, Composer, etc.
   2. **Panel files** (`setup/steps/files.py`)
      - Downloads the M12 Labs panel release from `macery12/M12Labs` and extracts it into your chosen install path.
   3. **Database** (`setup/steps/database.py`)
      - Creates the MySQL/MariaDB database and user.
   4. **Laravel config** (`setup/steps/laravel.py`)
      - Writes DB settings to `.env`, runs `composer install`, artisan `key:generate`, migrations + seeds, and admin user creation.
   5. **Cron + workers** (`setup/steps/workers.py`)
      - Adds a `www-data` cron entry for `php artisan schedule:run` and installs/enables a `jxctl.service` systemd worker.

5. Prints a final summary with NGINX and SSL reminders.

### How to run `setup.sh` (panel install)

Recommended interactive usage:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-installer/main/setup.sh)
```

This will:

- prompt you for confirmation,
- re‑exec as `sudo` when needed,
- then run the full interactive panel installer.

Non‑interactive / automated (skip confirmation prompt):

```bash
curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-installer/main/setup.sh | sudo bash -s -- -y
```

> **Note:** `setup.sh` is intended for **server‑style panel installs** (e.g. `/var/www/m12labs`) and will perform privileged operations such as installing apt packages, creating system users, configuring cron, and writing systemd units.

---

## Summary

- Use **`install.sh` / `uninstall.sh`** for the **M12 Labs installer CLI** (`m12labs-installer`) that manages checks and builds for M12 Labs extensions on an existing panel.
- Use **`setup.sh`** for a **full panel installation** of M12 Labs itself (code, database, Laravel config, cron, workers) from the `macery12/M12Labs` repository.
