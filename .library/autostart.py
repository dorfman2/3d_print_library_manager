"""
Cross-platform autostart management for the 3D Print Library server.

Registers (or removes) a boot/login startup entry so the Flask server launches
automatically. Uses launchd on macOS and Task Scheduler on Windows. All
OS-specific imports are lazy so this module imports cleanly on any platform.

CLI:
    python autostart.py install
    python autostart.py uninstall
    python autostart.py status
"""

import base64
import getpass
import logging
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

LIBRARY_DIR: Path = Path(__file__).resolve().parent
SERVER_PY: Path = LIBRARY_DIR / "server.py"

# Shared identifiers
MACOS_LABEL = "com.3dprint.library"
WINDOWS_TASK_NAME = "3DPrintLibrary"


def _pythonw_from_python(python_exe: str) -> str:
    """
    Return the windowless interpreter (pythonw.exe) beside the given python.

    On Windows, pythonw.exe runs without opening a console window. Falls back
    to the given executable if pythonw.exe is not found or off-Windows.

    Parameters
    ----------
    python_exe : str
        Path to a python executable.

    Returns
    -------
    str
        Path to pythonw.exe when present, else the input unchanged.
    """
    p = Path(python_exe)
    candidate = p.with_name("pythonw.exe")
    return str(candidate) if candidate.exists() else python_exe


# ─────────────────────────────────────────────────────────────────────────────
# macOS — launchd
# ─────────────────────────────────────────────────────────────────────────────

def _macos_plist_path() -> Path:
    """Return the per-user LaunchAgents plist path."""
    return Path.home() / "Library" / "LaunchAgents" / f"{MACOS_LABEL}.plist"


def _install_macos(python_exe: str) -> None:
    """
    Write and load a launchd LaunchAgent that runs the server at login.

    Parameters
    ----------
    python_exe : str
        Path to the python interpreter to launch the server with. For reliable
        Full Disk Access on macOS this should be a Developer-ID-signed
        interpreter (e.g. python.org), not Apple's CommandLineTools Python.
    """
    plist_path = _macos_plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": MACOS_LABEL,
        "ProgramArguments": [python_exe, "server.py"],
        "WorkingDirectory": str(LIBRARY_DIR),
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(LIBRARY_DIR / "server.out.log"),
        "StandardErrorPath": str(LIBRARY_DIR / "server.err.log"),
    }
    with open(plist_path, "wb") as fh:
        plistlib.dump(plist, fh)

    uid = subprocess.run(
        ["id", "-u"], capture_output=True, text=True, check=True
    ).stdout.strip()
    domain = f"gui/{uid}"
    # Idempotent: bootout any existing instance, then bootstrap.
    subprocess.run(
        ["launchctl", "bootout", f"{domain}/{MACOS_LABEL}"],
        capture_output=True,
    )
    subprocess.run(
        ["launchctl", "bootstrap", domain, str(plist_path)], check=True
    )
    logger.info("Installed launchd agent at %s", plist_path)
    logger.warning(
        "On macOS you must grant Full Disk Access to %s and then LOG OUT/IN "
        "for Downloads access to work under launchd.", python_exe
    )


def _uninstall_macos() -> None:
    """Unload and remove the launchd LaunchAgent."""
    plist_path = _macos_plist_path()
    uid = subprocess.run(
        ["id", "-u"], capture_output=True, text=True, check=True
    ).stdout.strip()
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}/{MACOS_LABEL}"],
        capture_output=True,
    )
    if plist_path.exists():
        plist_path.unlink()
    logger.info("Removed launchd agent %s", MACOS_LABEL)


