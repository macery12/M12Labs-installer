# M12 Labs Linux Extension Manager - Initial Plan

## Overall goal
Create a Linux-first extension manager launcher scaffold in `/launcher` with a runnable menu shell and future-ready structure.

## Menu design
Main menu:
1. Install
2. Uninstall
3. Update
4. Check
5. Build only

Current phase behavior:
- Install: paged mod list and placeholder selection flow
- Uninstall: tracked-state submenu placeholder
- Update: tracked-state submenu placeholder
- Check: validation/self-test placeholder
- Build only: dependency checks + `pnpm install` + `pnpm build`

## Future installer lifecycle
Planned lifecycle for each extension:
1. Discovery and selection
2. Validation checks
3. Install/update/uninstall execution
4. Post-action verification
5. State persistence and reporting

This first phase only delivers menu shell and starter build path.

## Project structure plan
- `launcher/main.py`: single-file starter app
- `launcher/PLAN.md`: planning and roadmap notes
- `launcher/RUN_AND_PACKAGE.md`: Linux-focused run/build/package guidance

## Linux-only support notes
- Template is intentionally Linux-first.
- Launcher checks platform at runtime.
- Windows/macOS support is out of scope for this phase.

## Future phases
- Add real extension state tracking
- Add real install/uninstall/update workflows
- Expand checks into actionable diagnostics
- Add packaged binary distribution flow so end users do not need local Python
