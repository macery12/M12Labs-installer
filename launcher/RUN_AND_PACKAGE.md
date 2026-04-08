# Run and Packaging Notes (Linux)

## Development dependencies
- Linux environment
- Python 3.10+ (for development of the launcher template)
- Node.js
- pnpm

## Run the launcher during development
From repository root:

```bash
python3 launcher/main.py
```

The menu is interactive and includes placeholder management flows plus a starter build path.

## Build-only behavior in current template
Menu option `5. Build only` does:
1. Verify `node` is installed
2. Verify `pnpm` is installed
3. Run `pnpm install`
4. Run `pnpm build`

It currently expects `package.json` at repository root.

## End-user packaging direction (future)
Goal: distribute a self-contained launcher binary so end users do not need Python installed.

Suggested future approaches:
- `PyInstaller` one-file executable build
- Alternative Linux packaging (AppImage, distro package) after launcher behavior stabilizes

## Development vs end-user expectations
- Current phase: developers run Python source directly.
- Future phase: end users should run packaged launcher artifacts without Python setup.
