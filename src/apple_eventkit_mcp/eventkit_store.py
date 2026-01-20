"""Thread-safe wrapper for EKEventStore operations."""

import threading
from datetime import datetime, timedelta
from typing import Optional

import EventKit
from Cocoa import NSDate, NSDateComponents, NSCalendar, NSURL

from .tags import decode_tags, merge_notes_with_tags
from .permissions import (
    require_calendar_permission,
    require_reminders_permission,
    request_all_permissions,
)

# Attribution added to items created via MCP
CREATED_BY_NOTE = "Created by Claude Desktop"


class EventKitStore:
    """Thread-safe wrapper for EKEventStore operations."""

    def __init__(self):
        self._store = EventKit.EKEventStore.alloc().init()
        self._lock = threading.Lock()

    def request_permissions(self) -> None:
        """Request permissions on startup."""
        request_all_permissions(self._store)

    # -------------------------------------------------------------------------
    # Calendar Operations
    # -------------------------------------------------------------------------

    def get_calendars(self) -> list[dict]:
        """Get all calendars for events."""
        require_calendar_permission()
        with self._lock:
            calendars = self._store.calendarsForEntityType_(
                EventKit.EKEntityTypeEvent
            )
            return [self._calendar_to_dict(c) for c in (calendars or [])]

    def get_default_calendar(self) -> Optional[EventKit.EKCalendar]:
        """Get the default calendar for new events."""
        with self._lock:
            return self._store.defaultCalendarForNewEvents()

    def find_calendar_by_name(
        self, name: str
    ) -> Optional[EventKit.EKCalendar]:
        """Find a calendar by name (case-insensitive)."""
        with self._lock:
            calendars = self._store.calendarsForEntityType_(
                EventKit.EKEntityTypeEvent
            )
            for cal in (calendars or []):
                if cal.title().lower() == name.lower():
                    return cal
            return None

    def get_events(
        self,
        start: datetime,
        end: datetime,
        calendar_name: Optional[str] = None,
        limit: int = 50
    ) -> list[dict]:
        """Fetch events in date range."""
        require_calendar_permission()
        with self._lock:
            start_ns = self._datetime_to_nsdate(start)
            end_ns = self._datetime_to_nsdate(end)

            if calendar_name:
                cal = self._find_calendar_unlocked(calendar_name)
                calendars = [cal] if cal else []
            else:
                calendars = list(
                    self._store.calendarsForEntityType_(EventKit.EKEntityTypeEvent)
                    or []
                )

            if not calendars:
                return []

            predicate = self._store.predicateForEventsWithStartDate_endDate_calendars_(
                start_ns, end_ns, calendars
            )

            events = self._store.eventsMatchingPredicate_(predicate) or []
            # Sort by start date and apply limit
            sorted_events = sorted(events, key=lambda e: e.startDate().timeIntervalSince1970())
            return [self._event_to_dict(e) for e in sorted_events[:limit]]

    def get_event_by_id(self, event_id: str) -> Optional[dict]:
        """Get a specific event by its external identifier."""
        require_calendar_permission()
        with self._lock:
            event = self._store.calendarItemWithIdentifier_(event_id)
            if event and isinstance(event, EventKit.EKEvent):
                return self._event_to_dict(event)
            # Try searching by external identifier
            event = self._find_event_by_external_id(event_id)
            if event:
                return self._event_to_dict(event)
            return None

    def create_event(
        self,
        title: str,
        start: datetime,
        end: datetime,
        calendar_name: Optional[str] = None,
        location: Optional[str] = None,
        notes: Optional[str] = None,
        url: Optional[str] = None,
        is_all_day: bool = False,
        tags: Optional[list[str]] = None
    ) -> dict:
        """Create a new calendar event."""
        require_calendar_permission()
        with self._lock:
            event = EventKit.EKEvent.eventWithEventStore_(self._store)
            event.setTitle_(title)
            event.setStartDate_(self._datetime_to_nsdate(start))
            event.setEndDate_(self._datetime_to_nsdate(end))
            event.setAllDay_(is_all_day)

            # Set calendar
            if calendar_name:
                cal = self._find_calendar_unlocked(calendar_name)
                if cal:
                    event.setCalendar_(cal)
                else:
                    event.setCalendar_(self._store.defaultCalendarForNewEvents())
            else:
                event.setCalendar_(self._store.defaultCalendarForNewEvents())

            # Optional fields
            if location:
                event.setLocation_(location)
            if url:
                event.setURL_(NSURL.URLWithString_(url))

            # Handle notes with tags, prepending attribution
            notes_with_attribution = f"{CREATED_BY_NOTE}\n\n{notes}" if notes else CREATED_BY_NOTE
            final_notes = merge_notes_with_tags(notes_with_attribution, tags)
            event.setNotes_(final_notes)

            # Save
            success, error = self._store.saveEvent_span_error_(
                event, EventKit.EKSpanThisEvent, None
            )

            if not success:
                raise Exception(f"Failed to save event: {error}")

            return self._event_to_dict(event)

    def edit_event(
        self,
        event_id: str,
        span: str = "this_event",
        title: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        location: Optional[str] = None,
        notes: Optional[str] = None,
        url: Optional[str] = None,
        tags: Optional[list[str]] = None
    ) -> dict:
        """Edit an existing event."""
        require_calendar_permission()
        with self._lock:
            event = self._find_event_by_any_id(event_id)
            if not event:
                raise ValueError(f"Event not found: {event_id}")

            if title is not None:
                event.setTitle_(title)
            if start is not None:
                event.setStartDate_(self._datetime_to_nsdate(start))
            if end is not None:
                event.setEndDate_(self._datetime_to_nsdate(end))
            if location is not None:
                event.setLocation_(location)
            if url is not None:
                if url:
                    event.setURL_(NSURL.URLWithString_(url))
                else:
                    event.setURL_(None)

            # Handle notes with tags
            if notes is not None or tags is not None:
                current_notes = event.notes() or ""
                clean_notes, existing_tags = decode_tags(current_notes)

                if notes is not None:
                    clean_notes = notes
                if tags is not None:
                    existing_tags = tags

                final_notes = merge_notes_with_tags(clean_notes, existing_tags)
                event.setNotes_(final_notes if final_notes else None)

            # Determine span
            ek_span = (
                EventKit.EKSpanFutureEvents
                if span == "future_events"
                else EventKit.EKSpanThisEvent
            )

            success, error = self._store.saveEvent_span_error_(event, ek_span, None)

            if not success:
                raise Exception(f"Failed to update event: {error}")

            return self._event_to_dict(event)

    def delete_event(self, event_id: str, span: str = "this_event") -> bool:
        """Delete an event."""
        require_calendar_permission()
        with self._lock:
            event = self._find_event_by_any_id(event_id)
            if not event:
                raise ValueError(f"Event not found: {event_id}")

            ek_span = (
                EventKit.EKSpanFutureEvents
                if span == "future_events"
                else EventKit.EKSpanThisEvent
            )

            success, error = self._store.removeEvent_span_error_(event, ek_span, None)

            if not success:
                raise Exception(f"Failed to delete event: {error}")

            return True

    def search_events(
        self,
        query: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        tags: Optional[list[str]] = None,
        limit: int = 50
    ) -> list[dict]:
        """Search events by text in title, location, or notes."""
        require_calendar_permission()

        # Default to searching past 30 days to future 90 days
        if start is None:
            start = datetime.now() - timedelta(days=30)
        if end is None:
            end = datetime.now() + timedelta(days=90)

        events = self.get_events(start, end, limit=1000)  # Get more for filtering

        query_lower = query.lower()
        results = []

        for event in events:
            # Search in title, location, and notes
            searchable = " ".join([
                event.get("title", "") or "",
                event.get("location", "") or "",
                event.get("notes", "") or "",
            ]).lower()

            if query_lower in searchable:
                results.append(event)

        # Filter by tags if specified
        if tags:
            from .tags import filter_by_tags
            results = filter_by_tags(results, tags)

        return results[:limit]

    # -------------------------------------------------------------------------
    # Reminder Operations
    # -------------------------------------------------------------------------

    def get_reminder_lists(self) -> list[dict]:
        """Get all reminder lists."""
        require_reminders_permission()
        with self._lock:
            calendars = self._store.calendarsForEntityType_(
                EventKit.EKEntityTypeReminder
            )
            return [self._calendar_to_dict(c) for c in (calendars or [])]

    def get_default_reminder_list(self) -> Optional[EventKit.EKCalendar]:
        """Get the default reminder list."""
        with self._lock:
            return self._store.defaultCalendarForNewReminders()

    def find_reminder_list_by_name(
        self, name: str
    ) -> Optional[EventKit.EKCalendar]:
        """Find a reminder list by name (case-insensitive)."""
        with self._lock:
            calendars = self._store.calendarsForEntityType_(
                EventKit.EKEntityTypeReminder
            )
            for cal in (calendars or []):
                if cal.title().lower() == name.lower():
                    return cal
            return None

    def get_reminders(
        self,
        list_name: Optional[str] = None,
        include_completed: bool = False,
        due_before: Optional[datetime] = None,
        limit: int = 100
    ) -> list[dict]:
        """Fetch reminders with optional filters."""
        require_reminders_permission()

        with self._lock:
            if list_name:
                cal = self._find_reminder_list_unlocked(list_name)
                calendars = [cal] if cal else []
            else:
                calendars = list(
                    self._store.calendarsForEntityType_(EventKit.EKEntityTypeReminder)
                    or []
                )

            if not calendars:
                return []

            # Create predicate
            if include_completed:
                predicate = self._store.predicateForRemindersInCalendars_(calendars)
            else:
                predicate = self._store.predicateForIncompleteRemindersWithDueDateStarting_ending_calendars_(
                    None,
                    self._datetime_to_nsdate(due_before) if due_before else None,
                    calendars
                )

            # Fetch reminders synchronously using semaphore
            import threading
            reminders_result = []
            semaphore = threading.Semaphore(0)

            def fetch_callback(reminders):
                nonlocal reminders_result
                reminders_result = list(reminders) if reminders else []
                semaphore.release()

            self._store.fetchRemindersMatchingPredicate_completion_(
                predicate, fetch_callback
            )

            # Wait for completion (with timeout)
            semaphore.acquire(timeout=30)

            results = [self._reminder_to_dict(r) for r in reminders_result]

            # Sort by due date (None dates at end)
            results.sort(key=lambda r: r.get("due_date") or "9999-12-31")

            return results[:limit]

    def get_reminder_by_id(self, reminder_id: str) -> Optional[dict]:
        """Get a specific reminder by its identifier."""
        require_reminders_permission()
        with self._lock:
            item = self._store.calendarItemWithIdentifier_(reminder_id)
            if item and isinstance(item, EventKit.EKReminder):
                return self._reminder_to_dict(item)
            # Try external identifier
            item = self._find_reminder_by_external_id(reminder_id)
            if item:
                return self._reminder_to_dict(item)
            return None

    def create_reminder(
        self,
        title: str,
        list_name: Optional[str] = None,
        notes: Optional[str] = None,
        due_date: Optional[datetime] = None,
        priority: Optional[str] = None,
        tags: Optional[list[str]] = None
    ) -> dict:
        """Create a new reminder."""
        require_reminders_permission()
        with self._lock:
            reminder = EventKit.EKReminder.reminderWithEventStore_(self._store)
            reminder.setTitle_(title)

            # Set list
            if list_name:
                cal = self._find_reminder_list_unlocked(list_name)
                if cal:
                    reminder.setCalendar_(cal)
                else:
                    reminder.setCalendar_(self._store.defaultCalendarForNewReminders())
            else:
                reminder.setCalendar_(self._store.defaultCalendarForNewReminders())

            # Set due date
            if due_date:
                components = self._datetime_to_components(due_date)
                reminder.setDueDateComponents_(components)

            # Set priority (0=none, 1=high, 5=medium, 9=low)
            if priority:
                priority_map = {"high": 1, "medium": 5, "low": 9, "none": 0}
                reminder.setPriority_(priority_map.get(priority.lower(), 0))

            # Handle notes with tags, prepending attribution
            notes_with_attribution = f"{CREATED_BY_NOTE}\n\n{notes}" if notes else CREATED_BY_NOTE
            final_notes = merge_notes_with_tags(notes_with_attribution, tags)
            reminder.setNotes_(final_notes)

            # Save
            success, error = self._store.saveReminder_commit_error_(
                reminder, True, None
            )

            if not success:
                raise Exception(f"Failed to save reminder: {error}")

            return self._reminder_to_dict(reminder)

    def edit_reminder(
        self,
        reminder_id: str,
        title: Optional[str] = None,
        notes: Optional[str] = None,
        due_date: Optional[datetime] = None,
        priority: Optional[str] = None,
        completed: Optional[bool] = None,
        tags: Optional[list[str]] = None
    ) -> dict:
        """Edit an existing reminder."""
        require_reminders_permission()
        with self._lock:
            reminder = self._find_reminder_by_any_id(reminder_id)
            if not reminder:
                raise ValueError(f"Reminder not found: {reminder_id}")

            if title is not None:
                reminder.setTitle_(title)

            if due_date is not None:
                components = self._datetime_to_components(due_date)
                reminder.setDueDateComponents_(components)

            if priority is not None:
                priority_map = {"high": 1, "medium": 5, "low": 9, "none": 0}
                reminder.setPriority_(priority_map.get(priority.lower(), 0))

            if completed is not None:
                reminder.setCompleted_(completed)

            # Handle notes with tags
            if notes is not None or tags is not None:
                current_notes = reminder.notes() or ""
                clean_notes, existing_tags = decode_tags(current_notes)

                if notes is not None:
                    clean_notes = notes
                if tags is not None:
                    existing_tags = tags

                final_notes = merge_notes_with_tags(clean_notes, existing_tags)
                reminder.setNotes_(final_notes if final_notes else None)

            # Save
            success, error = self._store.saveReminder_commit_error_(
                reminder, True, None
            )

            if not success:
                raise Exception(f"Failed to update reminder: {error}")

            return self._reminder_to_dict(reminder)

    def complete_reminder(self, reminder_id: str) -> dict:
        """Mark a reminder as completed."""
        return self.edit_reminder(reminder_id, completed=True)

    def delete_reminder(self, reminder_id: str) -> bool:
        """Delete a reminder."""
        require_reminders_permission()
        with self._lock:
            reminder = self._find_reminder_by_any_id(reminder_id)
            if not reminder:
                raise ValueError(f"Reminder not found: {reminder_id}")

            success, error = self._store.removeReminder_commit_error_(
                reminder, True, None
            )

            if not success:
                raise Exception(f"Failed to delete reminder: {error}")

            return True

    def search_reminders(
        self,
        query: str,
        tags: Optional[list[str]] = None,
        include_completed: bool = False,
        limit: int = 50
    ) -> list[dict]:
        """Search reminders by text in title or notes."""
        require_reminders_permission()

        reminders = self.get_reminders(include_completed=include_completed, limit=1000)

        query_lower = query.lower()
        results = []

        for reminder in reminders:
            searchable = " ".join([
                reminder.get("title", "") or "",
                reminder.get("notes", "") or "",
            ]).lower()

            if query_lower in searchable:
                results.append(reminder)

        # Filter by tags if specified
        if tags:
            from .tags import filter_by_tags
            results = filter_by_tags(results, tags)

        return results[:limit]

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _datetime_to_nsdate(self, dt: datetime) -> NSDate:
        """Convert Python datetime to NSDate."""
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        return NSDate.dateWithTimeIntervalSince1970_(dt.timestamp())

    def _nsdate_to_iso(self, ns_date: NSDate) -> Optional[str]:
        """Convert NSDate to ISO 8601 string."""
        if not ns_date:
            return None
        timestamp = ns_date.timeIntervalSince1970()
        return datetime.fromtimestamp(timestamp).isoformat()

    def _datetime_to_components(self, dt: datetime) -> NSDateComponents:
        """Convert datetime to NSDateComponents for reminder due dates."""
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))

        components = NSDateComponents.alloc().init()
        components.setYear_(dt.year)
        components.setMonth_(dt.month)
        components.setDay_(dt.day)
        components.setHour_(dt.hour)
        components.setMinute_(dt.minute)
        components.setSecond_(dt.second)
        return components

    def _components_to_iso(self, components: NSDateComponents) -> Optional[str]:
        """Convert NSDateComponents to ISO string."""
        if not components:
            return None

        try:
            calendar = NSCalendar.currentCalendar()
            ns_date = calendar.dateFromComponents_(components)
            if ns_date:
                return self._nsdate_to_iso(ns_date)
        except Exception:
            pass

        # Fallback: manually construct date
        try:
            dt = datetime(
                year=components.year() if components.year() != 9223372036854775807 else 2000,
                month=components.month() if components.month() != 9223372036854775807 else 1,
                day=components.day() if components.day() != 9223372036854775807 else 1,
                hour=components.hour() if components.hour() != 9223372036854775807 else 0,
                minute=components.minute() if components.minute() != 9223372036854775807 else 0,
                second=components.second() if components.second() != 9223372036854775807 else 0,
            )
            return dt.isoformat()
        except Exception:
            return None

    def _calendar_to_dict(self, calendar: EventKit.EKCalendar) -> dict:
        """Convert EKCalendar to dictionary."""
        return {
            "id": calendar.calendarIdentifier(),
            "title": calendar.title(),
            "type": str(calendar.type()),
            "allows_modifications": calendar.allowsContentModifications(),
        }

    def _event_to_dict(self, event: EventKit.EKEvent) -> dict:
        """Convert EKEvent to dictionary."""
        notes = event.notes() or ""
        clean_notes, tags = decode_tags(notes)

        return {
            "id": event.calendarItemIdentifier(),
            "external_id": event.calendarItemExternalIdentifier(),
            "title": event.title(),
            "start_date": self._nsdate_to_iso(event.startDate()),
            "end_date": self._nsdate_to_iso(event.endDate()),
            "location": event.location(),
            "notes": clean_notes,
            "tags": tags,
            "calendar": event.calendar().title() if event.calendar() else None,
            "is_all_day": event.isAllDay(),
            "url": str(event.URL()) if event.URL() else None,
            "has_recurrence": event.hasRecurrenceRules(),
        }

    def _reminder_to_dict(self, reminder: EventKit.EKReminder) -> dict:
        """Convert EKReminder to dictionary."""
        notes = reminder.notes() or ""
        clean_notes, tags = decode_tags(notes)

        # Map priority back to string
        priority_val = reminder.priority()
        if priority_val == 1:
            priority = "high"
        elif priority_val == 5:
            priority = "medium"
        elif priority_val == 9:
            priority = "low"
        else:
            priority = "none"

        return {
            "id": reminder.calendarItemIdentifier(),
            "external_id": reminder.calendarItemExternalIdentifier(),
            "title": reminder.title(),
            "notes": clean_notes,
            "tags": tags,
            "list": reminder.calendar().title() if reminder.calendar() else None,
            "due_date": self._components_to_iso(reminder.dueDateComponents()),
            "priority": priority,
            "completed": reminder.isCompleted(),
            "completion_date": self._nsdate_to_iso(reminder.completionDate()),
        }

    def _find_calendar_unlocked(self, name: str) -> Optional[EventKit.EKCalendar]:
        """Find calendar by name without acquiring lock (caller must hold lock)."""
        calendars = self._store.calendarsForEntityType_(EventKit.EKEntityTypeEvent)
        for cal in (calendars or []):
            if cal.title().lower() == name.lower():
                return cal
        return None

    def _find_reminder_list_unlocked(
        self, name: str
    ) -> Optional[EventKit.EKCalendar]:
        """Find reminder list by name without acquiring lock."""
        calendars = self._store.calendarsForEntityType_(EventKit.EKEntityTypeReminder)
        for cal in (calendars or []):
            if cal.title().lower() == name.lower():
                return cal
        return None

    def _find_event_by_any_id(
        self, event_id: str
    ) -> Optional[EventKit.EKEvent]:
        """Find event by either internal or external identifier."""
        # Try internal identifier first
        item = self._store.calendarItemWithIdentifier_(event_id)
        if item and isinstance(item, EventKit.EKEvent):
            return item

        # Try external identifier
        return self._find_event_by_external_id(event_id)

    def _find_event_by_external_id(
        self, external_id: str
    ) -> Optional[EventKit.EKEvent]:
        """Find event by external identifier (searches recent events)."""
        # Search in a wide date range
        start = datetime.now() - timedelta(days=365)
        end = datetime.now() + timedelta(days=365)

        start_ns = self._datetime_to_nsdate(start)
        end_ns = self._datetime_to_nsdate(end)

        calendars = list(
            self._store.calendarsForEntityType_(EventKit.EKEntityTypeEvent) or []
        )
        if not calendars:
            return None

        predicate = self._store.predicateForEventsWithStartDate_endDate_calendars_(
            start_ns, end_ns, calendars
        )

        events = self._store.eventsMatchingPredicate_(predicate) or []
        for event in events:
            if event.calendarItemExternalIdentifier() == external_id:
                return event

        return None

    def _find_reminder_by_any_id(
        self, reminder_id: str
    ) -> Optional[EventKit.EKReminder]:
        """Find reminder by either internal or external identifier."""
        item = self._store.calendarItemWithIdentifier_(reminder_id)
        if item and isinstance(item, EventKit.EKReminder):
            return item

        return self._find_reminder_by_external_id(reminder_id)

    def _find_reminder_by_external_id(
        self, external_id: str
    ) -> Optional[EventKit.EKReminder]:
        """Find reminder by external identifier."""
        calendars = list(
            self._store.calendarsForEntityType_(EventKit.EKEntityTypeReminder) or []
        )
        if not calendars:
            return None

        predicate = self._store.predicateForRemindersInCalendars_(calendars)

        import threading
        result = []
        semaphore = threading.Semaphore(0)

        def callback(reminders):
            nonlocal result
            if reminders:
                for r in reminders:
                    if r.calendarItemExternalIdentifier() == external_id:
                        result.append(r)
                        break
            semaphore.release()

        self._store.fetchRemindersMatchingPredicate_completion_(predicate, callback)
        semaphore.acquire(timeout=30)

        return result[0] if result else None
