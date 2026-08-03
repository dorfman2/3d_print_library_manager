# Tasks — Windows Support

## Task 1: Fix Open/Reveal on Windows (the known bug)
- [ ] In `server.py` reveal endpoint: drop `check=True` for the Windows `explorer`
      call (explorer returns exit code 1 even on success)
- [ ] Use `f"/select,{file_path}"` as a single argument, not `"/select,"` + path
- [ ] In `server.py` open endpoint: use `os.startfile(str(file_path))` on Windows
      instead of `cmd /c start` (no console flash, no shell quoting issues)
- [ ] Reference `os.startfile` inside the Windows branch only (it is Windows-only)
- [ ] Keep macOS (`open` / `open -R`) and Linux (`xdg-open`) branches unchanged
- [ ] Verify: reveal endpoint returns HTTP 200 on Windows when the file exists

## Task 2: Robust Downloads folder resolution
- [ ] Add `_windows_downloads_from_registry()` to `config.py` (lazy `winreg` import)
- [ ] Read Known Folders GUID `{374DE290-123F-4565-9164-39C4925E467B}` from
      `HKCU\...\Explorer\Shell Folders`, expand env vars
- [ ] Update `resolve_downloads_folder()`: registry → `~/Downloads` → home fallback
- [ ] Guard all registry access so `config.py` imports cleanly on macOS/Linux
- [ ] Verify: returns a valid dir on every OS; returns None gracefully off-Windows

## Task 3: Cross-platform autostart module
- [ ] Create `.library/autostart.py` with `install_autostart()`,
      `uninstall_autostart()`, `autostart_status()`
- [ ] Implement `_pythonw_from_python()` — swap python.exe → pythonw.exe when present
- [ ] Windows: `_install_windows_taskscheduler()` using `schtasks /create /sc onlogon`
- [ ] Windows: `_install_windows_registry()` fallback using `winreg` Run key
- [ ] Windows: uninstall removes both the task and the registry value if present
- [ ] macOS: write + `launchctl bootstrap` the plist (idempotent bootout-then-bootstrap)
- [ ] All OS-specific imports are lazy/guarded — module imports on any platform
- [ ] Verify: install is idempotent; uninstall fully removes the entry

## Task 4: Autostart CLI entry point
- [ ] Add a small CLI: `python autostart.py install` / `uninstall` / `status`
- [ ] Resolve python_exe, server.py, and workdir automatically from the module path
- [ ] Print clear success/failure and the method used (Task Scheduler / registry / launchd)
- [ ] Verify: CLI round-trips install → status → uninstall on the host OS

## Task 5: Tests
- [ ] Create `tests/test_paths.py` — MAX_PATH truncation, casefold dedup, spaces in
      paths (all callable on any OS)
- [ ] Create `tests/test_autostart.py` — status never raises; pythonw swap logic;
      registry helper returns None off-Windows; on Windows CI do a real
      install/status/uninstall round-trip with a throwaway task name
- [ ] Ensure existing 46 tests still pass unchanged
- [ ] Verify: full suite green locally (macOS)

## Task 6: Windows CI
- [ ] Create `.github/workflows/test.yml` running pytest on a matrix of
      ubuntu-latest, macos-latest, windows-latest (Python 3.11)
- [ ] Install from `.library/requirements.txt`, run `.library/tests/`
- [ ] Verify: workflow file is valid YAML; jobs defined for all three OSes

## Task 7: Documentation
- [ ] README: add "Windows Install" section (Python, pip, run server)
- [ ] README: add "Start on Boot (Windows)" — autostart.py install + manual
      Task Scheduler steps as fallback
- [ ] Document `pythonw.exe` and how to find the interpreter path (`where python`)
- [ ] Note the macOS launchd path for parity
- [ ] Update tech-context steering with Windows autostart + CI notes

## Task 8: Real-machine verification checklist (manual, documented)
- [ ] Document a Windows smoke-test checklist in the spec folder:
      server starts, setup wizard loads, scan works, thumbnails render,
      Open launches slicer, Reveal highlights in Explorer, sync moves files,
      autostart survives a reboot
- [ ] Note: this task is a manual checklist for when a Windows machine is available;
      code tasks 1–7 do not depend on it
