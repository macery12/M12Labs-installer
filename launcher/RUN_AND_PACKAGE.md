# Run and Packaging Notes (Linux)

## Development dependencies
- Linux environment
- Python 3.10+ (for development of the launcher template)
- `sudo` access (recommended) for automatic dependency installation in build mode

## Run the launcher during development
From repository root:

```bash
python3 launcher/main.py
```

The menu is interactive and includes placeholder management flows plus a starter build path.

## Build-only behavior in current template
Menu option `5. Build only` does:
1. Verify Linux platform
2. Verify `node` is installed (auto-installs if missing)
3. Verify `pnpm` is installed (auto-installs if missing)
4. Run `pnpm install`
5. Run `pnpm build`

It currently expects `package.json` at repository root.

### Auto-install details (Linux)
- Node.js install fallback uses detected system package manager (`apt-get`, `dnf`, `yum`, `pacman`, `zypper`, `apk`).
- pnpm install attempts:
  1. `corepack` (`corepack enable` + `corepack prepare pnpm@latest --activate`)
  2. `npm install -g pnpm@latest`
  3. system package manager fallback (`pnpm` package)
- If root access is required, launcher uses `sudo` when available.

## End-user packaging direction (future)
Goal: distribute a self-contained launcher binary so end users do not need Python installed.

Suggested future approaches:
- `PyInstaller` one-file executable build
- Alternative Linux packaging (AppImage, distro package) after launcher behavior stabilizes

## Development vs end-user expectations
- Current phase: developers run Python source directly.
- Future phase: end users should run packaged launcher artifacts without Python setup.
