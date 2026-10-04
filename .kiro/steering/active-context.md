---
inclusion: always
---

# Active Context - Current Task State

## Current Focus
3D Print Library v2 COMPLETE — unified app with Viewer + Sorter merged. Deployed and auto-starting on BOTH macOS (launchd) and Windows (Task Scheduler).

## Recent Changes
- All unified-library spec tasks completed
- config.py: shared config module (load/save, resolve paths)
- categories.py: 8-step name cleanup + keyword categorization + load/save
- sorter.py: 5-phase sync pipeline (ZIP, index, categorize, move, clean)
- server.py: extended with sync API, scheduler, config/categories endpoints, setup wizard
- sync.html + sync.js: sync control panel + category editor
- setup.html: first-run wizard (starter / existing / blank modes)
- Edge-case hardening: EC-1 through EC-28 implemented
- README updated with combined-app usage

## Upcoming Changes
- Implement the windows-support spec in code (Explorer reveal-bug fix, autostart.py, Windows CI) so the manual Windows setup becomes reproducible
- First real-user test of the unified app (ingest + browse)
- Potential v3 features: interactive 3D viewer, bulk tag editor, AI auto-tagging
- Dark mode toggle
- Keyboard navigation

## Windows Machine (Generic_PC, 192.168.1.153)
- Remote access: OpenSSH Server enabled; key auth via `~/.ssh/id_ed25519_winpc`
  (public key in both user and administrators authorized_keys). Known-hosts at
  `~/.ssh/winpc_known_hosts`. SSH login name is `dorfman2@buffalo.edu` (Azure AD),
  which maps to local account `generic_pc\dorfm` (SID
  S-1-5-21-553164822-2743434241-1808763967-1001).
- Connect (from this Mac, non-interactive): `ssh -i ~/.ssh/id_ed25519_winpc
  -o UserKnownHostsFile=~/.ssh/winpc_known_hosts -l "dorfman2@buffalo.edu" 192.168.1.153 <cmd>`
- IMPORTANT zsh gotcha: do NOT put ssh options in a variable (zsh won't word-split);
  pass them inline on the ssh line.
- Repo location: `C:\Users\dorfm\3d_print_library_manager` (`.library` subfolder for the app).
- Python: real interpreter `C:\Users\dorfm\AppData\Local\Python\pythoncore-3.14-64\python.exe`
  (3.14.4), pythonw.exe beside it. Flask 3.1.3 installed. Avoid the Microsoft Store
  stub at `...\WindowsApps\python.exe`.
- Server resolves all paths via `__file__` (DB_PATH, CONFIG_PATH, CATEGORIES_PATH all
  absolute) — cwd-independent.
- Autostart: Task Scheduler task `\3DPrintLibrary`, trigger At logon, runs
  `pythonw.exe server.py` from `.library` (headless), restart-on-failure 3x/1min.
  Task XML built locally, shipped as base64, written as true UTF-16 (schtasks /xml
  rejects UTF-8), registered with `schtasks /create /xml`.
- Removed the OLD standalone `3DPrintSync` app (separate 3d-print-library repo):
  deleted its HKCU Run value, Uninstall\3D Print Sync_is1 key, and
  AppData\Local\3DPrintSync folder (its uninstaller had left all three behind).
- Server binds 127.0.0.1:5050 (local-only on the box; not reachable from the Mac).

## Active Decisions and Considerations
- v2 is complete and functional — focus shifts to real-world usage feedback
- STL thumbnails will render progressively as user browses (first-time only, then cached)
- 265 of 688 files already have thumbnails from 3MF extraction — instant on first load
- Sync scheduler uses shared lock with scanner — non-reentrant, prevents collisions
