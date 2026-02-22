#!/usr/bin/env python3
"""
Setup script to request Calendar and Reminders permissions on macOS.

This script triggers the macOS permission dialogs for Calendar and
Reminders. On macOS 14+, it uses the newer full-access APIs.

macOS TCC (Transparency, Consent, and Control) requires BOTH the direct
binary (uv/python) AND the responsible app (VS Code, Claude Desktop,
etc.) to have permission. Some apps (VS Code, Cursor, and other
Electron-based IDEs) cannot present Calendar permission dialogs, so
this script must be run from Terminal.app. After the dialog grants
permission to the uv binary, the script automatically copies the
permission to the IDE via the TCC database (if the IDE already has
Reminders access).

Usage (from Terminal.app):
    cd /path/to/apple-eventkit-mcp
    uv run python scripts/setup_permissions.py
"""

import os
import platform
import sqlite3
import sys
import time

try:
    import EventKit
    from Cocoa import NSApplication, NSDate
except ImportError:
    print("Error: pyobjc-framework-EventKit and pyobjc-framework-Cocoa are required.")
    print("Install with: pip install pyobjc-framework-EventKit pyobjc-framework-Cocoa")
    sys.exit(1)

TCC_DB = os.path.expanduser("~/Library/Application Support/com.apple.TCC/TCC.db")


def _macos_version() -> tuple[int, ...]:
    """Return the macOS version as a tuple, e.g. (14, 5, 0)."""
    return tuple(int(x) for x in platform.mac_ver()[0].split("."))


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


def get_cal_status() -> int:
    return EventKit.EKEventStore.authorizationStatusForEntityType_(
        EventKit.EKEntityTypeEvent
    )


def get_rem_status() -> int:
    return EventKit.EKEventStore.authorizationStatusForEntityType_(
        EventKit.EKEntityTypeReminder
    )


def check_current_status():
    """Display current permission status."""
    cal_status = get_cal_status()
    rem_status = get_rem_status()

    print("\n=== Current Permission Status ===")
    print(f"Calendar:  {get_status_name(cal_status)}")
    print(f"Reminders: {get_status_name(rem_status)}")

    return cal_status, rem_status


# Known MCP client bundle IDs
KNOWN_MCP_CLIENTS = [
    "com.microsoft.VSCode",
    "com.microsoft.VSCodeInsiders",
    "com.todesktop.230313mzl4w4u92",  # Cursor
    "com.anthropic.claude",
    "com.codeium.windsurf",
]


def _tcc_has_permission(client: str, service: str) -> bool:
    """Check if a client has a specific TCC permission."""
    try:
        with sqlite3.connect(TCC_DB) as conn:
            cursor = conn.execute(
                "SELECT auth_value FROM access WHERE service=? AND client=?",
                (service, client),
            )
            row = cursor.fetchone()
            return row is not None and row[0] == 2  # auth_value 2 = Authorized
    except Exception:
        return False


def _tcc_copy_permission(client: str, from_service: str, to_service: str) -> bool:
    """Copy a TCC permission entry from one service to another.

    This is used to grant Calendar permission to an app that already has
    Reminders permission, by copying the TCC database row. This works
    because both services use the same code signing requirement for the
    same app.

    Returns True if the copy succeeded.
    """
    try:
        with sqlite3.connect(TCC_DB) as conn:
            # Get column names dynamically to be schema-agnostic
            cursor = conn.execute("PRAGMA table_info(access)")
            columns = [row[1] for row in cursor.fetchall()]

            non_service_cols = [c for c in columns if c != "service"]
            col_list = ", ".join(non_service_cols)

            conn.execute(
                f"INSERT OR REPLACE INTO access (service, {col_list}) "
                f"SELECT ?, {col_list} FROM access "
                f"WHERE service=? AND client=?",
                (to_service, from_service, client),
            )
            conn.commit()
        return True
    except Exception as e:
        print(f"  Warning: Could not update TCC database: {e}")
        return False


def try_grant_via_tcc_db(service: str = "kTCCServiceCalendar") -> list[str]:
    """Grant Calendar permission to all known MCP clients that need it.

    macOS TCC requires both the direct binary (uv/python) AND the
    responsible app (e.g., VS Code) to have permission. IDEs cannot
    trigger the Calendar permission dialog, but if they already have
    Reminders permission, we can copy that TCC entry to Calendar.

    Checks ALL known MCP clients (not just the current parent app),
    so this works correctly when run from Terminal.app.

    Returns a list of apps that were granted permission.
    """
    granted = []

    for bundle_id in KNOWN_MCP_CLIENTS:
        if _tcc_has_permission(bundle_id, service):
            continue  # Already has Calendar permission

        if _tcc_has_permission(bundle_id, "kTCCServiceReminders"):
            print(f"\n  {bundle_id} has Reminders but not Calendar permission.")
            print(f"  Copying Reminders TCC entry to Calendar...")
            if _tcc_copy_permission(bundle_id, "kTCCServiceReminders", service):
                print(f"  Granted Calendar permission to {bundle_id}.")
                granted.append(bundle_id)

    return granted


