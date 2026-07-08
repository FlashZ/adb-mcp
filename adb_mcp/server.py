"""adb-mcp entry point.

Importing adb_mcp.tools registers every tool onto the shared FastMCP instance in
adb_mcp.core. `main()` runs the server over stdio (the default MCP transport).

Run directly:      python -m adb_mcp.server
Or via entry point: adb-mcp
"""

from __future__ import annotations

from . import tools  # noqa: F401  (import side effect: registers all tools)
from .core import mcp


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
