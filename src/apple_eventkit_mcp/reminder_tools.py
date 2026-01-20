"""Reminder tools for the MCP server."""

from datetime import datetime
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .eventkit_store import EventKitStore
from .permissions import PermissionError


def register_reminder_tools(mcp: FastMCP, store: EventKitStore) -> None:
    """Register all reminder-related tools with the MCP server."""

    @mcp.tool()
    def reminders_list_lists() -> dict:
        """List all reminder lists.

        Returns a list of reminder lists that can be used for creating reminders.
        """
        try:
            lists = store.get_reminder_lists()
            return {
                "success": True,
                "lists": lists,
                "count": len(lists),
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
    def reminders_list(
        list_name: Optional[str] = None,
        include_completed: bool = False,
        due_before: Optional[str] = None,
        limit: int = 100
    ) -> dict:
        """List reminders with optional filters.

        Args:
            list_name: Filter to specific list (optional)
            include_completed: Include completed reminders (default: false)
            due_before: Filter by due date - ISO 8601 format (optional)
            limit: Maximum reminders to return (default: 100)
        """
        try:
            due_date = None
            if due_before:
                due_date = datetime.fromisoformat(due_before.replace("Z", "+00:00"))

            reminders = store.get_reminders(
                list_name=list_name,
                include_completed=include_completed,
                due_before=due_date,
                limit=limit
            )

            return {
                "success": True,
                "reminders": reminders,
                "count": len(reminders),
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
    def reminders_get(reminder_id: str) -> dict:
        """Get detailed information about a specific reminder.

        Args:
            reminder_id: The reminder identifier (id or external_id from list results)
        """
        try:
            reminder = store.get_reminder_by_id(reminder_id)
            if reminder:
                return {
                    "success": True,
                    "reminder": reminder,
                }
            else:
                return {
                    "success": False,
                    "error": "not_found",
                    "message": f"Reminder not found: {reminder_id}",
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
    def reminders_search(
        query: str,
        tags: Optional[list[str]] = None,
        include_completed: bool = False,
        limit: int = 50
    ) -> dict:
        """Search reminders by text in title or notes.

        Args:
            query: Search text to match
            tags: Filter by tags (optional)
            include_completed: Include completed reminders (default: false)
            limit: Maximum reminders to return (default: 50)
        """
        try:
            reminders = store.search_reminders(
                query=query,
                tags=tags,
                include_completed=include_completed,
                limit=limit
            )

            return {
                "success": True,
                "reminders": reminders,
                "count": len(reminders),
                "query": query,
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
    def reminders_create(
        title: str,
        list_name: Optional[str] = None,
        notes: Optional[str] = None,
        due_date: Optional[str] = None,
        priority: Optional[str] = None,
        tags: Optional[list[str]] = None
    ) -> dict:
        """Create a new reminder.

        Args:
            title: Reminder title
            list_name: Target list (uses default if omitted)
            notes: Additional notes (optional)
            due_date: Due date in ISO 8601 format (optional)
            priority: 'none', 'low', 'medium', or 'high' (optional)
            tags: Tags to apply (optional)
        """
        try:
            due = None
            if due_date:
                due = datetime.fromisoformat(due_date.replace("Z", "+00:00"))

            if priority and priority not in ("none", "low", "medium", "high"):
                return {
                    "success": False,
                    "error": "invalid_priority",
                    "message": "priority must be 'none', 'low', 'medium', or 'high'",
                }

            reminder = store.create_reminder(
                title=title,
                list_name=list_name,
                notes=notes,
                due_date=due,
                priority=priority,
                tags=tags
            )

            return {
                "success": True,
                "reminder": reminder,
                "message": f"Reminder '{title}' created successfully",
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
    def reminders_edit(
        reminder_id: str,
        title: Optional[str] = None,
        notes: Optional[str] = None,
        due_date: Optional[str] = None,
        priority: Optional[str] = None,
        completed: Optional[bool] = None,
        tags: Optional[list[str]] = None
    ) -> dict:
        """Edit an existing reminder.

        Args:
            reminder_id: The reminder identifier
            title: New title (optional)
            notes: New notes (optional)
            due_date: New due date in ISO 8601 format (optional)
            priority: New priority - 'none', 'low', 'medium', or 'high' (optional)
            completed: Mark as completed/incomplete (optional)
            tags: New tags - replaces existing tags (optional)
        """
        try:
            due = None
            if due_date:
                due = datetime.fromisoformat(due_date.replace("Z", "+00:00"))

            if priority and priority not in ("none", "low", "medium", "high"):
                return {
                    "success": False,
                    "error": "invalid_priority",
                    "message": "priority must be 'none', 'low', 'medium', or 'high'",
                }

            reminder = store.edit_reminder(
                reminder_id=reminder_id,
                title=title,
                notes=notes,
                due_date=due,
                priority=priority,
                completed=completed,
                tags=tags
            )

            return {
                "success": True,
                "reminder": reminder,
                "message": "Reminder updated successfully",
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
    def reminders_complete(reminder_id: str) -> dict:
        """Mark a reminder as completed.

        Args:
            reminder_id: The reminder identifier
        """
        try:
            reminder = store.complete_reminder(reminder_id)

            return {
                "success": True,
                "reminder": reminder,
                "message": "Reminder marked as completed",
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
    def reminders_delete(reminder_id: str) -> dict:
        """Delete a reminder.

        Args:
            reminder_id: The reminder identifier
        """
        try:
            store.delete_reminder(reminder_id)

            return {
                "success": True,
                "message": "Reminder deleted successfully",
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
