# M12Labs Panel Setup Module – Plan (superseded)

> **Note:** This file is the original draft.  The authoritative plan and full
> implementation now live in `setup/installer_SETUP_PLAN.md` (lowercase `setup/`).

---

Goal: In the M12Labs **panel** project, create a new `setup/` folder that provides a Linux-only, Python-driven installer for the panel. This setup code should *follow the same architectural style* as this repo’s existing installer modules, but live in a separate `setup/` namespace that we can later copy or vendor into the panel repo.

This repo (`M12Labs-installer`) is the design sandbox and reference for how the setup code should look.

---

## High-level behavior

The new `setup/` module (to be used in the panel project) should:

- Automate the manual install steps currently documented in `M12Docs/docs/panel/installation`:
  1. Install system dependencies
  2. Download/extract panel release
  3. Create MySQL/MariaDB database and user
  4. Configure Laravel environment (`.env`, composer, migrations, admin user)
  5. Configure cron job + systemd queue worker
- Target Linux only (Ubuntu ≥ 23.x, Debian ≥ 11.x being the “happy path”).
- Run via a single command like:

  ```bash
  python3 -m setup.main
  ```

  and optionally through a `setup.sh` shell bootstrap.

This **must be isolated** in a `setup/` folder (no coupling to existing extension installer logic besides reusing patterns/ideas).

---

## Target structure (in the PANEL repo)

We intend the panel repo to eventually contain:

```text
setup/
  __init__.py
  main.py         # entrypoint and orchestration
  config.py       # install path, DB config, non-interactive flags
  log.py          # text log setup (similar to installer/log.py)
  system.py       # shell helpers (similar to installer/build.py)
  steps/
    __init__.py
    deps.py       # Step 1 – system dependencies
    files.py      # Step 2 – download panel files
    database.py   # Step 3 – DB + user creation
    laravel.py    # Step 4 – env + artisan + migrations
    workers.py    # Step 5 – cron + queue worker
  backup/
    __init__.py
    backup.py     # optional backup/restore helpers for the panel tree
```

This repo (`M12Labs-installer`) should contain working versions of these modules (in a mirrored layout), so they can be copied or adapted into the panel repo later.

---

## Mapping to existing docs

Use the M12Docs pages as the source of truth for commands and flow:

- `install-dependencies.md` → `steps/deps.py`
- `download-files.md` → `steps/files.py`
- `database-setup.md` → `steps/database.py`
- `environment-setup.md` → `steps/laravel.py`
- `queue-workers.md` → `steps/workers.py`

For now, hardcode the current release URL:

```text
https://github.com/macery12/M12Labs/releases/download/v2.0.0-m12-rc1/panel.tar.gz
```

Make it easy to change later (single constant).

---

## Detailed module requirements

### 1. `system.py` (copied/adapted from installer/build.py)

Responsibilities:

- Run external commands with nice logging:
  - `run_command(cmd: Sequence[str], cwd: Path | None = None) -> bool`
  - `run_command_no_cwd(cmd: Sequence[str]) -> bool`
- Detect package manager:
  - `get_package_manager() -> str | None`
- Prepare privileged commands:
  - `with_privilege(cmd: Sequence[str]) -> list[str] | None`
- Install packages:
  - `install_packages(pkgs: Sequence[str]) -> bool`

This should be essentially the same as `installer/build.py`’s package-manager logic, but without the Node/pnpm specific bits.

### 2. `config.py`

Responsibilities:

- Define a `Config` dataclass with at minimum:
  - `install_path: Path | None`  (default `/var/www/m12labs`)
  - `db_name: str | None`        (default `jexactyldb`)
  - `db_user: str | None`        (default `jexactyluser`)
  - `db_pass: str | None`        (optional; can be generated)
  - `non_interactive: bool`      (default `False`)
- Read/write a TOML config stored next to the setup code (e.g. `setup/config.toml`) using `tomllib` (like `installer/config.py`).
- Provide:
  - `load_config() -> Config`
  - `save_config(cfg: Config) -> None`
  - `prompt_for_install_path(cfg: Config) -> Config`
  - `prompt_for_db_config(cfg: Config) -> Config`

Behavior is similar to the existing `installer/config.py`, but focused on install path + DB settings.

### 3. `log.py`

Responsibilities:

- Provide `setup_logging(install_path: Path | None, enabled: bool) -> logging.Logger`:
  - When enabled and `install_path` is set, create `<install_path>/setup_logs/`.
  - Write logs to `setup_logs/logs-YYYY-MM-DD_HH-MM-SS.txt`.
  - Same pattern as `installer/log.py` (no console logging here; use `print()` for user-facing output).
- Provide `get_logger() -> logging.Logger`.

### 4. Step modules in `steps/`

#### `steps/deps.py` – system dependencies

Implement:

```python
def install_dependencies() -> bool: ...
```

