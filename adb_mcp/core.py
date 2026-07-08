"""Shared plumbing for adb-mcp: adb discovery, invocation, serial handling,
error shaping, and the single FastMCP instance every tool module registers onto.

Design principles (from the project brief):
  * Idempotent, structured-output tools — never bare terminal text.
  * NO unrestricted `adb shell <anything>` tool by default. A scoped, opt-in
    `run_shell` exists only when ADB_MCP_ALLOW_SHELL=1.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP

# The one FastMCP instance. Tool modules do `from adb_mcp.core import mcp`.
mcp = FastMCP("adb-mcp")

# Avoid a flashing console window per adb call on Windows.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Runtime-settable default device (set_default_device), overrides ADB_SERIAL.
_runtime_serial: str | None = None


# --------------------------------------------------------------------------- #
# adb binary discovery
# --------------------------------------------------------------------------- #


def _candidates() -> list[str]:
    env = os.environ
    paths = [
        env.get("ADB_PATH", ""),
        os.path.join(env.get("ANDROID_HOME", ""), "platform-tools", "adb.exe"),
        os.path.join(env.get("ANDROID_SDK_ROOT", ""), "platform-tools", "adb.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
        os.path.expandvars(r"%USERPROFILE%\scoop\apps\adb\current\adb.exe"),
        os.path.expandvars(r"%USERPROFILE%\AppData\Local\Android\Sdk\platform-tools\adb.exe"),
        "/usr/local/bin/adb",
        "/usr/bin/adb",
        os.path.expanduser("~/Android/Sdk/platform-tools/adb"),
        os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
    ]
    return [p for p in paths if p]


@functools.lru_cache(maxsize=1)
def adb_bin() -> str:
    """Resolve the adb executable, caching the result. Raises AdbError if absent."""
    for c in _candidates():
        if os.path.isfile(c):
            return c
    found = shutil.which("adb")
    if found:
        return found
    raise AdbError(
        "adb executable not found. Set ADB_PATH (or ANDROID_HOME) to your SDK, or add platform-tools to PATH."
    )


# --------------------------------------------------------------------------- #
# errors + result shaping
# --------------------------------------------------------------------------- #


class AdbError(RuntimeError):
    """Raised for adb invocation problems; surfaced to the agent as a tool error."""


def ok(**fields: Any) -> dict[str, Any]:
    """Build a successful structured result, always with ok=True."""
    return {"ok": True, **fields}


def err(message: str, **fields: Any) -> dict[str, Any]:
    """Build a structured error result (does not raise)."""
    return {"ok": False, "error": message, **fields}


# --------------------------------------------------------------------------- #
# serial resolution
# --------------------------------------------------------------------------- #


def default_serial() -> str | None:
    if _runtime_serial:
        return _runtime_serial
    s = os.environ.get("ADB_SERIAL", "").strip()
    return s or None


def set_runtime_serial(serial: str | None) -> None:
    global _runtime_serial
    _runtime_serial = serial or None


# --------------------------------------------------------------------------- #
# invocation
# --------------------------------------------------------------------------- #


def run(
    args: list[str],
    serial: str | None = None,
    timeout: float = 30.0,
    binary: bool = False,
    check: bool = False,
) -> subprocess.CompletedProcess:
    """Run `adb [-s serial] <args>`.

    Returns a CompletedProcess (str output unless binary=True). If check=True,
    raises AdbError on a non-zero exit."""
    cmd = [adb_bin()]
    ser = serial if serial is not None else default_serial()
    if ser:
        cmd += ["-s", ser]
    cmd += args
    try:
        cp = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            text=not binary,
            creationflags=_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as e:
        raise AdbError(f"adb timed out after {timeout}s: {' '.join(args)}") from e
    if check and cp.returncode != 0:
        msg = (cp.stderr if not binary else b"").strip() if not binary else ""
        raise AdbError(f"adb {' '.join(args)} failed (rc={cp.returncode}): {msg}")
    return cp


def shell(shell_args: list[str] | str, serial: str | None = None, timeout: float = 30.0) -> str:
    """Run `adb shell <args>` and return combined stdout+stderr, stripped.

    Pass a list for normal args, or a single string when you need device-side
    shell quoting (e.g. "su -c 'cat /x'")."""
    args = ["shell"] + (shell_args if isinstance(shell_args, list) else [shell_args])
    cp = run(args, serial=serial, timeout=timeout)
    return ((cp.stdout or "") + (cp.stderr or "")).strip()


def shell_rc(
    shell_args: list[str] | str, serial: str | None = None, timeout: float = 30.0
) -> tuple[int, str]:
    """Like shell() but also returns the device-side exit code via `; echo $?`."""
    base = shell_args if isinstance(shell_args, str) else " ".join(shell_args)
    out = shell(f"{base}; echo __rc=$?", serial=serial, timeout=timeout)
    rc = 0
    if "__rc=" in out:
        out, _, tail = out.rpartition("__rc=")
        try:
            rc = int(tail.strip().split()[0])
        except (ValueError, IndexError):
            rc = 0
    return rc, out.strip()


def tool(*d_args, **d_kwargs) -> Callable:
    """Thin passthrough to mcp.tool() so modules can `from ..core import tool`."""
    return mcp.tool(*d_args, **d_kwargs)


def shell_allowed() -> bool:
    return os.environ.get("ADB_MCP_ALLOW_SHELL", "").strip() in ("1", "true", "yes")
