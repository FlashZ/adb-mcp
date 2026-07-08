"""Network tools: port forward/reverse (adb forward/reverse), IP, wifi/data toggles.

`reverse_port` is the key one for local server shims — it maps a device-side port
to a host-side port so the app's localhost traffic reaches your PC."""

from __future__ import annotations

from typing import Any

from ..core import err, ok, run, shell, tool


@tool()
def forward_port(local_port: int, remote_port: int, serial: str | None = None) -> dict[str, Any]:
    """`adb forward tcp:local tcp:remote` — forward a HOST port to a DEVICE port
    (host connects locally, traffic reaches the device)."""
    cp = run(["forward", f"tcp:{local_port}", f"tcp:{remote_port}"], serial=serial)
    if cp.returncode == 0:
        return ok(host_port=local_port, device_port=remote_port)
    return err((cp.stderr or "forward failed").strip())


@tool()
def reverse_port(device_port: int, host_port: int, serial: str | None = None) -> dict[str, Any]:
    """`adb reverse tcp:device tcp:host` — map a DEVICE port to a HOST port so the
    app's 127.0.0.1:<device_port> traffic reaches your PC (e.g. a local API/CDN shim)."""
    cp = run(["reverse", f"tcp:{device_port}", f"tcp:{host_port}"], serial=serial)
    if cp.returncode == 0:
        return ok(device_port=device_port, host_port=host_port)
    return err((cp.stderr or "reverse failed").strip())


@tool()
def list_forwards(serial: str | None = None) -> list[dict[str, Any]]:
    """List active `adb forward` rules: [{serial, local, remote}]."""
    cp = run(["forward", "--list"], serial=serial)
    out = []
    for line in (cp.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 3:
            out.append({"serial": parts[0], "local": parts[1], "remote": parts[2]})
    return out


@tool()
def list_reverses(serial: str | None = None) -> list[dict[str, Any]]:
    """List active `adb reverse` rules: [{remote, local}]."""
    cp = run(["reverse", "--list"], serial=serial)
    out = []
    for line in (cp.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            out.append({"remote": parts[-2], "local": parts[-1]})
    return out


@tool()
def remove_forward(local_port: int, serial: str | None = None) -> dict[str, Any]:
    """Remove a single `adb forward` rule for tcp:local_port."""
    run(["forward", "--remove", f"tcp:{local_port}"], serial=serial)
    return ok(removed=f"tcp:{local_port}")


@tool()
def remove_reverse(device_port: int, serial: str | None = None) -> dict[str, Any]:
    """Remove a single `adb reverse` rule for tcp:device_port."""
    run(["reverse", "--remove", f"tcp:{device_port}"], serial=serial)
    return ok(removed=f"tcp:{device_port}")


@tool()
def clear_forwards(serial: str | None = None) -> dict[str, Any]:
    """Remove ALL forward and reverse rules for the device."""
    run(["forward", "--remove-all"], serial=serial)
    run(["reverse", "--remove-all"], serial=serial)
    return ok(status="cleared")


@tool()
def get_ip_address(iface: str = "wlan0", serial: str | None = None) -> dict[str, Any]:
    """Return the device's IPv4 address on an interface (default wlan0)."""
    out = shell(["ip", "-f", "inet", "addr", "show", iface], serial)
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("inet "):
            return ok(iface=iface, ip=line.split()[1].split("/")[0])
    return err(f"no IPv4 on {iface}", iface=iface, raw=out)


@tool()
def set_wifi(enabled: bool, serial: str | None = None) -> dict[str, Any]:
    """Enable/disable Wi-Fi via `svc wifi` (may need root on newer Android)."""
    out = shell(["svc", "wifi", "enable" if enabled else "disable"], serial)
    return ok(wifi=enabled, message=out)


@tool()
def set_mobile_data(enabled: bool, serial: str | None = None) -> dict[str, Any]:
    """Enable/disable mobile data via `svc data` (may need root on newer Android)."""
    out = shell(["svc", "data", "enable" if enabled else "disable"], serial)
    return ok(mobile_data=enabled, message=out)


@tool()
def set_airplane_mode(enabled: bool, serial: str | None = None) -> dict[str, Any]:
    """Toggle airplane mode (settings + broadcast). May need root on newer Android."""
    state = "true" if enabled else "false"
    shell(["settings", "put", "global", "airplane_mode_on", "1" if enabled else "0"], serial)
    out = shell(
        ["am", "broadcast", "-a", "android.intent.action.AIRPLANE_MODE", "--ez", "state", state],
        serial,
    )
    return ok(airplane_mode=enabled, message=out)
