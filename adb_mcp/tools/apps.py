"""Application/package tools: list, launch, lifecycle, install, permissions."""

from __future__ import annotations

import os
import time
from typing import Any

from ..core import err, ok, run, shell, tool


def _pidof(package: str, serial: str | None) -> int | None:
    out = shell(["pidof", package], serial).strip()
    if out and out.split()[0].isdigit():
        return int(out.split()[0])
    ps = shell(["ps", "-A"], serial)
    for line in ps.splitlines():
        if line.rstrip().endswith(package):
            cols = line.split()
            if len(cols) > 1 and cols[1].isdigit():
                return int(cols[1])
    return None


@tool()
def list_packages(
    filter: str | None = None,
    only_third_party: bool = False,
    only_enabled: bool = False,
    include_paths: bool = False,
    serial: str | None = None,
) -> list[Any]:
    """List installed package names. `filter` = case-insensitive substring.
    only_third_party excludes system apps; include_paths returns {package, apk}."""
    args = ["pm", "list", "packages"]
    if only_third_party:
        args.append("-3")
    if only_enabled:
        args.append("-e")
    if include_paths:
        args.append("-f")
    out = shell(args, serial)
    result: list[Any] = []
    for ln in out.splitlines():
        if not ln.startswith("package:"):
            continue
        body = ln[len("package:") :].strip()
        if include_paths and "=" in body:
            apk, _, pkg = body.rpartition("=")
            result.append({"package": pkg, "apk": apk})
        else:
            result.append(body)
    if filter:
        f = filter.lower()
        result = [r for r in result if f in (r["package"] if isinstance(r, dict) else r).lower()]
    return sorted(result, key=lambda r: r["package"] if isinstance(r, dict) else r)


@tool()
def launch_package(package: str, serial: str | None = None) -> dict[str, Any]:
    """Launch an app by package via its LAUNCHER intent (idempotent).
    Returns {package, pid, status}."""
    shell(["monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"], serial)
    time.sleep(1.0)
    pid = _pidof(package, serial)
    return {"package": package, "pid": pid, "status": "running" if pid else "not_running"}


@tool()
def launch_activity(component: str, serial: str | None = None) -> dict[str, Any]:
    """Start an explicit activity, e.g. 'com.app/.MainActivity' (`am start -n`).
    Returns the am output and resulting pid if resolvable."""
    out = shell(["am", "start", "-n", component], serial)
    pkg = component.split("/", 1)[0]
    time.sleep(0.8)
    return {"component": component, "pid": _pidof(pkg, serial), "message": out}


@tool()
def force_stop(package: str, serial: str | None = None) -> dict[str, Any]:
    """Force-stop an app (idempotent). Returns {package, status}."""
    shell(["am", "force-stop", package], serial)
    return {"package": package, "status": "stopped"}


@tool()
def kill_background(package: str, serial: str | None = None) -> dict[str, Any]:
    """Kill an app's background processes (`am kill`, gentler than force-stop)."""
    shell(["am", "kill", package], serial)
    return {"package": package, "status": "killed"}


@tool()
def clear_app_data(package: str, serial: str | None = None) -> dict[str, Any]:
    """Clear ALL app data for a package (destructive: wipes saves/cache/prefs)."""
    out = shell(["pm", "clear", package], serial)
    return {"package": package, "status": out.strip() or "unknown"}


@tool()
def app_status(package: str, serial: str | None = None) -> dict[str, Any]:
    """Return {package, pid, running} for a package."""
    pid = _pidof(package, serial)
    return {"package": package, "pid": pid, "running": pid is not None}


@tool()
def get_current_activity(serial: str | None = None) -> dict[str, Any]:
    """Return the currently focused activity/package (foreground app)."""
    out = shell(["dumpsys", "activity", "activities"], serial)
    for line in out.splitlines():
        line = line.strip()
        if "mResumedActivity" in line or "ResumedActivity" in line or "topResumedActivity" in line:
            # ... u0 com.app/.Main t123}
            for tok in line.split():
                if "/" in tok and "." in tok:
                    pkg = tok.split("/")[0]
                    return ok(component=tok.rstrip("}"), package=pkg)
    # fallback via window focus
    win = shell(["dumpsys", "window"], serial)
    for line in win.splitlines():
        if "mCurrentFocus" in line and "/" in line:
            tok = line.strip().rstrip("}").split()[-1]
            return ok(component=tok, package=tok.split("/")[0])
    return err("could not determine current activity")


