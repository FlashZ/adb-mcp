"""UI automation tools: dump the view hierarchy (uiautomator), find elements by
text/id/description, and tap them by their computed center. This turns the
observe->decide->act loop into structured queries instead of blind pixel taps."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from ..core import err, ok, run, shell, tool

_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")

_REMOTE_DUMP = "/sdcard/adbmcp_uidump.xml"


def _parse_bounds(b: str) -> dict[str, int] | None:
    m = _BOUNDS_RE.match(b or "")
    if not m:
        return None
    x1, y1, x2, y2 = (int(v) for v in m.groups())
    return {
        "left": x1,
        "top": y1,
        "right": x2,
        "bottom": y2,
        "center_x": (x1 + x2) // 2,
        "center_y": (y1 + y2) // 2,
        "width": x2 - x1,
        "height": y2 - y1,
    }


def _dump_xml(serial: str | None) -> str:
    """Run uiautomator dump on the device and return the XML text."""
    # Try dumping straight to stdout first (fast path, supported on most builds).
    out = shell(["uiautomator", "dump", "/dev/tty"], serial, timeout=30)
    if out.lstrip().startswith("<?xml") or "<hierarchy" in out:
        return out[out.index("<") :]
    # Fallback: dump to a file, then read it back.
    shell(["uiautomator", "dump", _REMOTE_DUMP], serial, timeout=30)
    cp = run(["exec-out", "cat", _REMOTE_DUMP], serial=serial, timeout=30)
    return cp.stdout or ""


def _elements(serial: str | None) -> list[dict[str, Any]]:
    xml = _dump_xml(serial)
    if "<hierarchy" not in xml and "<node" not in xml:
        return []
    root = ET.fromstring(xml[xml.index("<") :])
    out: list[dict[str, Any]] = []
    for node in root.iter("node"):
        a = node.attrib
        bounds = _parse_bounds(a.get("bounds", ""))
        out.append(
            {
                "text": a.get("text", ""),
                "resource_id": a.get("resource-id", ""),
                "content_desc": a.get("content-desc", ""),
                "class": a.get("class", ""),
                "package": a.get("package", ""),
                "clickable": a.get("clickable") == "true",
                "enabled": a.get("enabled") == "true",
                "focused": a.get("focused") == "true",
                "checked": a.get("checked") == "true",
                "bounds": bounds,
            }
        )
    return out


@tool()
def dump_ui(
    clickable_only: bool = False, non_empty_only: bool = True, serial: str | None = None
) -> list[dict[str, Any]]:
    """Dump the current on-screen view hierarchy as a flat list of elements
    {text, resource_id, content_desc, class, clickable, enabled, bounds:{...,center_x,center_y}}.

    non_empty_only drops nodes with no text/id/description (usually layout containers);
    clickable_only keeps only clickable nodes."""
    els = _elements(serial)
    if non_empty_only:
        els = [e for e in els if e["text"] or e["resource_id"] or e["content_desc"]]
    if clickable_only:
        els = [e for e in els if e["clickable"]]
    return els


@tool()
def find_elements(
    text: str | None = None,
    resource_id: str | None = None,
    content_desc: str | None = None,
    exact: bool = False,
    serial: str | None = None,
) -> list[dict[str, Any]]:
    """Find on-screen elements matching any of text / resource_id / content_desc.
    Substring match by default; exact=True requires a full match. Returns the same
    element records as dump_ui, each with a bounds.center for tapping."""
    els = _elements(serial)

    def match(field: str, needle: str | None) -> bool:
        if needle is None:
            return True
        return field == needle if exact else needle.lower() in (field or "").lower()

    return [
        e
        for e in els
        if match(e["text"], text)
        and match(e["resource_id"], resource_id)
        and match(e["content_desc"], content_desc)
        and (text is not None or resource_id is not None or content_desc is not None)
    ]


@tool()
def tap_element(
    text: str | None = None,
    resource_id: str | None = None,
    content_desc: str | None = None,
    index: int = 0,
    exact: bool = False,
    serial: str | None = None,
) -> dict[str, Any]:
    """Find an element (by text/resource_id/content_desc) and tap its center.
    `index` selects among multiple matches. Returns the matched element + tap point."""
    matches = find_elements(
        text=text,
        resource_id=resource_id,
        content_desc=content_desc,
        exact=exact,
        serial=serial,
    )
    if not matches:
        query = {"text": text, "resource_id": resource_id, "content_desc": content_desc}
        return err("no matching element", query=query)
    if index >= len(matches):
        return err(f"index {index} out of range ({len(matches)} matches)", matches=len(matches))
    el = matches[index]
    b = el.get("bounds")
    if not b:
        return err("matched element has no bounds", element=el)
    shell(["input", "tap", str(b["center_x"]), str(b["center_y"])], serial)
    return ok(tapped=[b["center_x"], b["center_y"]], element=el, total_matches=len(matches))
