# Design — Windows Support

## Overview

Make the existing cross-platform code actually work on Windows: fix the known
Explorer bug, harden Downloads resolution, add a Windows autostart mechanism
parallel to the macOS launchd agent, and add Windows CI so regressions are caught.

## New / Changed Files

```
.library/
├── server.py          CHANGE: fix reveal (explorer exit-code quirk)
├── config.py          CHANGE: registry-based Downloads resolution + fallback
├── autostart.py       NEW: cross-platform install/uninstall of boot startup
└── tests/
    ├── test_autostart.py   NEW: platform-guarded autostart tests
    └── test_paths.py       NEW: path + MAX_PATH + case-fold tests
.github/workflows/
└── test.yml           NEW: pytest on windows-latest + macos-latest
```

## FR-2: Reveal fix (the real bug)

`explorer.exe /select,<path>` returns **exit code 1 even on success**. The current
code uses `subprocess.run(..., check=True)`, which raises `CalledProcessError` and
returns HTTP 500 despite the window opening correctly.

```python
# server.py — reveal endpoint (Windows branch)
elif system == "Windows":
    # explorer returns 1 even on success — do NOT use check=True
    subprocess.run(["explorer", f"/select,{file_path}"])
    # treat as success regardless of exit code
```

Also switch the Open branch away from `cmd /c start` to the cleaner
`os.startfile()` (Windows-only stdlib), which avoids a console flash and shell
quoting issues:

```python
if system == "Windows":
    os.startfile(str(file_path))          # open in default app
```

`os.startfile` only exists on Windows, so import/reference it inside the branch.

## FR-3: Downloads resolution via Known Folders

```python
# config.py
def resolve_downloads_folder() -> Path:
    if sys.platform == "win32":
        path = _windows_downloads_from_registry()
        if path and path.is_dir():
            return path
    downloads = Path.home() / "Downloads"
    if downloads.is_dir():
        return downloads
    return Path.home()

def _windows_downloads_from_registry() -> Optional[Path]:
    """Read the real Downloads path from the Known Folders registry value."""
    try:
        import winreg
        key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
        guid = "{374DE290-123F-4565-9164-39C4925E467B}"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            val, _ = winreg.QueryValueEx(k, guid)
        # Expand %USERPROFILE% etc.
        return Path(os.path.expandvars(val))
    except (ImportError, OSError, FileNotFoundError):
        return None
```

`winreg` is imported lazily inside the function so `config.py` imports fine on macOS.

## FR-4 / FR-5: autostart.py

A single module with an OS-dispatched API:

```python
def install_autostart(python_exe: str, server_py: str, workdir: str) -> None:
    """Register the server to start at login for the current OS."""

def uninstall_autostart() -> None:
    """Remove the autostart entry for the current OS."""

def autostart_status() -> dict:
    """Return {installed: bool, method: str, detail: str}."""
```

### Windows — Task Scheduler (preferred)

Use `schtasks` via subprocess (no admin needed for per-user tasks):

```python
TASK_NAME = "3DPrintLibrary"

def _install_windows_taskscheduler(pythonw, server_py, workdir):
    # /sc onlogon = at logon; /rl limited = no elevation
    cmd = [
        "schtasks", "/create", "/tn", TASK_NAME,
        "/tr", f'"{pythonw}" "{server_py}"',
        "/sc", "onlogon", "/rl", "limited", "/f",
    ]
    subprocess.run(cmd, check=True, cwd=workdir)
```

Prefer `pythonw.exe` (resolved from the given `python_exe` by swapping the
filename) so no console window appears.

### Windows — Registry Run key (fallback)

```python
def _install_windows_registry(pythonw, server_py):
    import winreg
    key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    value = f'"{pythonw}" "{server_py}"'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0,
                        winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, "3DPrintLibrary", 0, winreg.REG_SZ, value)
```

Registry approach launches from the value's implied cwd; the server resolves the
library folder from `config.json`, so cwd independence matters — verify server.py
resolves paths absolutely (it does, via config).

### macOS — launchd (already exists, formalize it)

`autostart.py` on macOS writes the same plist we created manually and loads it via
`launchctl bootstrap`. Idempotent: bootout-then-bootstrap.

### pythonw resolution

```python
def _pythonw_from_python(python_exe: str) -> str:
    p = Path(python_exe)
    candidate = p.with_name("pythonw.exe")
    return str(candidate) if candidate.exists() else python_exe
```

## FR-6: GitHub Actions — test.yml

```yaml
name: tests
on: [push, pull_request]
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r .library/requirements.txt
      - run: python -m pytest .library/tests/ -v
```

## Testing Strategy

### test_paths.py (runs on all OSes)
- MAX_PATH truncation produces a valid path under the limit (force-test the logic
  regardless of host OS by calling the helper directly)
- casefold dedup matches `Widget` vs `widget`
- raw-file serving handles a path with spaces

### test_autostart.py (platform-guarded)
- `autostart_status()` returns a dict on every OS without raising
- On Windows CI: install → status shows installed → uninstall → status shows removed
  (uses a throwaway task name; real schtasks/registry on the CI runner)
- On macOS: skip schtasks tests; verify plist path construction is correct
- `_pythonw_from_python` swaps the filename correctly
- `_windows_downloads_from_registry` returns None gracefully on non-Windows

## Rollout

1. Fix reveal + open (server.py) — the one real bug
2. Harden Downloads resolution (config.py)
3. Add autostart.py + tests
4. Add Windows CI workflow
5. Update README with Windows install + autostart
6. (Manual) verify on a real Windows machine: open, reveal, sync, autostart
