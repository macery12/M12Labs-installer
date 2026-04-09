# Run and Packaging Notes (Linux)

## Development dependencies
- Linux environment
- Python 3.10+
- `sudo` access (recommended) for automatic dependency installation in build mode

## Run the launcher during development
From the repository root:

```bash
python3 launcher/main.py
```

The menu is interactive.  On the first run the launcher will prompt for the
panel install path (example: `/var/www/m12labs`) and save it for all future
runs.

## Install path management
- Saved to `~/.config/m12labs/install_path` as plain text.
- Prompted once on first run; reused silently on every subsequent run.
- No hardcoded fallback paths are used.

## Build-only behavior (menu option 5)
1. Verify Linux platform
2. Verify `package.json` exists at the saved install path (stops if missing)
3. Show a dependency setup notice when Node.js/pnpm need to be installed
4. Detect and install Node.js if missing (via system package manager)
5. Detect and install pnpm if missing (corepack → npm → system package manager)
6. Run `pnpm install`
7. Run `pnpm build`

The expected frontend build command from `package.json`:
- `pnpm build` → `vite build`

### Auto-install details (Linux)
- Node.js: `apt-get`, `dnf`, `yum`, `pacman`, `zypper`, or `apk` depending on distro.
- pnpm: tries `corepack` first, then `npm install -g pnpm@latest`, then system package manager.
- Uses `sudo` when available and not already root.

## Check behavior (menu option 4)
Strictly read-only.  Validates the saved install path without making any
changes to the system.  Reports **PASS**, **WARN**, or **FAIL** for:
- `package.json`
- `composer.json`
- `artisan`
- `resources/scripts/`
- `app/`
- `config/`
- `routes/`
- `database/`

## Project context references
The launcher expects the target panel to contain:
- `package.json`, `composer.json`, `artisan`, `Containerfile`
- `resources/scripts/`, `app/`, `config/`, `routes/`, `database/`

## End-user packaging direction (future)
Goal: distribute a self-contained launcher binary so end users do not need
Python installed.

Suggested approaches:
- `PyInstaller` one-file executable
- AppImage or distro package after behavior stabilizes

## Development vs end-user expectations
- Current phase: developers run Python source directly.
- Future phase: end users run a packaged binary artifact.

