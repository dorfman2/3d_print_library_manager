# Requirements — Windows Support

## Purpose

The app was built and verified on macOS. It has Windows code branches (open/reveal,
path resolution, MAX_PATH handling) that were written but **never executed on
Windows**. This spec ensures the app runs correctly and installs cleanly on Windows,
with feature parity to macOS.

## Background — current Windows state

| Area | Status |
|------|--------|
| Open file | `cmd /c start "" <path>` branch exists, unverified |
| Reveal file | `explorer /select,<path>` branch exists — **has a known bug** (see FR-2) |
| Downloads folder | `Path.home() / "Downloads"` — works, but ignores relocated folders |
| MAX_PATH (260) | truncation logic exists in sorter, unverified |
| Boot on startup | **macOS launchd only — no Windows equivalent** |
| CI / tests on Windows | **none — tests only ran on macOS** |
| Console window | not suppressed (pythonw not used) |

## Functional Requirements

### FR-1: Verified cross-platform file paths
- MUST handle Windows paths (backslashes, drive letters, spaces) throughout
- MUST handle the 260-character MAX_PATH limit in the sorter (verify existing logic)
- MUST treat the filesystem as case-insensitive for dedup (already uses casefold)
- MUST serve raw files and thumbnails correctly regardless of path separator

### FR-2: Fix and verify Open/Reveal on Windows
- MUST fix the `explorer /select,` call: `explorer.exe` returns exit code 1 even on
  success, so `check=True` wrongly reports failure (HTTP 500). Do not use `check=True`
  for explorer; treat non-zero as success for the reveal path.
- MUST verify "Open" launches the OS default app (slicer) on Windows
- MUST verify "Reveal" highlights the file in File Explorer on Windows
- MUST safely handle paths with spaces and special characters (no shell injection)

### FR-3: Robust Downloads folder resolution
- SHOULD resolve the real Windows Downloads folder even if relocated, by reading the
  Known Folders registry value
  (`HKCU\...\Shell Folders\{374DE290-123F-4565-9164-39C4925E467B}`)
- MUST fall back to `~/Downloads` then home directory if the registry lookup fails
- MUST NOT crash if the registry key is missing

### FR-4: Start on boot (Windows)
- MUST provide a documented, working autostart mechanism for Windows
- MUST run without a visible console window (use `pythonw.exe`)
- MUST offer two options:
  1. **Task Scheduler** (recommended) — a task triggered "At log on"
  2. **Registry Run key** —
     `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
- MUST provide a helper script to install AND uninstall the autostart entry
- MUST document the manual steps as a fallback

### FR-5: Cross-platform startup helper
- SHOULD provide a single entry point that abstracts "install autostart" per OS
  (launchd on macOS, Task Scheduler / registry on Windows)
- MUST be idempotent (re-running does not create duplicates)
- MUST support a clean uninstall

### FR-6: Windows CI
- MUST add a GitHub Actions workflow running the pytest suite on `windows-latest`
- MUST run the same 46 tests that pass on macOS
- MUST pass on both `ubuntu-latest`/`macos-latest` and `windows-latest`

## Non-Functional Requirements

### NFR-1: No new runtime dependencies
- Windows autostart uses stdlib (`winreg`, `subprocess` with `schtasks`) — no pip deps
- Registry access guarded so imports never fail on macOS

### NFR-2: Testing
- Windows-specific helpers MUST have tests that run on Windows CI
- Path/registry logic MUST degrade gracefully and be testable on any OS
- Real-filesystem tests, no mocks (per python-prefs.md)

### NFR-3: Documentation
- README MUST have a Windows install + autostart section
- MUST document `pythonw.exe` usage and how to find the Python path

## Out of Scope
- A packaged `.exe` installer (Inno Setup / PyInstaller) — separate future effort
- A Windows system-tray GUI — the web UI covers all controls
- Windows service (as opposed to per-user autostart) — not needed for a local tool

## Reference
- Existing macOS launchd agent: `~/Library/LaunchAgents/com.3dprint.library.plist`
- #[[file:.library/server.py]]
- #[[file:.library/config.py]]
- #[[file:.library/sorter.py]]
