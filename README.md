# Apple EventKit MCP Server

A Model Context Protocol (MCP) server that provides Claude Desktop with access to Apple Calendar and Reminders on macOS.

## Features

### Calendar Operations
- **List calendars**: View all available calendars
- **List events**: Get events within a date range
- **Search events**: Search by text in title, location, or notes
- **Create events**: Add new calendar events with location, notes, URL, and tags
- **Edit events**: Modify existing events (with recurring event support)
- **Delete events**: Remove events (with recurring event support)

### Reminder Operations
- **List reminder lists**: View all reminder lists
- **List reminders**: Get reminders with filters (completed, due date)
- **Search reminders**: Search by text in title or notes
- **Create reminders**: Add new reminders with due date, priority, and tags
- **Edit reminders**: Modify existing reminders
- **Complete reminders**: Mark reminders as done
- **Delete reminders**: Remove reminders

### Tagging System
Since Apple's EventKit doesn't support native tags, this server implements a hashtag-based tagging system. Tags are stored as `#hashtags` at the end of the notes field and sync via iCloud.

## Installation

### Prerequisites
- macOS 10.15 or later
- Python 3.10 or later
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Step 1: Grant Permissions

Before using the MCP server, you need to grant Calendar and Reminders permissions.

Run the setup script from Terminal:

```bash
cd /path/to/apple-eventkit-mcp
uv run python scripts/setup_permissions.py
```

This will trigger system permission dialogs. Click "OK" to grant access to both Calendar and Reminders.

**If dialogs don't appear**, manually grant permissions:
1. Open **System Settings** > **Privacy & Security** > **Calendar**
2. Enable access for Terminal (and/or your Python interpreter)
3. Open **System Settings** > **Privacy & Security** > **Reminders**
4. Enable access for Terminal (and/or your Python interpreter)

### Step 2: Configure Claude Desktop

Add this server to your Claude Desktop configuration.

Open `~/Library/Application Support/Claude/claude_desktop_config.json` and add:

```json
{
  "mcpServers": {
    "apple-eventkit": {
      "command": "/path/to/uv",
      "args": [
        "--directory",
        "/path/to/apple-eventkit-mcp",
        "run",
        "python",
        "-m",
        "apple_eventkit_mcp.server"
      ]
    }
  }
}
```

Replace `/path/to/uv` with the output of `which uv` and `/path/to/apple-eventkit-mcp` with your actual installation path.

### Step 3: Restart Claude Desktop

Completely quit and restart Claude Desktop. You should see the MCP server indicator (hammer icon) in the chat input area.

## Usage Examples

Once configured, you can ask Claude to:

- "Show me my calendar events for this week"
- "Create a meeting titled 'Team Sync' tomorrow at 2pm for 1 hour"
- "List my reminders that are due this week"
- "Create a reminder to 'Review PR' with high priority, due Friday"
- "Search for calendar events containing 'dentist'"
- "Mark my 'Buy groceries' reminder as complete"

## Available Tools

### Permission Tools
| Tool | Description |
|------|-------------|
| `eventkit_check_permissions` | Check Calendar and Reminders permission status |

### Calendar Tools
| Tool | Description |
|------|-------------|
| `calendar_list_calendars` | List all available calendars |
| `calendar_list_events` | List events within a date range |
| `calendar_get_event` | Get event details by ID |
| `calendar_search_events` | Search events by text/tags |
| `calendar_create_event` | Create a new event |
| `calendar_edit_event` | Edit an existing event |
| `calendar_delete_event` | Delete an event |

### Reminder Tools
| Tool | Description |
|------|-------------|
| `reminders_list_lists` | List all reminder lists |
| `reminders_list` | List reminders with filters |
| `reminders_get` | Get reminder details by ID |
| `reminders_search` | Search reminders by text/tags |
| `reminders_create` | Create a new reminder |
| `reminders_edit` | Edit an existing reminder |
| `reminders_complete` | Mark a reminder as completed |
| `reminders_delete` | Delete a reminder |

## Troubleshooting

### "Permission denied" errors

1. Run the setup script: `uv run python scripts/setup_permissions.py`
2. If that doesn't work, manually grant permissions in System Settings
3. Make sure Claude Desktop (or the Python interpreter it uses) has access

### Server doesn't appear in Claude Desktop

1. Check your JSON configuration for syntax errors
2. Verify the paths are correct (use absolute paths)
3. Check Claude Desktop logs at `~/Library/Logs/Claude/mcp-server-apple-eventkit.log`
4. Try running the server manually to test:
   ```bash
   cd /path/to/apple-eventkit-mcp
   uv run python -m apple_eventkit_mcp.server
   ```

### Events/reminders not showing up

- Check that the correct calendar or reminder list is selected
- iCloud sync may take a moment to reflect changes
- Verify the date range you're querying includes the items

## How Tagging Works

Since EventKit doesn't support native tags, this server stores tags as hashtags at the end of the notes field:

```
Your note content here

#work #high_priority
```

Tags are:
- Human-readable in Calendar and Reminders apps
- Synced via iCloud with the item
- Searchable by the MCP server
- Automatically normalized (spaces become underscores, lowercase)

## License

MIT