def try_request_permission(store, entity_type, macos_ver):
    """Attempt to request a permission programmatically.

    Initializes NSApplication, makes the request, and pumps the event
    loop briefly. Returns a dict with:
      - "callback_fired": True if the completion handler was called
      - "granted": True if access was granted
    """
    result = {"callback_fired": False, "granted": False}

    def callback(granted, error):
        result["callback_fired"] = True
        result["granted"] = granted
        if error:
            print(f"  {entity_type} error: {error}")

    # Initialize NSApplication so the process can potentially show dialogs.
    # This connects to the window server, which is necessary for TCC dialogs.
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(0)  # NSApplicationActivationPolicyRegular
    app.activateIgnoringOtherApps_(True)

    if entity_type == "calendar":
        if macos_ver >= (14, 0):
            store.requestFullAccessToEventsWithCompletion_(callback)
        else:
            store.requestAccessToEntityType_completion_(
                EventKit.EKEntityTypeEvent, callback
            )
    else:
        if macos_ver >= (14, 0):
            store.requestFullAccessToRemindersWithCompletion_(callback)
        else:
            store.requestAccessToEntityType_completion_(
                EventKit.EKEntityTypeReminder, callback
            )

    # Pump the event loop briefly to allow the dialog to appear.
    # From Terminal.app this succeeds quickly; from IDEs it always fails,
    # so we keep the timeout short to avoid unnecessary waiting.
    deadline = time.time() + 3
    while not result["callback_fired"] and time.time() < deadline:
        event = app.nextEventMatchingMask_untilDate_inMode_dequeue_(
            0xFFFFFFFFFFFF,  # NSEventMaskAny
            NSDate.dateWithTimeIntervalSinceNow_(0.5),
            "kCFRunLoopDefaultMode",
            True,
        )
        if event:
            app.sendEvent_(event)
        app.updateWindows()

    return result


def request_permissions():
    """Request Calendar and Reminders permissions."""
    store = EventKit.EKEventStore.alloc().init()
    macos_ver = _macos_version()

    cal_status, rem_status = check_current_status()

    results = {"calendar": None, "reminders": None}
    needs_terminal = []

    # --- Calendar ---
    if cal_status in (0, 4):  # Not Determined or Write Only
        if cal_status == 4:
            print("\nCalendar has write-only access — requesting full access...")
        else:
            print("\nRequesting Calendar full access...")

        req = try_request_permission(store, "calendar", macos_ver)

        if req["callback_fired"] and req["granted"]:
            print("  Calendar: Granted!")
            results["calendar"] = True
        elif req["callback_fired"] and not req["granted"]:
            # Callback fired but not granted, and status is still Not Determined.
            # This means the app cannot present the TCC dialog.
            new_status = get_cal_status()
            if new_status == 3:
                print("  Calendar: Granted!")
                results["calendar"] = True
            else:
                needs_terminal.append("Calendar")
                results["calendar"] = False
        else:
            # Callback never fired — dialog could not be presented
            needs_terminal.append("Calendar")
            results["calendar"] = False

    elif cal_status == 3:
        print("\nCalendar: Already authorized (full access)")
        results["calendar"] = True
    else:
        print(f"\nCalendar: {get_status_name(cal_status)}")
        needs_terminal.append("Calendar")
        results["calendar"] = False

    # --- Reminders ---
    if rem_status == 0:  # Not Determined
        print("\nRequesting Reminders access...")

        req = try_request_permission(store, "reminders", macos_ver)

        if req["callback_fired"] and req["granted"]:
            print("  Reminders: Granted!")
            results["reminders"] = True
        elif req["callback_fired"] and not req["granted"]:
            new_status = get_rem_status()
            if new_status == 3:
                print("  Reminders: Granted!")
                results["reminders"] = True
            else:
                needs_terminal.append("Reminders")
                results["reminders"] = False
        else:
            needs_terminal.append("Reminders")
            results["reminders"] = False

    elif rem_status == 3:
        print("\nReminders: Already authorized")
        results["reminders"] = True
    else:
        print(f"\nReminders: {get_status_name(rem_status)}")
        needs_terminal.append("Reminders")
        results["reminders"] = False

    results["needs_terminal"] = needs_terminal
    return results


def main():
    print("=" * 60)
    print("Apple EventKit MCP Server - Permission Setup")
    print("=" * 60)

    macos_ver = _macos_version()
    print(f"\nDetected macOS version: {'.'.join(str(x) for x in macos_ver)}")

    if macos_ver >= (14, 0):
        print("Using macOS 14+ full-access permission APIs.")

    results = request_permissions()

    # Check final status
    print("\n" + "=" * 60)
    final_cal, final_rem = check_current_status()
    print("=" * 60)

    if final_cal == 3 and final_rem == 3:
        print("\n✓ SUCCESS: All permissions granted!")

        # Also grant Calendar to the responsible app (e.g., VS Code) if needed.
        # macOS TCC requires both the binary AND the responsible app to have
        # permission. The dialog grants to the binary, but the responsible app
        # also needs an entry.
        tcc_granted = try_grant_via_tcc_db()
        if tcc_granted:
            apps = ", ".join(tcc_granted)
            print(f"\nAlso granted Calendar access to: {apps}")
            print("(Required because macOS checks both the binary and the parent app)")

        print("\nYou can now use the Apple EventKit MCP server.")
        print("Restart your MCP client if it's currently running.")
    elif results.get("needs_terminal"):
        failed = " and ".join(results["needs_terminal"])
        print(f"\n⚠ Could not show permission dialog for: {failed}")
        print()
        print("Some apps (VS Code, Cursor, and other IDEs) cannot present")
        print("macOS Calendar permission dialogs from their integrated terminals.")
        print()
        print("To fix this, run this script from Terminal.app:")
        print()
        print("  1. Open Terminal.app (not your IDE's terminal)")
        print("  2. Run:")
        print(f"     cd {_get_project_dir()}")
        print("     uv run python scripts/setup_permissions.py")
        print("  3. Grant access when the dialog appears")
        print()
        print("The script will automatically grant Calendar permission to")
        print("your IDE (e.g., VS Code) if it already has Reminders access.")
    else:
        print("\n⚠ Some permissions are missing.")
        print("Please run this script from Terminal.app.")


def _get_project_dir() -> str:
    """Best-effort guess at the project directory."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(script_dir)


if __name__ == "__main__":
    main()
