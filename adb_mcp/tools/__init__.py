"""Importing this package registers every tool onto the shared FastMCP instance.

Each submodule decorates its functions with @tool (adb_mcp.core.mcp.tool), so a
single `import adb_mcp.tools` wires up the whole surface."""

from . import (  # noqa: F401
    apps,
    device,
    files,
    input,
    logs,
    media,
    network,
    system,
    ui,
)

__all__ = [
    "device",
    "apps",
    "input",
    "ui",
    "logs",
    "media",
    "files",
    "network",
    "system",
]
