"""Device tools: discovery, properties, connection, power, root."""

from __future__ import annotations

from typing import Any

from ..core import default_serial, err, ok, run, set_runtime_serial, shell, tool


@tool()
def get_devices() -> list[dict[str, Any]]:
    """List attached devices/emulators with state and transport.

    Returns [{serial, state, is_usb, model, device, transport_id}]. is_usb is
    False for network devices (serials containing ':', e.g. WSA/emulators)."""
    cp = run(["devices", "-l"])
    devices = []
    for line in (cp.stdout or "").splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        serial = parts[0]
        meta = {}
        for p in parts[2:]:
            if ":" in p:
                k, v = p.split(":", 1)
                meta[k] = v
        devices.append(
            {
                "serial": serial,
                "state": parts[1] if len(parts) > 1 else "unknown",
                "is_usb": ":" not in serial,
                "model": meta.get("model"),
                "device": meta.get("device"),
                "transport_id": meta.get("transport_id"),
            }
        )
    return devices


@tool()
def get_state(serial: str | None = None) -> dict[str, Any]:
    """Return the connection state of a device: device / offline / unauthorized."""
    cp = run(["get-state"], serial=serial)
    return ok(state=(cp.stdout or cp.stderr or "").strip())


@tool()
def adb_version() -> dict[str, Any]:
    """Return the host adb client version string and the resolved adb path."""
    from ..core import adb_bin

    cp = run(["version"])
    return ok(version=(cp.stdout or "").strip(), path=adb_bin())


@tool()
def get_device_properties(serial: str | None = None) -> dict[str, Any]:
    """Return the target environment: model, manufacturer, abi, android release,
    sdk level, build fingerprint, and screen info. Tells the agent exactly what
    it is targeting before acting."""
    g = lambda p: shell(["getprop", p], serial)  # noqa: E731
    props = {
        "model": g("ro.product.model"),
        "manufacturer": g("ro.product.manufacturer"),
        "brand": g("ro.product.brand"),
        "device": g("ro.product.device"),
        "abi": g("ro.product.cpu.abi"),
        "abis": g("ro.product.cpu.abilist"),
        "android": g("ro.build.version.release"),
        "sdk": g("ro.build.version.sdk"),
        "security_patch": g("ro.build.version.security_patch"),
        "fingerprint": g("ro.build.fingerprint"),
        "serialno": g("ro.serialno"),
    }
    props["screen"] = get_screen_info(serial)
    return props


@tool()
def get_screen_info(serial: str | None = None) -> dict[str, Any]:
    """Return effective display size and density: {width, height, density, raw}.

    Prefers the Override size (what input coordinates map to) when set."""
    size = shell(["wm", "size"], serial)
    density = shell(["wm", "density"], serial)
    w = h = dens = None
    # "Physical size: 1440x3120\nOverride size: 1080x2340" -> prefer override
    dims = None
    for line in size.splitlines():
        if "Override size:" in line:
            dims = line.split(":")[-1].strip()
            break
    if dims is None and "size:" in size.lower():
        dims = size.splitlines()[0].split(":")[-1].strip()
    if dims and "x" in dims:
        try:
            w, h = (int(v) for v in dims.split("x"))
        except ValueError:
            pass
    for tok in density.replace(":", " ").split():
        if tok.isdigit():
            dens = int(tok)
            break
    return {"width": w, "height": h, "density": dens, "raw": size}


@tool()
def get_battery(serial: str | None = None) -> dict[str, Any]:
    """Return battery level/status/health/temperature (from dumpsys battery)."""
    out = shell(["dumpsys", "battery"], serial)
    info: dict[str, Any] = {}
    for line in out.splitlines():
        if ":" not in line:
            continue
        k, v = (x.strip() for x in line.split(":", 1))
        if k in ("level", "scale", "temperature", "voltage"):
            info[k] = int(v) if v.lstrip("-").isdigit() else v
        elif k in ("status", "health", "AC powered", "USB powered", "Charge counter"):
            info[k] = v
    if isinstance(info.get("temperature"), int):
        info["temperature_c"] = info["temperature"] / 10.0
    return info


@tool()
def connect(host_port: str) -> dict[str, Any]:
    """`adb connect ip:port` — attach a network device (WSA, emulator, wireless)."""
    cp = run(["connect", host_port])
    out = (cp.stdout or cp.stderr or "").strip()
    if "connected" in out or "already" in out:
        return ok(target=host_port, message=out)
    return err(out, target=host_port)


@tool()
def disconnect(host_port: str | None = None) -> dict[str, Any]:
    """`adb disconnect` a network device (or all if host_port omitted)."""
    cp = run(["disconnect"] + ([host_port] if host_port else []))
    return ok(message=(cp.stdout or cp.stderr or "").strip())


@tool()
def wait_for_device(serial: str | None = None, timeout: float = 60.0) -> dict[str, Any]:
    """Block until the device is online (or timeout). Useful after reboot/connect."""
    cp = run(["wait-for-device"], serial=serial, timeout=timeout)
    return ok(status="online") if cp.returncode == 0 else err("wait-for-device failed")


@tool()
def reboot(mode: str = "", serial: str | None = None) -> dict[str, Any]:
    """Reboot the device. mode: '' (normal), 'recovery', 'bootloader', or 'sideload'."""
    args = ["reboot"] + ([mode] if mode else [])
    run(args, serial=serial, timeout=15)
    return ok(status="rebooting", mode=mode or "normal")


@tool()
def set_default_device(serial: str) -> dict[str, Any]:
    """Set the session default device serial (overrides ADB_SERIAL for later calls).
    Pass an empty string to clear it."""
    set_runtime_serial(serial or None)
    return ok(default_serial=serial or None)


@tool()
def get_default_device() -> dict[str, Any]:
    """Return the currently active default device serial (runtime or ADB_SERIAL)."""
    return ok(default_serial=default_serial())


@tool()
def root_adb(serial: str | None = None) -> dict[str, Any]:
    """Restart adbd as root (`adb root`). Only works on rooted/userdebug builds;
    on production builds use su via read_file(as_root=True) etc. instead."""
    cp = run(["root"], serial=serial, timeout=20)
    return ok(message=(cp.stdout or cp.stderr or "").strip())


@tool()
def unroot_adb(serial: str | None = None) -> dict[str, Any]:
    """Restart adbd without root (`adb unroot`)."""
    cp = run(["unroot"], serial=serial, timeout=20)
    return ok(message=(cp.stdout or cp.stderr or "").strip())


@tool()
def remount(serial: str | None = None) -> dict[str, Any]:
    """Remount /system (and other partitions) read-write (`adb remount`). Needs root."""
    cp = run(["remount"], serial=serial, timeout=20)
    return ok(message=(cp.stdout or cp.stderr or "").strip())
