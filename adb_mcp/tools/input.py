"""Input tools: tap, swipe, drag, text, key events, and convenience buttons."""

from __future__ import annotations

from typing import Any

from ..core import ok, shell, tool


@tool()
def tap(x: int, y: int, serial: str | None = None) -> dict[str, Any]:
    """Tap the screen at pixel (x, y)."""
    shell(["input", "tap", str(x), str(y)], serial)
    return {"action": "tap", "x": x, "y": y}


@tool()
def long_press(x: int, y: int, duration_ms: int = 800, serial: str | None = None) -> dict[str, Any]:
    """Long-press at (x, y) for duration_ms (implemented as a zero-distance swipe)."""
    shell(["input", "swipe", str(x), str(y), str(x), str(y), str(duration_ms)], serial)
    return {"action": "long_press", "x": x, "y": y, "duration_ms": duration_ms}


@tool()
def swipe(
    x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300, serial: str | None = None
) -> dict[str, Any]:
    """Swipe from (x1,y1) to (x2,y2) over duration_ms. Use for scrolling/flinging."""
    shell(["input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)], serial)
    return {"action": "swipe", "from": [x1, y1], "to": [x2, y2], "duration_ms": duration_ms}


@tool()
def drag(
    x1: int, y1: int, x2: int, y2: int, duration_ms: int = 1000, serial: str | None = None
) -> dict[str, Any]:
    """Drag (slow swipe) from (x1,y1) to (x2,y2). Alias of swipe with a longer default."""
    shell(["input", "draganddrop", str(x1), str(y1), str(x2), str(y2), str(duration_ms)], serial)
    return {"action": "drag", "from": [x1, y1], "to": [x2, y2], "duration_ms": duration_ms}


@tool()
def text(value: str, serial: str | None = None) -> dict[str, Any]:
    """Type a string into the focused field. Spaces and shell-special characters
    are escaped so the literal text is entered."""
    escaped = (
        value.replace("%", "%%")
        .replace(" ", "%s")
        .replace("&", "\\&")
        .replace("<", "\\<")
        .replace(">", "\\>")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("|", "\\|")
        .replace(";", "\\;")
        .replace('"', '\\"')
        .replace("'", "\\'")
    )
    shell(["input", "text", escaped], serial)
    return {"action": "text", "value": value}


@tool()
def keyevent(keycode: str | int, longpress: bool = False, serial: str | None = None) -> dict[str, Any]:
    """Send a key event. Accepts a numeric keycode or a name like BACK, HOME,
    ENTER, TAB, DEL, APP_SWITCH, VOLUME_UP (KEYCODE_ prefix optional)."""
    kc = str(keycode)
    if not kc.isdigit() and not kc.startswith("KEYCODE_"):
        kc = "KEYCODE_" + kc.upper()
    args = ["input", "keyevent"] + (["--longpress"] if longpress else []) + [kc]
    shell(args, serial)
    return {"action": "keyevent", "keycode": kc, "longpress": longpress}


def _key(name: str, serial: str | None) -> dict[str, Any]:
    shell(["input", "keyevent", "KEYCODE_" + name], serial)
    return {"action": "keyevent", "keycode": "KEYCODE_" + name}


@tool()
def press_home(serial: str | None = None) -> dict[str, Any]:
    """Press the HOME button."""
    return _key("HOME", serial)


@tool()
def press_back(serial: str | None = None) -> dict[str, Any]:
    """Press the BACK button."""
    return _key("BACK", serial)


@tool()
def press_recents(serial: str | None = None) -> dict[str, Any]:
    """Open the recent-apps / overview screen (APP_SWITCH)."""
    return _key("APP_SWITCH", serial)


@tool()
def press_power(serial: str | None = None) -> dict[str, Any]:
    """Press the POWER button (toggles screen on/off)."""
    return _key("POWER", serial)


@tool()
def press_enter(serial: str | None = None) -> dict[str, Any]:
    """Press ENTER."""
    return _key("ENTER", serial)


@tool()
def wake_and_unlock(serial: str | None = None) -> dict[str, Any]:
    """Wake the screen and swipe up to dismiss a non-secure lock screen."""
    shell(["input", "keyevent", "KEYCODE_WAKEUP"], serial)
    shell(["input", "keyevent", "KEYCODE_MENU"], serial)
    return ok(status="woke_and_unlocked")