Translate `install-dependencies.md`:

- `apt -y install software-properties-common curl apt-transport-https ca-certificates gnupg`
- `LC_ALL=C.UTF-8 add-apt-repository -y ppa:ondrej/php`
- `apt update`
- `apt -y install php8.3 php8.3-{common,cli,gd,mysql,mbstring,bcmath,xml,fpm,curl,zip} mariadb-server nginx tar unzip git redis-server cron`
- Install Composer via curl if `composer` is missing.

Use `system.install_packages` and `system.run_command_no_cwd` for commands.

#### `steps/files.py` – download panel

Implement:

```python
def download_panel(install_path: Path, release_url: str) -> bool: ...
```

Translate `download-files.md`:

- Create directory (`mkdir /var/www/m12labs`)
- `curl -Lo panel.tar.gz <release_url>`
- `tar -xzvf panel.tar.gz`
- `chmod -R 755 storage/* bootstrap/cache/`
- `chown -R www-data:www-data /var/www/m12labs/*`

Make `install_path` and `release_url` parameters (no hard-coded paths inside).

#### `steps/database.py` – DB setup

Implement:

```python
def setup_database(db_name: str, db_user: str, db_pass: str) -> bool: ...
```

Translate `database-setup.md`:

- Use root MySQL/MariaDB connection and run:

  ```sql
  CREATE USER 'jexactyluser'@'127.0.0.1' IDENTIFIED BY 'randomPassword';
  CREATE DATABASE jexactyldb;
  GRANT ALL PRIVILEGES ON jexactyldb.* TO 'jexactyluser'@'127.0.0.1' WITH GRANT OPTION;
  FLUSH PRIVILEGES;
  ```

With safety:

- Use `CREATE DATABASE IF NOT EXISTS` and `CREATE USER IF NOT EXISTS`.
- Connect via `mysql -u root -e "<SQL>"`.

#### `steps/laravel.py` – Laravel env + migrations

Implement:

```python
def configure_laravel(install_path: Path, db_name: str, db_user: str, db_pass: str) -> bool: ...
```

Translate `environment-setup.md`:

1. `cp -R .env.example .env` (if `.env` doesn’t exist).
2. Patch `.env` with `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`.
3. `composer install --no-dev --optimize-autoloader` (run as `www-data` if possible).
4. `php artisan key:generate --force`
5. `php artisan p:environment:setup`
6. `php artisan p:environment:database`
7. `php artisan migrate --seed --force`
8. `php artisan p:user:make`
9. Reset permissions as in docs.

Provide a small helper inside this module to run artisan commands as `www-data`:

```python
def artisan(install_path: Path, *args: str) -> bool: ...
```

#### `steps/workers.py` – cron + queue worker

Implement:

```python
def configure_workers(install_path: Path) -> bool: ...
```

Translate `queue-workers.md`:

- Install `cron` if missing.
- Append to crontab (if not already present):

  ```text
  * * * * * php /var/www/m12labs/artisan schedule:run >> /dev/null 2>&1
  ```

- Create `/etc/systemd/system/jxctl.service` containing the provided unit.
- `systemctl daemon-reload && systemctl enable --now jxctl.service`.

---

### 5. `main.py` orchestration

Create an `InstallOptions` dataclass:

```python
@dataclass
class InstallOptions:
    install_path: Path
    db_name: str
    db_user: str
    db_pass: str
    non_interactive: bool = False
```

Implement:

```python
def full_install(cfg: Config, opts: InstallOptions | None = None) -> None:
    # 1. Ensure Linux + root/sudo
    # 2. Load config, prompt for missing install_path / DB fields (unless non_interactive)
    # 3. Call steps.deps.install_dependencies()
    # 4. steps.database.setup_database(...)
    # 5. steps.files.download_panel(...)
    # 6. steps.laravel.configure_laravel(...)
    # 7. steps.workers.configure_workers(...)
    # 8. Print clear summary (install path, DB credentials, next steps)
```

For now, `main.py` can be a simple script that just runs `full_install(...)` straight away (no menu required), but it should be easy to extend later with a menu similar to `installer/main.py`.

---

### 6. Shell bootstrap (in panel repo)

Assume the panel repo will add:

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "M12Labs Panel Setup"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required. Please install Python 3.10+ and re-run."
  exit 1
fi

python3 -m setup.main
```

---

## Implementation guidance for agent

- Use this repo’s existing modules (`installer/build.py`, `installer/config.py`, `installer/log.py`, `installer/backup.py`) as style and structure references.
- Keep all new setup-related code under a `setup/` namespace (and/or a dedicated branch) so it can later be copied into the panel repo.
- Ensure code is Linux-only, with graceful error messages for unsupported platforms.
- Prioritize clear, step-based console messages (e.g., `[1/5] Installing dependencies…`, `[2/5] Setting up database…`, etc.).