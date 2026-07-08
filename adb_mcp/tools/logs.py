"""Logging tools: background logcat capture + structured dump/filter, plus
ANR traces and bugreport pulls."""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any

from ..core import _NO_WINDOW, adb_bin, default_serial, err, ok, run, tool

# One background logcat capture at a time.
_proc: subprocess.Popen | None = None
_buf_path: str | None = None
_fh = None


def _tmp(name: str) -> str:
    return os.path.join(os.environ.get("TEMP", os.environ.get("TMPDIR", "/tmp")), name)


@tool()
def logcat_start(serial: str | None = None, clear: bool = True, buffers: str | None = None) -> dict[str, Any]:
    """Start a background logcat capture to a temp file. Read it with logcat_dump/
    logcat_filter; end it with logcat_stop. Only one capture runs at a time.
    `buffers` optionally selects e.g. 'main,system,crash'."""
    global _proc, _buf_path, _fh
    logcat_stop()
    if clear:
        run(["logcat", "-c"], serial=serial)
    path = _tmp(f"adbmcp_logcat_{int(time.time())}.log")
    cmd = [adb_bin()]
    ser = serial if serial is not None else default_serial()
    if ser:
        cmd += ["-s", ser]
    cmd += ["logcat", "-v", "threadtime"]
    if buffers:
        cmd += ["-b", buffers]
    _fh = open(path, "w", encoding="utf-8", errors="replace")
    _proc = subprocess.Popen(cmd, stdout=_fh, stderr=subprocess.STDOUT, creationflags=_NO_WINDOW)
    _buf_path = path
    return ok(status="started", buffer=path, pid=_proc.pid)


@tool()
def logcat_stop() -> dict[str, Any]:
    """Stop the background logcat capture started by logcat_start."""
    global _proc, _fh
    if _proc is not None:
        _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _proc.kill()
        _proc = None
        if _fh:
            _fh.close()
            _fh = None
        return ok(status="stopped", buffer=_buf_path)
    return ok(status="not_running")


def _parse_line(line: str) -> dict[str, Any] | None:
    line = line.rstrip()
    if not line or line.startswith("---------"):
        return None
    parts = line.split(None, 5)
    if len(parts) < 6:
        return None
    date, tm, pid, tid, level, rest = parts
    if not (pid.isdigit() and tid.isdigit()) or len(level) != 1:
        return None
    tag, _, msg = rest.partition(":")
    return {
        "time": f"{date} {tm}",
        "pid": int(pid),
        "tid": int(tid),
        "level": level,
        "tag": tag.strip(),
        "message": msg.strip(),
    }


def _read_buffer() -> list[str]:
    if not _buf_path or not os.path.isfile(_buf_path):
        return []
    with open(_buf_path, encoding="utf-8", errors="replace") as fh:
        return fh.read().splitlines()


@tool()
def logcat_dump(
    tags: list[str] | None = None,
    priority: str | None = None,
    message_contains: str | None = None,
    tail: int = 500,
    serial: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent logcat lines as records {time, pid, tid, level, tag, message}.

    Reads the running capture's buffer if active, else does a one-shot `logcat -d`.
    tags = filter by tag substring(s); priority = min level V/D/I/W/E/F;
    message_contains = substring filter on the message; tail = newest N records."""
    lines = (
        _read_buffer()
        if _proc is not None
        else (run(["logcat", "-d", "-v", "threadtime"], serial=serial, timeout=30).stdout or "").splitlines()
    )
    records = [r for r in (_parse_line(ln) for ln in lines) if r]
    if tags:
        tl = [t.lower() for t in tags]
        records = [r for r in records if any(t in r["tag"].lower() for t in tl)]
    if priority:
        order = "VDIWEF"
        want = order.find(priority.upper())
        if want >= 0:
            records = [r for r in records if order.find(r["level"]) >= want]
    if message_contains:
        mc = message_contains.lower()
        records = [r for r in records if mc in r["message"].lower()]
    return records[-tail:]


@tool()
def logcat_filter(tags: list[str], tail: int = 200, serial: str | None = None) -> list[dict[str, Any]]:
    """Convenience: logcat_dump filtered to the given tags (e.g. ['Unity','libc','DEBUG'])."""
    return logcat_dump(tags=tags, tail=tail, serial=serial)


@tool()
def logcat_clear(serial: str | None = None) -> dict[str, Any]:
    """Clear the device logcat ring buffers (`logcat -c`)."""
    run(["logcat", "-c"], serial=serial)
    return ok(status="cleared")


@tool()
def get_crash_log(tail: int = 200, serial: str | None = None) -> list[dict[str, Any]]:
    """Dump the 'crash' logcat buffer (native + Java crashes), newest `tail` records."""
    out = run(["logcat", "-d", "-b", "crash", "-v", "threadtime"], serial=serial, timeout=30).stdout or ""
    return [r for r in (_parse_line(ln) for ln in out.splitlines()) if r][-tail:]


@tool()
def get_anr_traces(local_path: str | None = None, serial: str | None = None) -> dict[str, Any]:
    """Pull the most recent ANR trace file (/data/anr/traces.txt or /data/anr/).
    Returns {status, local, size} (needs root/permission on some devices)."""
    local = local_path or _tmp(f"anr_traces_{int(time.time())}.txt")
    cp = run(["pull", "/data/anr/traces.txt", local], serial=serial, timeout=60)
    if os.path.exists(local) and os.path.getsize(local) > 0:
        return ok(status="ok", local=local, size=os.path.getsize(local))
    return err("no traces.txt (try /data/anr/ dir, or needs root)", message=(cp.stderr or "").strip())


@tool()
def capture_bugreport(local_path: str, serial: str | None = None) -> dict[str, Any]:
    """Capture a full bugreport zip to `local_path` (slow; can take minutes)."""
    cp = run(["bugreport", local_path], serial=serial, timeout=600)
    ok_ = os.path.exists(local_path)
    return (
        ok(status="ok", local=local_path, size=os.path.getsize(local_path))
        if ok_
        else err("bugreport failed", message=(cp.stderr or cp.stdout or "").strip())
    )
