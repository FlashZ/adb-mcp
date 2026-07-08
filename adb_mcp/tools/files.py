"""File tools: list, stat, pull, push, read, write, mkdir, delete."""

from __future__ import annotations

import os
import posixpath
import shlex
import tempfile
from typing import Any

from ..core import err, ok, run, shell, shell_rc, tool


@tool()
def list_files(remote_dir: str, as_root: bool = False, serial: str | None = None) -> list[dict[str, Any]]:
    """List a device directory: [{name, size, is_dir, is_link, perms}].
    as_root uses `su -c ls` on rooted devices. Symlinked dirs (e.g. /sdcard on
    Samsung) are dereferenced so their contents are listed, not the link."""
    # -L dereferences the arg so a symlinked directory lists its contents.
    cmd = f"ls -laL {shlex.quote(remote_dir)}"
    out = shell(f"su -c {shlex.quote(cmd)}" if as_root else cmd, serial)
    entries = []
    for line in out.splitlines():
        cols = line.split(None, 7)
        if len(cols) < 8 or cols[0] == "total":
            continue
        perms, _, _, _, size, _, _, name = cols[:8]
        entries.append(
            {
                "name": name.split(" -> ")[0],
                "size": int(size) if size.isdigit() else None,
                "is_dir": perms.startswith("d"),
                "is_link": perms.startswith("l"),
                "perms": perms,
                "link_target": name.split(" -> ", 1)[1] if " -> " in name else None,
            }
        )
    return entries


@tool()
def file_exists(remote: str, as_root: bool = False, serial: str | None = None) -> dict[str, Any]:
    """Check whether a path exists on the device. Returns {exists, is_dir}."""
    test = f"test -e {shlex.quote(remote)} && echo Y || echo N"
    out = shell(f"su -c {shlex.quote(test)}" if as_root else test, serial)
    exists = out.strip().endswith("Y")
    is_dir = False
    if exists:
        dtest = f"test -d {shlex.quote(remote)} && echo Y || echo N"
        is_dir = shell(f"su -c {shlex.quote(dtest)}" if as_root else dtest, serial).strip().endswith("Y")
    return ok(exists=exists, is_dir=is_dir, remote=remote)


@tool()
def stat_file(remote: str, serial: str | None = None) -> dict[str, Any]:
    """Return stat info for a device path: {size, mtime, perms, uid, gid} (best-effort)."""
    out = shell(["stat", "-c", "%s|%Y|%A|%U|%G", remote], serial)
    if "|" not in out:
        return err(out or "stat failed", remote=remote)
    size, mtime, perms, uid, gid = (out.strip().split("|") + [""] * 5)[:5]
    return ok(
        remote=remote,
        size=int(size) if size.isdigit() else None,
        mtime=int(mtime) if mtime.isdigit() else None,
        perms=perms,
        uid=uid,
        gid=gid,
    )


@tool()
def pull(remote: str, local: str, serial: str | None = None) -> dict[str, Any]:
    """Pull a file/dir from the device to host path `local`."""
    os.makedirs(os.path.dirname(os.path.abspath(local)), exist_ok=True)
    cp = run(["pull", remote, local], serial=serial, timeout=300)
    exists = os.path.exists(local)
    return {
        "remote": remote,
        "local": local,
        "status": "ok" if exists else "failed",
        "size": os.path.getsize(local) if exists and os.path.isfile(local) else None,
        "message": (cp.stdout or cp.stderr or "").strip(),
    }


@tool()
def push(local: str, remote: str, serial: str | None = None) -> dict[str, Any]:
    """Push a host file `local` to device path `remote`."""
    if not os.path.exists(local):
        return err(f"local file not found: {local}")
    cp = run(["push", local, remote], serial=serial, timeout=300)
    return {
        "local": local,
        "remote": remote,
        "status": "ok" if cp.returncode == 0 else "failed",
        "message": (cp.stdout or cp.stderr or "").strip(),
    }


@tool()
def read_file(
    remote: str, max_bytes: int = 65536, as_root: bool = False, serial: str | None = None
) -> dict[str, Any]:
    """Read a text file from the device (up to max_bytes). as_root uses `su -c cat`
    (WSA/Magisk). Returns {remote, truncated, content}."""
    cmd = f"cat {shlex.quote(remote)}"
    out = shell(f"su -c {shlex.quote(cmd)}" if as_root else cmd, serial)
    raw = out.encode("utf-8", "replace")
    truncated = len(raw) > max_bytes
    if truncated:
        out = raw[:max_bytes].decode("utf-8", "replace")
    return {"remote": remote, "truncated": truncated, "content": out}


@tool()
def write_file(remote: str, content: str, as_root: bool = False, serial: str | None = None) -> dict[str, Any]:
    """Write text `content` to a device file by pushing a temp file (handles any
    content safely, unlike shell echo). as_root pushes to /data/local/tmp then
    `su -c cp` into place. Returns {status, remote, bytes}."""
    tmp = tempfile.NamedTemporaryFile("w", suffix=".adbmcp", delete=False, encoding="utf-8")
    try:
        tmp.write(content)
        tmp.close()
        if as_root:
            staging = "/data/local/tmp/" + posixpath.basename(remote) + ".adbmcp"
            run(["push", tmp.name, staging], serial=serial, timeout=120)
            cp_cmd = f"cp {shlex.quote(staging)} {shlex.quote(remote)}"
            rc, out = shell_rc(f"su -c {shlex.quote(cp_cmd)}", serial)
            shell(["rm", "-f", staging], serial)
            if rc != 0:
                return err(out or "root copy failed", remote=remote)
        else:
            cp = run(["push", tmp.name, remote], serial=serial, timeout=120)
            if cp.returncode != 0:
                return err((cp.stderr or "push failed").strip(), remote=remote)
        return ok(status="ok", remote=remote, bytes=len(content.encode("utf-8")))
    finally:
        os.unlink(tmp.name)


@tool()
def make_dir(remote: str, as_root: bool = False, serial: str | None = None) -> dict[str, Any]:
    """Create a directory on the device (`mkdir -p`)."""
    cmd = f"mkdir -p {shlex.quote(remote)}"
    rc, out = shell_rc(f"su -c {shlex.quote(cmd)}" if as_root else cmd, serial)
    return ok(status="ok", remote=remote) if rc == 0 else err(out or "mkdir failed", remote=remote)


@tool()
def delete_file(
    remote: str, recursive: bool = False, as_root: bool = False, serial: str | None = None
) -> dict[str, Any]:
    """Delete a device file or (recursive=True) directory. DESTRUCTIVE.
    Refuses obviously dangerous roots like '/', '/system', '/data'."""
    norm = remote.rstrip("/")
    if norm in ("", "/", "/system", "/data", "/sdcard", "/vendor", "/product"):
        return err(f"refusing to delete protected path: {remote}")
    flag = "-rf" if recursive else "-f"
    cmd = f"rm {flag} {shlex.quote(remote)}"
    rc, out = shell_rc(f"su -c {shlex.quote(cmd)}" if as_root else cmd, serial)
    return ok(status="deleted", remote=remote) if rc == 0 else err(out or "rm failed", remote=remote)