def _status_macos() -> dict:
    """Return launchd autostart status."""
    plist_path = _macos_plist_path()
    installed = plist_path.exists()
    listed = subprocess.run(
        ["launchctl", "list"], capture_output=True, text=True
    ).stdout
    running = MACOS_LABEL in listed
    return {
        "installed": installed,
        "method": "launchd",
        "detail": f"plist={plist_path}, loaded={running}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Windows — Task Scheduler
# ─────────────────────────────────────────────────────────────────────────────

def _windows_task_xml(pythonw: str) -> str:
    """
    Build the Task Scheduler XML for an at-logon task.

    schtasks /xml requires true UTF-16; the caller writes it accordingly.
    Working directory is set so the server runs from .library even though its
    paths are __file__-based.

    Parameters
    ----------
    pythonw : str
        Path to pythonw.exe (windowless interpreter).

    Returns
    -------
    str
        The task definition XML (declaration states UTF-16).
    """
    user = f"{_win_domain()}\\{getpass.getuser()}"
    return (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.2" '
        'xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        "  <RegistrationInfo><Description>3D Print Library Manager server"
        "</Description></RegistrationInfo>\n"
        "  <Triggers><LogonTrigger><Enabled>true</Enabled>"
        f"<UserId>{user}</UserId></LogonTrigger></Triggers>\n"
        '  <Principals><Principal id="Author">'
        f"<UserId>{user}</UserId>"
        "<LogonType>InteractiveToken</LogonType>"
        "<RunLevel>LeastPrivilege</RunLevel></Principal></Principals>\n"
        "  <Settings>\n"
        "    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n"
        "    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n"
        "    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n"
        "    <AllowHardTerminate>true</AllowHardTerminate>\n"
        "    <StartWhenAvailable>true</StartWhenAvailable>\n"
        "    <Enabled>true</Enabled>\n"
        "    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>\n"
        "    <RestartOnFailure><Interval>PT1M</Interval><Count>3</Count>"
        "</RestartOnFailure>\n"
        "  </Settings>\n"
        '  <Actions Context="Author"><Exec>\n'
        f"    <Command>{pythonw}</Command>\n"
        "    <Arguments>server.py</Arguments>\n"
        f"    <WorkingDirectory>{LIBRARY_DIR}</WorkingDirectory>\n"
        "  </Exec></Actions>\n"
        "</Task>\n"
    )


def _win_domain() -> str:
    """Return the local machine/domain name for the task principal."""
    import os
    return os.environ.get("USERDOMAIN", os.environ.get("COMPUTERNAME", "."))


def _install_windows(python_exe: str) -> None:
    """
    Create a Task Scheduler task that runs the server at logon.

    Writes the task XML as true UTF-16 (schtasks /xml rejects UTF-8) and
    registers it with schtasks /create /f.
    """
    pythonw = _pythonw_from_python(python_exe)
    xml = _windows_task_xml(pythonw)
    tmp = Path(tempfile.gettempdir()) / "3dplib_task.xml"
    # UTF-16 LE with BOM — required by schtasks.
    tmp.write_text(xml, encoding="utf-16")
    subprocess.run(
        ["schtasks", "/create", "/tn", WINDOWS_TASK_NAME,
         "/xml", str(tmp), "/f"],
        check=True,
    )
    logger.info("Created Task Scheduler task %s", WINDOWS_TASK_NAME)


def _uninstall_windows() -> None:
    """Delete the Task Scheduler task."""
    subprocess.run(
        ["schtasks", "/delete", "/tn", WINDOWS_TASK_NAME, "/f"],
        capture_output=True,
    )
    logger.info("Deleted Task Scheduler task %s", WINDOWS_TASK_NAME)


def _status_windows() -> dict:
    """Return Task Scheduler autostart status."""
    result = subprocess.run(
        ["schtasks", "/query", "/tn", WINDOWS_TASK_NAME],
        capture_output=True, text=True,
    )
    installed = result.returncode == 0
    return {
        "installed": installed,
        "method": "Task Scheduler",
        "detail": result.stdout.strip() or result.stderr.strip(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def install_autostart(python_exe: Optional[str] = None) -> None:
    """
    Register the server to start at login for the current OS.

    Parameters
    ----------
    python_exe : Optional[str]
        Interpreter to launch the server with. Defaults to the current
        interpreter (sys.executable).

    Raises
    ------
    RuntimeError
        If the current OS is unsupported.
    """
    python_exe = python_exe or sys.executable
    if sys.platform == "darwin":
        _install_macos(python_exe)
    elif sys.platform == "win32":
        _install_windows(python_exe)
    else:
        raise RuntimeError(f"Autostart not supported on {sys.platform}")


def uninstall_autostart() -> None:
    """Remove the autostart entry for the current OS."""
    if sys.platform == "darwin":
        _uninstall_macos()
    elif sys.platform == "win32":
        _uninstall_windows()
    else:
        raise RuntimeError(f"Autostart not supported on {sys.platform}")


def autostart_status() -> dict:
    """
    Return autostart status for the current OS.

    Returns
    -------
    dict
        Keys: installed (bool), method (str), detail (str). Never raises.
    """
    try:
        if sys.platform == "darwin":
            return _status_macos()
        if sys.platform == "win32":
            return _status_windows()
    except Exception as exc:  # noqa: BLE001 - status must never raise
        return {"installed": False, "method": "unknown", "detail": str(exc)}
    return {
        "installed": False,
        "method": "unsupported",
        "detail": f"{sys.platform} not supported",
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _main(argv: list) -> int:
    """CLI entry point: install | uninstall | status."""
    if len(argv) != 2 or argv[1] not in {"install", "uninstall", "status"}:
        print("usage: python autostart.py {install|uninstall|status}")
        return 2
    action = argv[1]
    if action == "install":
        install_autostart()
        print(f"Autostart installed via {autostart_status()['method']}.")
    elif action == "uninstall":
        uninstall_autostart()
        print("Autostart removed.")
    else:
        status = autostart_status()
        print(f"installed={status['installed']} method={status['method']}")
        print(status["detail"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
