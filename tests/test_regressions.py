"""Regression checks for failures that must not appear as successful device actions."""

from __future__ import annotations

import subprocess

import pytest


def test_missing_shell_exit_marker_is_an_error(monkeypatch):
    from adb_mcp import core

    monkeypatch.setattr(core, "shell", lambda *args, **kwargs: "error: device offline")
    with pytest.raises(core.AdbError, match="did not report an exit code"):
        core.shell_rc(["mkdir", "/sdcard/example"])


def test_shell_exit_code_and_output(monkeypatch):
    from adb_mcp import core

    monkeypatch.setattr(core, "shell", lambda *args, **kwargs: "permission denied\n__rc=1")
    assert core.shell_rc(["mkdir", "/data/example"]) == (1, "permission denied")


def test_adb_start_failure_is_shaped_as_adb_error(monkeypatch):
    from adb_mcp import core

    monkeypatch.setattr(core, "adb_bin", lambda: "missing-adb")

    def fail(*args, **kwargs):
        raise FileNotFoundError("missing-adb")

    monkeypatch.setattr(core.subprocess, "run", fail)
    with pytest.raises(core.AdbError, match="could not start adb"):
        core.run(["devices"])


@pytest.mark.parametrize("remote", ["/", "/system/..", "/data/../sdcard/", "system", "."])
def test_delete_refuses_protected_or_relative_paths(monkeypatch, remote):
    from adb_mcp.tools import files

    monkeypatch.setattr(files, "shell_rc", lambda *args, **kwargs: pytest.fail("rm was called"))
    assert files.delete_file(remote, recursive=True)["ok"] is False


def test_failed_pull_does_not_trust_stale_local_file(monkeypatch, tmp_path):
    from adb_mcp.tools import files

    local = tmp_path / "old.txt"
    local.write_text("old content")
    monkeypatch.setattr(
        files,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, "", "device offline"),
    )
    assert files.pull("/sdcard/new.txt", str(local))["status"] == "failed"


def test_root_write_stops_if_staging_push_fails(monkeypatch):
    from adb_mcp.tools import files

    monkeypatch.setattr(
        files,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, "", "device offline"),
    )
    monkeypatch.setattr(files, "shell_rc", lambda *args, **kwargs: pytest.fail("root copy was called"))
    result = files.write_file("/data/local/example.txt", "hello", as_root=True)
    assert result["ok"] is False
    assert "device offline" in result["error"]
