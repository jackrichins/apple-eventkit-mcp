"""Apple EventKit MCP Server - Access Apple Calendar and Reminders via MCP."""

import sys

from mcp.server.fastmcp import FastMCP

from .eventkit_store import EventKitStore
from .calendar_tools import register_calendar_tools
from .reminder_tools import register_reminder_tools
from .permissions import check_permissions


# Initialize the FastMCP server
mcp = FastMCP(
    "Apple EventKit",
    dependencies=[
        "pyobjc-framework-EventKit",
        "pyobjc-framework-Cocoa",
    ]
)

# Initialize the EventKit store (singleton)
store = EventKitStore()


@mcp.tool()
def eventkit_check_permissions() -> dict:
    """Check Calendar and Reminders permission status.

    Returns the current authorization status for both Calendar and Reminders,
    along with instructions if permissions need to be granted.
    """
    return check_permissions()


# Register calendar tools
register_calendar_tools(mcp, store)

# Register reminder tools
register_reminder_tools(mcp, store)


def main():
    """Entry point for the MCP server."""
    # Attempt to request permissions on startup (may not trigger UI in subprocess)
    try:
        store.request_permissions()
    except Exception:
        # Ignore permission request errors on startup - tools will report them
        pass

    # Run the server
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
