"""
Tests for autostart.py and the Windows Downloads-registry resolver.

Platform-guarded: logic callable on any OS is tested everywhere; OS-specific
registration is only exercised on its native platform. No mocks — real calls,
real files (per python-prefs.md).
"""

import sys
from pathlib import Path

import pytest

import autostart
import config


def test_autostart_status_never_raises() -> None:
    """autostart_status() returns a well-formed dict on every OS."""
    status = autostart.autostart_status()
    assert isinstance(status, dict)
    assert set(status) >= {"installed", "method", "detail"}
    assert isinstance(status["installed"], bool)


def test_pythonw_swap_noop_when_absent(tmp_path: Path) -> None:
    """_pythonw_from_python returns input unchanged when pythonw.exe is absent."""
    fake = tmp_path / "python3"
    fake.write_text("")
    assert autostart._pythonw_from_python(str(fake)) == str(fake)


def test_pythonw_swap_prefers_pythonw(tmp_path: Path) -> None:
    """When pythonw.exe exists beside python, it is preferred."""
    (tmp_path / "python.exe").write_text("")
    (tmp_path / "pythonw.exe").write_text("")
    result = autostart._pythonw_from_python(str(tmp_path / "python.exe"))
    assert result.endswith("pythonw.exe")


def test_windows_task_xml_well_formed() -> None:
    """The generated Task Scheduler XML is parseable and declares UTF-16."""
    import xml.etree.ElementTree as ET

    xml = autostart._windows_task_xml(r"C:\py\pythonw.exe")
    assert 'encoding="UTF-16"' in xml
    assert "server.py" in xml
    assert r"C:\py\pythonw.exe" in xml
    # Strip declaration (ET rejects an explicit encoding in a str) and parse
    body = xml.split("?>", 1)[1]
    ET.fromstring(body)  # raises if malformed


def test_downloads_registry_returns_none_off_windows() -> None:
    """The Windows registry resolver is a safe no-op on non-Windows."""
    if sys.platform != "win32":
        assert config._windows_downloads_from_registry() is None


def test_resolve_downloads_folder_exists() -> None:
    """resolve_downloads_folder always returns an existing directory."""
    result = config.resolve_downloads_folder()
    assert isinstance(result, Path)
    assert result.is_dir()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only round-trip")
def test_windows_autostart_round_trip() -> None:
    """On Windows CI: install → status installed → uninstall → status gone."""
    autostart.uninstall_autostart()  # clean slate
    autostart.install_autostart()
    assert autostart.autostart_status()["installed"] is True
    autostart.uninstall_autostart()
    assert autostart.autostart_status()["installed"] is False
