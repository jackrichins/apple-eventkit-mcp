"""Calendar tools for the MCP server."""

from datetime import datetime, timedelta
from typing import Optional
import zoneinfo

from mcp.server.fastmcp import FastMCP

from .eventkit_store import EventKitStore
from .permissions import PermissionError


def _get_current_datetime_context() -> dict:
    """Get current date/time context to help with scheduling.

    Returns a dict with current date, time, day of week, and upcoming days map.
    """
    # Get local timezone
    try:
        local_tz = datetime.now().astimezone().tzinfo
        tz_name = str(local_tz)
    except Exception:
        tz_name = "local"

    now = datetime.now()

    # Build map of upcoming days
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    upcoming_days = {}
    for i in range(1, 8):
        future_date = now + timedelta(days=i)
        day_name = day_names[future_date.weekday()]
        upcoming_days[day_name] = future_date.strftime("%Y-%m-%d")

    return {
        "current_date": now.strftime("%Y-%m-%d"),
        "current_time": now.strftime("%H:%M:%S"),
        "day_of_week": day_names[now.weekday()],
        "timezone": tz_name,
        "upcoming_days": upcoming_days,
    }


def register_calendar_tools(mcp: FastMCP, store: EventKitStore) -> None:
    """Register all calendar-related tools with the MCP server."""

    @mcp.tool()
    def calendar_list_calendars() -> dict:
        """List all available calendars.

        Returns a list of calendars that can be used for creating events.
        """
        try:
            calendars = store.get_calendars()
            return {
                "success": True,
                "calendars": calendars,
                "count": len(calendars),
            }
        except PermissionError as e:
            return {
                "success": False,
                "error": "permission_denied",
                "message": str(e),
            }
        except Exception as e:
            return {
                "success": False,
                "error": "unexpected_error",
                "message": str(e),
            }

    @mcp.tool()
    def calendar_list_events(
        start_date: str,
        end_date: str,
        calendar_name: Optional[str] = None,
        limit: int = 50
    ) -> dict:
        """List calendar events within a date range.

        Args:
            start_date: Start date in ISO 8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            end_date: End date in ISO 8601 format
            calendar_name: Filter to specific calendar (optional)
            limit: Maximum events to return (default: 50)
        """
        try:
            start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))

            events = store.get_events(
                start=start,
                end=end,
                calendar_name=calendar_name,
                limit=limit
            )

            return {
                "success": True,
                "today": _get_current_datetime_context(),
                "events": events,
                "count": len(events),
            }
        except PermissionError as e:
            return {
                "success": False,
                "error": "permission_denied",
                "message": str(e),
            }
        except ValueError as e:
            return {
                "success": False,
                "error": "invalid_date",
                "message": f"Invalid date format: {e}",
            }
        except Exception as e:
            return {
                "success": False,
                "error": "unexpected_error",
                "message": str(e),
            }

    @mcp.tool()
    def calendar_get_event(event_id: str) -> dict:
        """Get detailed information about a specific calendar event.

        Args:
            event_id: The event identifier (id or external_id from list results)
        """
        try:
            event = store.get_event_by_id(event_id)
            if event:
                return {
                    "success": True,
                    "event": event,
                }
            else:
                return {
                    "success": False,
                    "error": "not_found",
                    "message": f"Event not found: {event_id}",
                }
        except PermissionError as e:
            return {
                "success": False,
                "error": "permission_denied",
                "message": str(e),
            }
        except Exception as e:
            return {
                "success": False,
                "error": "unexpected_error",
                "message": str(e),
            }

    @mcp.tool()
    def calendar_search_events(
        query: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        tags: Optional[list[str]] = None,
        limit: int = 50
    ) -> dict:
        """Search events by text in title, location, or notes.

        Args:
            query: Search text to match
            start_date: Search range start (optional, defaults to 30 days ago)
            end_date: Search range end (optional, defaults to 90 days from now)
            tags: Filter by tags (optional)
            limit: Maximum events to return (default: 50)
        """
        try:
            start = None
            end = None
            if start_date:
                start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            if end_date:
                end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))

            events = store.search_events(
                query=query,
                start=start,
                end=end,
                tags=tags,
                limit=limit
            )

            return {
                "success": True,
                "events": events,
                "count": len(events),
                "query": query,
            }
        except PermissionError as e:
            return {
                "success": False,
                "error": "permission_denied",
                "message": str(e),
            }
        except ValueError as e:
            return {
                "success": False,
                "error": "invalid_date",
                "message": f"Invalid date format: {e}",
            }
        except Exception as e:
            return {
                "success": False,
                "error": "unexpected_error",
                "message": str(e),
            }

    @mcp.tool()
    def calendar_create_event(
        title: str,
        start_date: str,
        end_date: str,
        calendar_name: Optional[str] = None,
        location: Optional[str] = None,
        notes: Optional[str] = None,
        url: Optional[str] = None,
        is_all_day: bool = False,
        tags: Optional[list[str]] = None
    ) -> dict:
        """Create a new calendar event.

        Args:
            title: Event title
            start_date: Start date/time in ISO 8601 format
            end_date: End date/time in ISO 8601 format
            calendar_name: Target calendar (uses default if omitted)
            location: Event location (optional)
            notes: Event notes/description (optional)
            url: Associated URL (optional)
            is_all_day: All-day event flag (default: false)
            tags: Tags to apply (optional)
        """
        try:
            start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))

            event = store.create_event(
                title=title,
                start=start,
                end=end,
                calendar_name=calendar_name,
                location=location,
                notes=notes,
                url=url,
                is_all_day=is_all_day,
                tags=tags
            )

            return {
                "success": True,
                "event": event,
                "message": f"Event '{title}' created successfully",
            }
        except PermissionError as e:
            return {
                "success": False,
                "error": "permission_denied",
                "message": str(e),
            }
        except ValueError as e:
            return {
                "success": False,
                "error": "invalid_input",
                "message": str(e),
            }
        except Exception as e:
            return {
                "success": False,
                "error": "unexpected_error",
                "message": str(e),
            }

    @mcp.tool()
    def calendar_edit_event(
        event_id: str,
        span: str,
        title: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        location: Optional[str] = None,
        notes: Optional[str] = None,
        url: Optional[str] = None,
        tags: Optional[list[str]] = None
    ) -> dict:
        """Edit an existing calendar event.

        Args:
            event_id: The event identifier
            span: For recurring events - 'this_event' or 'future_events' (REQUIRED)
            title: New title (optional)
            start_date: New start date/time (optional)
            end_date: New end date/time (optional)
            location: New location (optional)
            notes: New notes (optional)
            url: New URL (optional)
            tags: New tags - replaces existing tags (optional)
        """
        if span not in ("this_event", "future_events"):
            return {
                "success": False,
                "error": "invalid_span",
                "message": "span must be 'this_event' or 'future_events'",
            }

        try:
            start = None
            end = None
            if start_date:
                start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            if end_date:
                end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))

            event = store.edit_event(
                event_id=event_id,
                span=span,
                title=title,
                start=start,
                end=end,
                location=location,
                notes=notes,
                url=url,
                tags=tags
            )

            return {
                "success": True,
                "event": event,
                "message": "Event updated successfully",
            }
        except PermissionError as e:
            return {
                "success": False,
                "error": "permission_denied",
                "message": str(e),
            }
        except ValueError as e:
            return {
                "success": False,
                "error": "not_found",
                "message": str(e),
            }
        except Exception as e:
            return {
                "success": False,
                "error": "unexpected_error",
                "message": str(e),
            }

    @mcp.tool()
    def calendar_delete_event(event_id: str, span: str) -> dict:
        """Delete a calendar event.

        Args:
            event_id: The event identifier
            span: For recurring events - 'this_event' or 'future_events' (REQUIRED)
        """
        if span not in ("this_event", "future_events"):
            return {
                "success": False,
                "error": "invalid_span",
                "message": "span must be 'this_event' or 'future_events'",
            }

        try:
            store.delete_event(event_id=event_id, span=span)

            return {
                "success": True,
                "message": "Event deleted successfully",
            }
        except PermissionError as e:
            return {
                "success": False,
                "error": "permission_denied",
                "message": str(e),
            }
        except ValueError as e:
            return {
                "success": False,
                "error": "not_found",
                "message": str(e),
            }
        except Exception as e:
            return {
                "success": False,
                "error": "unexpected_error",
                "message": str(e),
            }
