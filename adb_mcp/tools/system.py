"""System tools: props, settings, memory/cpu, processes, dumpsys, and an
opt-in scoped shell (disabled unless ADB_MCP_ALLOW_SHELL=1)."""

from __future__ import annotations

import re
from typing import Any

from ..core import err, ok, shell, shell_allowed, shell_rc, tool


@tool()
def get_prop(name: str | None = None, serial: str | None = None) -> Any:
    """Read a single system property by name, or ALL props as a dict when name is
    omitted (parses `getprop`)."""
    if name:
        return ok(name=name, value=shell(["getprop", name], serial))
    out = shell(["getprop"], serial)
    props: dict[str, str] = {}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("[") and "]: [" in line:
            k, _, v = line.partition("]: [")
            props[k[1:]] = v.rstrip("]")
    return props


@tool()
def set_prop(name: str, value: str, serial: str | None = None) -> dict[str, Any]:
    """Set a system property (`setprop`). Many props are read-only or need root."""
    out = shell(["setprop", name, value], serial)
    return ok(name=name, value=value, message=out) if not out else err(out, name=name)


@tool()
def get_setting(namespace: str, key: str, serial: str | None = None) -> dict[str, Any]:
    """Read an Android setting. namespace = 'system' | 'secure' | 'global'."""
    out = shell(["settings", "get", namespace, key], serial)
    return ok(namespace=namespace, key=key, value=out.strip())


@tool()
def put_setting(namespace: str, key: str, value: str, serial: str | None = None) -> dict[str, Any]:
    """Write an Android setting. namespace = 'system' | 'secure' | 'global'."""
    out = shell(["settings", "put", namespace, key, value], serial)
    return ok(namespace=namespace, key=key, value=value, message=out)


@tool()
def list_processes(filter: str | None = None, serial: str | None = None) -> list[dict[str, Any]]:
    """List running processes (`ps -A`): [{pid, ppid, name, user}]. filter = name substring."""
    out = shell(["ps", "-A", "-o", "PID,PPID,USER,NAME"], serial)
    procs = []
    for line in out.splitlines()[1:]:
        cols = line.split(None, 3)
        if len(cols) < 4 or not cols[0].isdigit():
            continue
        procs.append(
            {
                "pid": int(cols[0]),
                "ppid": int(cols[1]) if cols[1].isdigit() else None,
                "user": cols[2],
                "name": cols[3],
            }
        )
    if filter:
        f = filter.lower()
        procs = [p for p in procs if f in p["name"].lower()]
    return procs


@tool()
def get_meminfo(package: str | None = None, serial: str | None = None) -> dict[str, Any]:
    """Return memory info. With a package: that app's total PSS (kB); otherwise the
    global summary (Total/Free/Used/Lost RAM). Returns parsed fields + raw text."""
    args = ["dumpsys", "meminfo"] + ([package] if package else [])
    out = shell(args, serial, timeout=30)

    def first_int(s: str) -> int | None:
        # Match the first number, allowing thousands commas and a K/M/kB suffix
        # (e.g. "11,356,016K" -> 11356016).
        m = re.search(r"([\d,]+)\s*(?:kB|KB|K|M)?\b", s)
        return int(m.group(1).replace(",", "")) if m and m.group(1).strip(",") else None

    if package:
        total = None
        for line in out.splitlines():
            s = line.strip()
            if s.startswith("TOTAL PSS:") or (s.startswith("TOTAL") and "kB" in s):
                total = first_int(s)
                break
        return ok(package=package, total_pss_kb=total, raw=out[:4000])

    # Global summary: "Total RAM: 11,880,404 kB", "Free RAM:", "Used RAM:", "Lost RAM:"
    ram: dict[str, int | None] = {}
    for line in out.splitlines():
        s = line.strip()
        for label, key in (
            ("Total RAM:", "total_ram_kb"),
            ("Free RAM:", "free_ram_kb"),
            ("Used RAM:", "used_ram_kb"),
            ("Lost RAM:", "lost_ram_kb"),
        ):
            if s.startswith(label):
                ram[key] = first_int(s)
    return ok(package=None, **ram, raw=out[:4000])


@tool()
def get_top(count: int = 10, serial: str | None = None) -> dict[str, Any]:
    """Return a one-shot `top` snapshot of the top `count` processes by CPU (raw text)."""
    out = shell(["top", "-b", "-n", "1", "-m", str(count)], serial, timeout=20)
    return ok(count=count, raw=out[:6000])


@tool()
def get_uptime(serial: str | None = None) -> dict[str, Any]:
    """Return device uptime (seconds + human string) from /proc/uptime and `uptime`."""
    up = shell(["cat", "/proc/uptime"], serial)
    seconds = None
    if up and up.split():
        try:
            seconds = float(up.split()[0])
        except ValueError:
            pass
    return ok(uptime_seconds=seconds, human=shell(["uptime"], serial))


@tool()
def dumpsys(
    service: str, args: list[str] | None = None, max_chars: int = 8000, serial: str | None = None
) -> dict[str, Any]:
    """Run `dumpsys <service>` for a NAMED service (e.g. 'battery', 'wifi',
    'activity', 'meminfo', 'connectivity') and return the raw text (capped).
    Scoped to a service name — not an arbitrary shell."""
    if not service or "/" in service or ";" in service or " " in service:
        return err("invalid service name")
    out = shell(["dumpsys", service, *(args or [])], serial, timeout=45)
    return ok(service=service, truncated=len(out) > max_chars, raw=out[:max_chars])


@tool()
def list_services(serial: str | None = None) -> list[str]:
    """List all dumpsys service names available on the device."""
    out = shell(["dumpsys", "-l"], serial, timeout=20)
    return sorted(ln.strip() for ln in out.splitlines() if ln.strip() and not ln.startswith("Currently"))


@tool()
def run_shell(command: str, serial: str | None = None, timeout: float = 30.0) -> dict[str, Any]:
    """Run an arbitrary device shell command. DISABLED by default — set the env var
    ADB_MCP_ALLOW_SHELL=1 to enable. Prefer the specific scoped tools; this exists
    only as an explicit, opt-in escape hatch. Returns {rc, output}."""
    if not shell_allowed():
        return err(
            "run_shell is disabled. Set ADB_MCP_ALLOW_SHELL=1 to enable the opt-in scoped shell escape hatch."
        )
    rc, out = shell_rc(command, serial=serial, timeout=timeout)
    return ok(rc=rc, output=out, command=command)
