"""Media tools: screenshots (inline image or base64) and screen recording."""

from __future__ import annotations

import base64
import os
import re
import time
from typing import Any

from mcp.server.fastmcp import Image

from ..core import err, ok, quote_argv, run, shell, tool


def _screencap(serial: str | None) -> bytes:
    cp = run(["exec-out", "screencap", "-p"], serial=serial, timeout=30, binary=True)
    data = cp.stdout or b""
    # Some legacy transports translate LF->CRLF; repair the PNG stream.
    if not data.startswith(b"\x89PNG") and b"\r\n" in data[:64]:
        data = data.replace(b"\r\n", b"\n")
    return data


@tool()
def capture_screen(serial: str | None = None, save_path: str | None = None) -> Image:
    """Capture a screenshot and return it as an inline PNG image. If save_path is
    given, also writes the PNG there. Ideal for an observe->decide->tap loop / OCR."""
    data = _screencap(serial)
    if save_path:
        with open(save_path, "wb") as fh:
            fh.write(data)
    return Image(data=data, format="png")


@tool()
def capture_screen_to_file(save_path: str, serial: str | None = None) -> dict[str, Any]:
    """Capture a screenshot and save it to `save_path`, returning {status, path, bytes}
    (no inline image — use when you only need the file)."""
    data = _screencap(serial)
    with open(save_path, "wb") as fh:
        fh.write(data)
    return ok(status="ok", path=save_path, bytes=len(data))


@tool()
def capture_screen_base64(serial: str | None = None) -> dict[str, Any]:
    """Capture a screenshot and return {format, bytes, base64} — for when a raw
    base64 payload is preferred over an inline image."""
    data = _screencap(serial)
    return ok(format="png", bytes=len(data), base64=base64.b64encode(data).decode())


# --- screen recording -------------------------------------------------------
_REMOTE_MP4 = "/sdcard/adbmcp_record.mp4"


@tool()
def record_screen_start(
    time_limit_s: int = 180,
    bit_rate_mbps: int = 8,
    size: str | None = None,
    serial: str | None = None,
) -> dict[str, Any]:
    """Start recording the screen on-device (screenrecord runs in the background).
    time_limit_s caps duration (screenrecord max 180s per segment). `size` like
    '720x1280' to downscale. Call record_screen_stop to finish and pull the mp4."""
    if size and not re.fullmatch(r"\d{2,5}x\d{2,5}", size):
        return err("invalid size — expected WxH like '720x1280'")
    # kill any stale recorder first
    shell(["pkill", "-INT", "screenrecord"], serial)
    args = ["screenrecord", "--time-limit", str(time_limit_s), "--bit-rate", str(bit_rate_mbps * 1_000_000)]
    if size:
        args += ["--size", size]
    args.append(_REMOTE_MP4)
    # Fire-and-forget on the device; screenrecord writes until stopped/limit.
    # Build one quoted command line (injection-safe) and append the background '&'.
    run(["shell", quote_argv(args) + " &"], serial=serial, timeout=5)
    return ok(status="recording", remote=_REMOTE_MP4, time_limit_s=time_limit_s)


@tool()
def record_screen_stop(local_path: str, serial: str | None = None) -> dict[str, Any]:
    """Stop the background screen recording, pull it to `local_path`, and clean up
    the on-device file. Returns {status, local, size}."""
    shell(["pkill", "-INT", "screenrecord"], serial)
    time.sleep(2.0)  # let screenrecord flush the moov atom
    cp = run(["pull", _REMOTE_MP4, local_path], serial=serial, timeout=120)
    shell(["rm", "-f", _REMOTE_MP4], serial)
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        return ok(status="ok", local=local_path, size=os.path.getsize(local_path))
    return err("recording pull failed", message=(cp.stderr or "").strip())
