"""Permission handling for EventKit access on macOS."""

from enum import Enum
from typing import Callable

import EventKit


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
        "can_request": status == AuthorizationStatus.NOT_DETERMINED.value,
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
        if calendar["status"] == "denied":
            instructions.append(
                "Calendar access denied. Please enable in: "
                "System Settings > Privacy & Security > Calendar > "
                "Enable access for Terminal or Claude Desktop."
            )
        elif calendar["status"] == "restricted":
            instructions.append(
                "Calendar access is restricted by device policy."
            )
        else:
            instructions.append(
                "Calendar access not yet requested. "
                "Run the setup_permissions.py script from Terminal."
            )

    if not reminders["authorized"]:
        if reminders["status"] == "denied":
            instructions.append(
                "Reminders access denied. Please enable in: "
                "System Settings > Privacy & Security > Reminders > "
                "Enable access for Terminal or Claude Desktop."
            )
        elif reminders["status"] == "restricted":
            instructions.append(
                "Reminders access is restricted by device policy."
            )
        else:
            instructions.append(
                "Reminders access not yet requested. "
                "Run the setup_permissions.py script from Terminal."
            )

    return "\n".join(instructions)


def request_calendar_access(
    store: EventKit.EKEventStore,
    callback: Callable[[bool, object], None] | None = None
) -> None:
    """Request calendar access permission.

    Note: On macOS, this will only show a dialog if run from a context
    that can present UI (e.g., Terminal). When run as a subprocess of
    Claude Desktop, you may need to grant permissions manually.
    """
    def default_callback(granted: bool, error: object) -> None:
        pass

    store.requestAccessToEntityType_completion_(
        EventKit.EKEntityTypeEvent,
        callback or default_callback
    )


def request_reminders_access(
    store: EventKit.EKEventStore,
    callback: Callable[[bool, object], None] | None = None
) -> None:
    """Request reminders access permission."""
    def default_callback(granted: bool, error: object) -> None:
        pass

    store.requestAccessToEntityType_completion_(
        EventKit.EKEntityTypeReminder,
        callback or default_callback
    )


def request_all_permissions(store: EventKit.EKEventStore) -> None:
    """Request both Calendar and Reminders permissions.

    This triggers the system permission dialogs if permissions
    haven't been determined yet.
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
                f"Please enable access in System Settings > Privacy & Security > "
                f"{self.entity_type}. Add Claude Desktop or Terminal to allowed apps."
            )
        elif self.status == "restricted":
            return "Access is restricted by device policy."
        return "Please run the setup_permissions.py script to request permissions."


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
