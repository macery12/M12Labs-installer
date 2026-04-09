# M12 Labs Linux Extension Manager - Initial Plan

## Overall goal
Create a Linux-only extension manager launcher scaffold in `/launcher` with a runnable menu shell and future-ready structure.

This launcher is designed around the target panel project context:
- `package.json` (frontend scripts, including `pnpm build` -> `vite build`)
- `composer.json`
- `artisan`
- `Containerfile`
- `resources/scripts/` (frontend source area)
- `app/`, `config/`, `routes/`, `database/` (Laravel/PHP backend areas)

## Menu design
Main menu:
1. Install
2. Uninstall
3. Update
4. Check
5. Build only

Current phase behavior:
- Install: paged extension list and placeholder page navigation flow
- Uninstall: installed-extension submenu placeholder (tracked state comes later)
- Update: update-selection and confirmation placeholder
- Check: non-destructive validation/self-test placeholder
- Build only: starter build path (`package.json` precheck -> tool checks/install -> `pnpm install` -> `pnpm build`)

## Future installer lifecycle
Planned lifecycle for each extension:
1. Discovery and selection
2. Validation checks
3. Install/update/uninstall execution
4. Post-action verification
5. State persistence and reporting

This first phase only delivers menu shell and starter build path.

## Project structure plan
- `launcher/main.py`: minimal menu/input launcher shell
- `launcher/build.py`: refactored build-only helper logic
- `launcher/PLAN.md`: planning and roadmap notes
- `launcher/RUN_AND_PACKAGE.md`: Linux-focused run/build/package guidance

## Linux-only support notes
- Template is intentionally Linux-first.
- Launcher checks platform at runtime.
- Windows/macOS support is out of scope for this phase.

## Planned check/validation direction
The future `Check` mode is intended to remain non-destructive and eventually verify:
- `package.json`
- `composer.json`
- `artisan`
- installed tool availability (Node.js, pnpm, etc.)
- extension tracking state integrity
- manifest validity
- file existence/readability for required panel paths

## Future phases
- Add real extension state tracking
- Add real install/uninstall/update workflows
- Expand checks into actionable diagnostics
- Add backup/rollback only after core lifecycle behavior is stable
- Add override support in a dedicated later phase
- Add runtime plugin loading in a dedicated later phase
- Add packaged binary distribution flow so end users do not need local Python
