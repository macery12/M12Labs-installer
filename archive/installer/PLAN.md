# M12 Labs Installer - Plan

## Overall goal
Create a Linux-only M12 Labs extension installer in `/installer` with a clean,
runnable menu shell and room to grow as the real extension lifecycle is built
out in future phases.

This installer targets the M12 Labs panel project layout:
- `package.json` (frontend scripts; `pnpm build` → `vite build`)
- `composer.json`
- `artisan`
- `Containerfile`
- `resources/scripts/` (frontend source)
- `app/`, `config/`, `routes/`, `database/` (Laravel/PHP backend)

## Module structure
| File | Responsibility |
|------|---------------|
| `main.py` | Menu shell and user interaction only |
| `check.py` | Read-only validation against the install location |
| `build.py` | Build flow helpers (`pnpm install` + `pnpm build`) |
| `config.py` | Config read/write (TOML), install path prompt, `Config` dataclass |
| `install_path.py` | Legacy install-path helper (superseded by `config.py`) |

## Install path behavior
- On the very first run the user is prompted for the panel install path.
- The suggested example path is `/var/www/m12labs`.
- The answer is saved to `installer/config.toml` (TOML format, co-located with the installer files).
- Every subsequent run reloads the saved value without prompting again.
- No hardcoded fallback paths are used anywhere.

## Menu design
```
1. Install
2. Uninstall
3. Update
4. Check
5. Build only
6. Config
0. Exit
```

Current phase behavior:
- **Install** – paged placeholder catalog with page navigation
- **Uninstall** – installed-extension submenu placeholder
- **Update** – update-selection and confirmation placeholder
- **Check** – real read-only validation via `check.py`; concise or detailed output controlled by `show_detailed_checks` config flag
- **Build only** – `package.json` precheck → tool install if needed → `pnpm install` → `pnpm build`
- **Config** – options 2 (change install path), 3 (toggle detailed checks), 5 (build on update), 6 (build on uninstall)

## check.py design
The `Check` command is strictly read-only.  It only inspects the filesystem
and reports results.  It never installs, rebuilds, moves files, or writes
to the project tree.

Validated items (all under the saved install root):
- `package.json`
- `composer.json`
- `artisan`
- `resources/scripts/`
- `app/`
- `config/`
- `routes/`
- `database/`

Each item is reported as **PASS**, **WARN**, or **FAIL**.  Adding new items
requires only a new entry in `check.REQUIRED_ITEMS`.

## Future phases
- Add real extension state tracking
- Add real install/uninstall/update workflows
- Expand check into actionable diagnostics (tool availability, manifest validity, etc.)
- Add backup/rollback after core lifecycle is stable
- Add packaged binary distribution (PyInstaller) for end users

