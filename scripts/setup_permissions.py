#!/usr/bin/env python3
"""
Setup script to request Calendar and Reminders permissions on macOS.

Run this script from Terminal ONCE to trigger the macOS permission dialogs.
This is necessary because when the MCP server runs as a subprocess of
Claude Desktop, it may not be able to trigger the permission dialogs.

Usage:
    python scripts/setup_permissions.py

After running, you should see permission dialogs for Calendar and Reminders.
Grant access to both, then restart Claude Desktop.

If dialogs don't appear, you may need to manually grant permissions:
1. Open System Settings > Privacy & Security > Calendar
2. Add Terminal (or the app running this script) to the allowed list
3. Repeat for Reminders
"""

import sys
import time
import threading

try:
    import EventKit
except ImportError:
    print("Error: pyobjc-framework-EventKit is required.")
    print("Install it with: pip install pyobjc-framework-EventKit")
    sys.exit(1)


def get_status_name(status: int) -> str:
    """Convert authorization status to readable name."""
    status_map = {
        0: "Not Determined",
        1: "Restricted",
        2: "Denied",
        3: "Authorized",
        4: "Write Only (macOS 14+)",
    }
    return status_map.get(status, f"Unknown ({status})")


def check_current_status():
    """Display current permission status."""
    cal_status = EventKit.EKEventStore.authorizationStatusForEntityType_(
        EventKit.EKEntityTypeEvent
    )
    rem_status = EventKit.EKEventStore.authorizationStatusForEntityType_(
        EventKit.EKEntityTypeReminder
    )

    print("\n=== Current Permission Status ===")
    print(f"Calendar:  {get_status_name(cal_status)}")
    print(f"Reminders: {get_status_name(rem_status)}")

    return cal_status, rem_status


def request_permissions():
    """Request Calendar and Reminders permissions."""
    store = EventKit.EKEventStore.alloc().init()

    cal_status, rem_status = check_current_status()

    # Track results
    results = {"calendar": None, "reminders": None}
    completed = threading.Event()
    pending = {"count": 0}

    def calendar_callback(granted, error):
        results["calendar"] = granted
        if error:
            print(f"Calendar error: {error}")
        pending["count"] -= 1
        if pending["count"] == 0:
            completed.set()

    def reminders_callback(granted, error):
        results["reminders"] = granted
        if error:
            print(f"Reminders error: {error}")
        pending["count"] -= 1
        if pending["count"] == 0:
            completed.set()

    # Request Calendar permission if needed
    if cal_status == 0:  # Not Determined
        print("\nRequesting Calendar access...")
        print(">>> A system dialog should appear. Please click 'OK' to grant access.")
        pending["count"] += 1
        store.requestAccessToEntityType_completion_(
            EventKit.EKEntityTypeEvent,
            calendar_callback
        )
    elif cal_status == 3:  # Authorized
        print("\nCalendar: Already authorized")
        results["calendar"] = True
    else:
        print(f"\nCalendar: {get_status_name(cal_status)}")
        print("  To grant access, go to: System Settings > Privacy & Security > Calendar")
        results["calendar"] = False

    # Request Reminders permission if needed
    if rem_status == 0:  # Not Determined
        print("\nRequesting Reminders access...")
        print(">>> A system dialog should appear. Please click 'OK' to grant access.")
        pending["count"] += 1
        store.requestAccessToEntityType_completion_(
            EventKit.EKEntityTypeReminder,
            reminders_callback
        )
    elif rem_status == 3:  # Authorized
        print("\nReminders: Already authorized")
        results["reminders"] = True
    else:
        print(f"\nReminders: {get_status_name(rem_status)}")
        print("  To grant access, go to: System Settings > Privacy & Security > Reminders")
        results["reminders"] = False

    # Wait for callbacks if we requested any
    if pending["count"] > 0:
        print("\nWaiting for permission dialogs...")
        print("(This may take up to 60 seconds if dialogs don't appear)")

        # Wait for completion or timeout
        completed.wait(timeout=60)

        # Give a moment for the system to update
        time.sleep(1)

    return results


def main():
    print("=" * 60)
    print("Apple EventKit MCP Server - Permission Setup")
    print("=" * 60)
    print()
    print("This script will request Calendar and Reminders permissions.")
    print("You should see system dialogs asking for permission.")
    print()

    results = request_permissions()

    # Check final status
    print("\n" + "=" * 60)
    final_cal, final_rem = check_current_status()
    print("=" * 60)

    if final_cal == 3 and final_rem == 3:
        print("\n✓ SUCCESS: All permissions granted!")
        print("\nYou can now use the Apple EventKit MCP server with Claude Desktop.")
        print("Restart Claude Desktop if it's currently running.")
    else:
        print("\n⚠ Some permissions are missing.")
        print("\nTo manually grant permissions:")
        print("1. Open System Settings")
        print("2. Go to Privacy & Security > Calendar")
        print("3. Enable access for Terminal (or your terminal app)")
        print("4. Go to Privacy & Security > Reminders")
        print("5. Enable access for Terminal (or your terminal app)")
        print("\nFor Claude Desktop, you may also need to grant access to:")
        print("  - Claude Desktop app itself")
        print("  - Python interpreter used by the MCP server")
        print("\nSee the README for more detailed instructions.")


if __name__ == "__main__":
    main()