@tool()
def get_package_info(package: str, serial: str | None = None) -> dict[str, Any]:
    """Return structured package info: versionName, versionCode, targetSdk, minSdk,
    installer, firstInstall/lastUpdate times, and granted runtime permissions."""
    out = shell(["dumpsys", "package", package], serial)
    info: dict[str, Any] = {"package": package, "granted_permissions": []}
    for raw in out.splitlines():
        line = raw.strip()
        if line.startswith("versionName="):
            info["versionName"] = line.split("=", 1)[1]
        elif line.startswith("versionCode="):
            info["versionCode"] = line.split("=", 1)[1].split()[0]
        elif line.startswith("targetSdk="):
            info["targetSdk"] = line.split("=", 1)[1].split()[0]
        elif line.startswith("minSdk="):
            info["minSdk"] = line.split("=", 1)[1].split()[0]
        elif line.startswith("installerPackageName="):
            info["installer"] = line.split("=", 1)[1]
        elif line.startswith("firstInstallTime="):
            info["firstInstallTime"] = line.split("=", 1)[1]
        elif line.startswith("lastUpdateTime="):
            info["lastUpdateTime"] = line.split("=", 1)[1]
        elif ": granted=true" in line and line.startswith("android.permission"):
            info["granted_permissions"].append(line.split(":")[0])
    if "versionName" not in info:
        return err(f"package not found or no info: {package}", package=package)
    return info


@tool()
def install_apk(
    apk_paths: list[str],
    replace: bool = True,
    grant_permissions: bool = True,
    downgrade: bool = False,
    serial: str | None = None,
) -> dict[str, Any]:
    """Install an APK, or a split-APK set via install-multiple when >1 path given.
    replace=-r, grant_permissions=-g, downgrade=-d. Returns {status, message}."""
    for p in apk_paths:
        if not os.path.isfile(p):
            return err(f"apk not found: {p}")
    flags = []
    if replace:
        flags.append("-r")
    if grant_permissions:
        flags.append("-g")
    if downgrade:
        flags.append("-d")
    verb = "install-multiple" if len(apk_paths) > 1 else "install"
    cp = run([verb, *flags, *apk_paths], serial=serial, timeout=300)
    out = (cp.stdout or "") + (cp.stderr or "")
    success = "Success" in out
    return {"status": "ok" if success else "failed", "apks": apk_paths, "message": out.strip()}


@tool()
def uninstall(package: str, keep_data: bool = False, serial: str | None = None) -> dict[str, Any]:
    """Uninstall a package. keep_data=True keeps data/cache dirs (`-k`)."""
    args = ["uninstall"] + (["-k"] if keep_data else []) + [package]
    cp = run(args, serial=serial, timeout=60)
    out = (cp.stdout or "") + (cp.stderr or "")
    return {"package": package, "status": "ok" if "Success" in out else "failed", "message": out.strip()}


@tool()
def grant_permission(package: str, permission: str, serial: str | None = None) -> dict[str, Any]:
    """Grant a runtime permission, e.g. 'android.permission.CAMERA' (`pm grant`)."""
    out = shell(["pm", "grant", package, permission], serial)
    return ok(package=package, permission=permission, message=out) if not out else err(out)


@tool()
def revoke_permission(package: str, permission: str, serial: str | None = None) -> dict[str, Any]:
    """Revoke a runtime permission (`pm revoke`)."""
    out = shell(["pm", "revoke", package, permission], serial)
    return ok(package=package, permission=permission, message=out) if not out else err(out)


@tool()
def set_package_enabled(package: str, enabled: bool, serial: str | None = None) -> dict[str, Any]:
    """Enable or disable a package (`pm enable` / `pm disable-user`)."""
    verb = "enable" if enabled else "disable-user"
    out = shell(["pm", verb, package], serial)
    return ok(package=package, enabled=enabled, message=out)


@tool()
def start_service(component: str, serial: str | None = None) -> dict[str, Any]:
    """Start a service by component 'pkg/.Service' (`am startservice`)."""
    out = shell(["am", "startservice", "-n", component], serial)
    return ok(component=component, message=out)


@tool()
def send_broadcast(
    action: str,
    component: str | None = None,
    extras: dict[str, str] | None = None,
    serial: str | None = None,
) -> dict[str, Any]:
    """Send a broadcast intent (`am broadcast -a <action>`). Optional target
    component and string extras {key: value}."""
    args = ["am", "broadcast", "-a", action]
    if component:
        args += ["-n", component]
    for k, v in (extras or {}).items():
        args += ["--es", k, v]
    out = shell(args, serial)
    return ok(action=action, message=out)
