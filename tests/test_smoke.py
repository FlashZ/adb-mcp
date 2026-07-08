"""Smoke tests that need NO device — they verify the package imports, every tool
registers, docstrings exist, and the serial/parsing helpers behave.

Run: pytest -q
"""

from __future__ import annotations

import asyncio

import pytest


def _tools():
    import adb_mcp.tools  # noqa: F401  (registers everything)
    from adb_mcp.core import mcp

    return asyncio.run(mcp.list_tools())


def test_all_tools_register():
    tools = _tools()
    names = {t.name for t in tools}
    # a representative slice across every module
    for expected in [
        "get_devices",
        "get_device_properties",
        "launch_package",
        "force_stop",
        "tap",
        "swipe",
        "text",
        "keyevent",
        "dump_ui",
        "find_elements",
        "tap_element",
        "logcat_start",
        "logcat_dump",
        "capture_screen",
        "record_screen_start",
        "list_files",
        "pull",
        "push",
        "read_file",
        "write_file",
        "reverse_port",
        "forward_port",
        "get_prop",
        "dumpsys",
        "run_shell",
    ]:
        assert expected in names, f"missing tool: {expected}"
    assert len(tools) >= 60, f"expected a broad surface, got {len(tools)}"


def test_every_tool_has_description():
    for t in _tools():
        assert t.description and t.description.strip(), f"{t.name} has no docstring"


def test_serial_resolution(monkeypatch):
    from adb_mcp import core

    monkeypatch.delenv("ADB_SERIAL", raising=False)
    core.set_runtime_serial(None)
    assert core.default_serial() is None

    monkeypatch.setenv("ADB_SERIAL", "127.0.0.1:58526")
    assert core.default_serial() == "127.0.0.1:58526"

    core.set_runtime_serial("RUNTIME123")  # runtime overrides env
    assert core.default_serial() == "RUNTIME123"
    core.set_runtime_serial(None)


def test_logcat_line_parser():
    from adb_mcp.tools.logs import _parse_line

    rec = _parse_line("06-28 17:45:01.123  8421  8421 I Unity   : FleetManager initialized")
    assert rec == {
        "time": "06-28 17:45:01.123",
        "pid": 8421,
        "tid": 8421,
        "level": "I",
        "tag": "Unity",
        "message": "FleetManager initialized",
    }
    assert _parse_line("--------- beginning of main") is None
    assert _parse_line("garbage") is None


def test_ui_bounds_parser():
    from adb_mcp.tools.ui import _parse_bounds

    b = _parse_bounds("[0,100][200,300]")
    assert b["center_x"] == 100 and b["center_y"] == 200
    assert b["width"] == 200 and b["height"] == 200
    assert _parse_bounds("nope") is None


def test_shell_allowed_flag(monkeypatch):
    from adb_mcp import core

    monkeypatch.delenv("ADB_MCP_ALLOW_SHELL", raising=False)
    assert core.shell_allowed() is False
    monkeypatch.setenv("ADB_MCP_ALLOW_SHELL", "1")
    assert core.shell_allowed() is True


def test_delete_refuses_protected_paths():
    from adb_mcp.tools.files import delete_file

    res = delete_file("/system")
    assert res["ok"] is False and "protected" in res["error"]


# --- security: device-side shell-injection resistance -----------------------


def test_quote_argv_neutralizes_metacharacters():
    import shlex

    from adb_mcp.core import quote_argv

    # A payload smuggled into a "scoped" arg must stay a single quoted token.
    cmd = quote_argv(["dumpsys", "battery", "; rm -rf /sdcard"])
    assert cmd == "dumpsys battery '; rm -rf /sdcard'"
    for payload in ["&& reboot", "| cat /etc/hosts", "$(id)", "`id`", "; wipe", "\n id"]:
        q = quote_argv(["echo", payload])
        assert q == "echo " + shlex.quote(payload)


def _capture_shell(monkeypatch):
    import adb_mcp.core as core

    seen = {}

    class _CP:
        stdout = ""
        stderr = ""

    def fake_run(args, serial=None, timeout=30.0, binary=False, check=False):
        seen["args"] = args
        return _CP()

    monkeypatch.setattr(core, "run", fake_run)
    return core, seen


def test_shell_list_mode_sends_single_quoted_command(monkeypatch):
    core, seen = _capture_shell(monkeypatch)
    core.shell(["echo", "; id"])
    # adb receives exactly: ["shell", "<one quoted command string>"]
    assert seen["args"][0] == "shell"
    assert len(seen["args"]) == 2
    assert seen["args"][1] == "echo '; id'"


def test_shell_string_mode_is_verbatim(monkeypatch):
    core, seen = _capture_shell(monkeypatch)
    # Deliberately-composed device shell lines (su -c, redirects) pass through.
    core.shell("su -c 'cat /data/x'")
    assert seen["args"][1] == "su -c 'cat /data/x'"


def test_run_shell_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ADB_MCP_ALLOW_SHELL", raising=False)
    from adb_mcp.tools.system import run_shell

    res = run_shell("id")
    assert res["ok"] is False and "disabled" in res["error"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
