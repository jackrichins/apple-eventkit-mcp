"""Permission handling for EventKit access on macOS."""

import platform
from enum import Enum
from typing import Callable

import EventKit


def _macos_version() -> tuple[int, ...]:
    """Return the macOS version as a tuple, e.g. (14, 5, 0)."""
    return tuple(int(x) for x in platform.mac_ver()[0].split("."))


class AuthorizationStatus(Enum):
    """EventKit authorization status values."""
    NOT_DETERMINED = 0
    RESTRICTED = 1
    DENIED = 2
    AUTHORIZED = 3
    WRITE_ONLY = 4  # macOS 14+ / iOS 17+


def get_status_name(status: int) -> str:
    """Convert authorization status int to readable name."""
    try:
        return AuthorizationStatus(status).name.lower()
    except ValueError:
        return "unknown"


def check_calendar_permission() -> dict:
    """Check current calendar permission status."""
    status = EventKit.EKEventStore.authorizationStatusForEntityType_(
        EventKit.EKEntityTypeEvent
    )
    return {
        "status": get_status_name(status),
        "authorized": status == AuthorizationStatus.AUTHORIZED.value,
        "can_request": status in (
            AuthorizationStatus.NOT_DETERMINED.value,
            AuthorizationStatus.WRITE_ONLY.value,
        ),
    }


def check_reminders_permission() -> dict:
    """Check current reminders permission status."""
    status = EventKit.EKEventStore.authorizationStatusForEntityType_(
        EventKit.EKEntityTypeReminder
    )
    return {
        "status": get_status_name(status),
        "authorized": status == AuthorizationStatus.AUTHORIZED.value,
        "can_request": status == AuthorizationStatus.NOT_DETERMINED.value,
    }


def check_permissions() -> dict:
    """Check both Calendar and Reminders permission status."""
    calendar = check_calendar_permission()
    reminders = check_reminders_permission()

    result = {
        "calendar": calendar,
        "reminders": reminders,
        "all_authorized": calendar["authorized"] and reminders["authorized"],
    }

    # Add instructions if permissions are missing
    if not result["all_authorized"]:
        result["instructions"] = get_permission_instructions(calendar, reminders)

    return result


def get_permission_instructions(calendar: dict, reminders: dict) -> str:
    """Generate user-friendly instructions for granting permissions."""
    instructions = []

    if not calendar["authorized"]:
        if calendar["status"] == "write_only":
            instructions.append(
                "Calendar has write-only access — full access is required. "
                "Run: uv run python scripts/setup_permissions.py from Terminal.app"
            )
        elif calendar["status"] == "denied":
            instructions.append(
                "Calendar access denied. "
                "Run: uv run python scripts/setup_permissions.py from Terminal.app"
            )
        elif calendar["status"] == "restricted":
            instructions.append(
                "Calendar access is restricted by device policy."
            )
        else:
            instructions.append(
                "Calendar access not yet granted. "
                "Run: uv run python scripts/setup_permissions.py from Terminal.app "
                "(not your IDE's integrated terminal). The permission is granted to "
                "the 'uv' binary and will work from any MCP client."
            )

    if not reminders["authorized"]:
        if reminders["status"] == "denied":
            instructions.append(
                "Reminders access denied. "
                "Run: uv run python scripts/setup_permissions.py from Terminal.app"
            )
        elif reminders["status"] == "restricted":
            instructions.append(
                "Reminders access is restricted by device policy."
            )
        else:
            instructions.append(
                "Reminders access not yet granted. "
                "Run: uv run python scripts/setup_permissions.py from Terminal.app"
            )

    return "\n".join(instructions)


def request_calendar_access(
    store: EventKit.EKEventStore,
    callback: Callable[[bool, object], None] | None = None
) -> None:
    """Request calendar access permission.

    On macOS 14+, uses requestFullAccessToEventsWithCompletion_ instead of
    the deprecated requestAccessToEntityType_completion_, which silently
    fails to show a permission dialog from non-Apple apps like VS Code.

    Note: This will only show a dialog when run from a context that can
    present UI (e.g., Terminal.app). When run as a subprocess of an IDE,
    the request may silently fail. Use setup_permissions.py from
    Terminal.app to grant permissions.
    """
    def default_callback(granted: bool, error: object) -> None:
        pass

    cb = callback or default_callback

    if _macos_version() >= (14, 0):
        store.requestFullAccessToEventsWithCompletion_(cb)
    else:
        store.requestAccessToEntityType_completion_(
            EventKit.EKEntityTypeEvent, cb
        )


def request_reminders_access(
    store: EventKit.EKEventStore,
    callback: Callable[[bool, object], None] | None = None
) -> None:
    """Request reminders access permission.

    On macOS 14+, uses requestFullAccessToRemindersWithCompletion_ instead
    of the deprecated requestAccessToEntityType_completion_.
    """
    def default_callback(granted: bool, error: object) -> None:
        pass

    cb = callback or default_callback

    if _macos_version() >= (14, 0):
        store.requestFullAccessToRemindersWithCompletion_(cb)
    else:
        store.requestAccessToEntityType_completion_(
            EventKit.EKEntityTypeReminder, cb
        )


def request_all_permissions(store: EventKit.EKEventStore) -> None:
    """Request both Calendar and Reminders permissions (best-effort).

    This is called at server startup as a best-effort attempt. It will
    only succeed if the process can present TCC dialogs (e.g., when run
    from Terminal.app). When running as an MCP subprocess of VS Code or
    similar IDEs, this will silently fail — users must run
    setup_permissions.py from Terminal.app instead.
    """
    calendar = check_calendar_permission()
    reminders = check_reminders_permission()

    if calendar["can_request"]:
        request_calendar_access(store)

    if reminders["can_request"]:
        request_reminders_access(store)


class PermissionError(Exception):
    """Raised when EventKit permissions are insufficient."""

    def __init__(self, entity_type: str, status: str):
        self.entity_type = entity_type
        self.status = status
        instructions = self._get_instructions()
        super().__init__(f"{entity_type} access {status}. {instructions}")

    def _get_instructions(self) -> str:
        if self.status == "denied":
            return (
                "Please run: uv run python scripts/setup_permissions.py "
                "from Terminal.app (not your IDE's terminal)."
            )
        elif self.status == "restricted":
            return "Access is restricted by device policy."
        return (
            "Please run: uv run python scripts/setup_permissions.py "
            "from Terminal.app (not your IDE's terminal). "
            "The permission is granted to the 'uv' binary and will "
            "work from any MCP client."
        )


def require_calendar_permission() -> None:
    """Raise PermissionError if calendar access is not authorized."""
    perm = check_calendar_permission()
    if not perm["authorized"]:
        raise PermissionError("Calendar", perm["status"])


def require_reminders_permission() -> None:
    """Raise PermissionError if reminders access is not authorized."""
    perm = check_reminders_permission()
    if not perm["authorized"]:
        raise PermissionError("Reminders", perm["status"])
