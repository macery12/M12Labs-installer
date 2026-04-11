# M12Labs Panel Setup Module – Design Plan

> **Version:** v1  
> **Target:** Linux only (Ubuntu ≥ 23.x / Debian ≥ 11.x are the happy path)  
> **Self-contained:** `setup/` has no runtime imports from `installer/`; it
> only reuses patterns and ideas.

---

## High-level goal

The `setup/` module provides a **Linux-only, Python-driven interactive
walkthrough** that installs the M12Labs panel on a fresh server.  Instead of
copy-pasting commands from the docs, the user runs:

```bash
python3 -m setup.main
```

The installer executes every step from the M12Docs install pages in order.
The user still answers interactive prompts (artisan setup questions, admin
user creation) — the value-add is that they no longer need to type each
command manually.

---

## Directory structure

```text
setup/
  __init__.py
  installer_SETUP_PLAN.md      ← this file
  main.py                      # orchestrator / entrypoint
  config.py                    # install path + DB config (no persisted DB password)
  log.py                       # file-based logging (mirrors installer/log.py)
  system.py                    # system helpers (mirrors installer/build.py, no Node/pnpm)
  steps/
    __init__.py
    deps.py                    # Step 1 – system dependencies
    files.py                   # Step 2 – download panel files
    database.py                # Step 3 – DB + user creation
    laravel.py                 # Step 4 – env + artisan / migrations / admin user
    workers.py                 # Step 5 – cron + queue worker
  backup/
    __init__.py
    backup.py                  # optional – skeleton only in v1
```

---

## Mapping to M12Docs install pages

| Docs page                  | Implemented in        |
|----------------------------|-----------------------|
| `install-dependencies.md`  | `steps/deps.py`       |
| `download-files.md`        | `steps/files.py`      |
| `database-setup.md`        | `steps/database.py`   |
| `environment-setup.md`     | `steps/laravel.py`    |
| `queue-workers.md`         | `steps/workers.py`    |

---

## User preferences (non-negotiable constraints)

### 1. Default install path

- **Default:** `/var/www/m12labs`
- Created automatically if it does not exist; the installer prints what it is doing.
- User can override via interactive prompt or via `setup/config.toml`.

### 2. Release URL

The initial fixed release URL is:

```text
https://github.com/macery12/M12Labs/releases/download/v2.0.0-m12-rc2.6/panel.tar.gz
```

Stored as `DEFAULT_RELEASE_URL` in `steps/files.py`.  Update this constant
when a new version is released.

### 3. User / group

- Installed files are owned by `www-data:www-data`.
- `composer` and `php artisan` commands are run via `sudo -u www-data`.

### 4. NGINX configuration

NGINX is **not** configured by the installer in v1.  At the end of the run
the installer prints clear reminders:

- Configure NGINX to serve `<install_path>/public`.
- Set up SSL (Let's Encrypt recommended).

### 5. Backup support

Backup / restore under `setup/backup/` is **optional in v1**.  The
`backup.py` module contains skeleton stubs that raise `NotImplementedError`.

### 6. Flow

`python3 -m setup.main` runs a **single full install flow** (no menu).
Steps 4 (artisan) are interactive — the user answers prompts in the terminal.

---

## Security requirement: DB password handling

> **The database password must never be persisted to disk by the installer.**

Specifically:

- `config.py` / `InstallConfig` does **not** have a `db_pass` field.
- `save_config()` does **not** write any password field to `setup/config.toml`.
- `prompt_for_db_config()` returns `(InstallConfig, db_pass_str)` — the
  password is a plain `str` local variable in the caller.
- `main.py` passes `db_pass` directly to `setup_database()` and
  `configure_laravel()`, then immediately overwrites the variable with `""`.
- The password is written **once** into the panel's `.env` file by
  `steps/laravel.py` and nowhere else.
- The password is **never** logged (neither to console nor to file).

---

## Module responsibilities and signatures

### `setup/system.py`

System helpers (no Node/pnpm).

```python
def run_command(cmd: Sequence[str], cwd: Path | None = None) -> bool: ...
def run_command_no_cwd(cmd: Sequence[str]) -> bool: ...
def run_as_www_data(cmd: Sequence[str], cwd: Path | None = None) -> bool: ...
def get_package_manager() -> str | None: ...
def with_privilege(cmd: Sequence[str]) -> list[str] | None: ...
def install_packages(packages: Sequence[str]) -> bool: ...
```

### `setup/config.py`

```python
DEFAULT_INSTALL_PATH: Path   # /var/www/m12labs
DEFAULT_DB_NAME: str         # jexactyldb
DEFAULT_DB_USER: str         # jexactyluser

@dataclass
class InstallConfig:
    install_path: Path
    db_name: str
    db_user: str
    non_interactive: bool
    text_logs_enabled: bool
    # NOTE: db_pass is intentionally absent

def load_config() -> InstallConfig: ...
def save_config(cfg: InstallConfig) -> None: ...          # never writes db_pass
def generate_db_password(length: int = 24) -> str: ...    # returns in-memory string
def prompt_for_install_path(cfg: InstallConfig) -> InstallConfig: ...
def prompt_for_db_config(cfg: InstallConfig) -> tuple[InstallConfig, str]: ...
```

### `setup/log.py`

```python
LOG_DIR_NAME = "setup_logs"   # <install_path>/setup_logs/

def setup_logging(install_path: Path | None, text_logs_enabled: bool) -> logging.Logger: ...
def get_logger() -> logging.Logger: ...
```

### `setup/main.py`

```python
def full_install() -> int: ...   # returns 0 on success, 1 on failure
def main() -> int: ...
```

### `setup/steps/deps.py`

```python
def install_dependencies() -> bool: ...
```

Packages installed:
- Base: `software-properties-common curl apt-transport-https ca-certificates gnupg`
- PHP 8.3: `php8.3 php8.3-{common,cli,gd,mysql,mbstring,bcmath,xml,fpm,curl,zip}`
- System: `mariadb-server nginx tar unzip git redis-server cron`
- Composer: installed via `curl` if not already present

### `setup/steps/files.py`

```python
DEFAULT_RELEASE_URL: str   # https://github.com/…/v2.0.0-m12-rc2.6/panel.tar.gz

def download_panel(install_path: Path, release_url: str = DEFAULT_RELEASE_URL) -> bool: ...
```

### `setup/steps/database.py`

```python
def setup_database(db_name: str, db_user: str, db_pass: str) -> bool: ...
```

SQL is passed to `mysql` via **stdin** (not via `-e`), so the password never
appears in the process argument list.

### `setup/steps/laravel.py`

```python
def artisan(install_path: Path, *args: str) -> bool: ...
def configure_laravel(install_path: Path, db_name: str, db_user: str, db_pass: str) -> bool: ...
```

Artisan steps (in order):
1. `key:generate --force`
2. `p:environment:setup` ← interactive
3. `p:environment:database`
4. `migrate --seed --force`
5. `p:user:make` ← interactive

### `setup/steps/workers.py`

```python
def configure_workers(install_path: Path) -> bool: ...
```

Creates:
- www-data crontab entry: `* * * * * php <artisan> schedule:run >> /dev/null 2>&1`
- `/etc/systemd/system/jxctl.service` (runs `php artisan queue:work` as www-data)
- `systemctl daemon-reload && systemctl enable --now jxctl.service`

---

## Install flow (step order)

```
python3 -m setup.main
  │
  ├─ [guard]  ensure Linux
  ├─ [guard]  warn if not root / no sudo
  ├─ [prompt] install path
  ├─ [prompt] DB name, DB user, DB password  ← password in memory only
  ├─ [log]    setup_logging()
  │
  ├─ [1/5] install_dependencies()
  ├─ [2/5] download_panel()
  ├─ [3/5] setup_database()           ← password consumed here (.env write)
  ├─ [4/5] configure_laravel()        ← password consumed here, then cleared
  └─ [5/5] configure_workers()
       │
       └─ print final summary + NGINX/SSL reminders
```

---

## v1 scope

- ✅ Full install walkthrough (Steps 1–5)
- ✅ Interactive prompts for path, DB name/user/password
- ✅ DB password security (in-memory only, written to `.env` once)
- ✅ www-data ownership and `sudo -u www-data` for artisan/composer
- ✅ NGINX reminder at end
- ⬜ NGINX configuration (deferred to v2)
- ⬜ SSL setup (deferred to v2)
- ⬜ Backup / restore (skeleton only)
- ⬜ Non-interactive / CI mode (config flag reserved, not wired up)
