# Google Calendar (`gws calendar`)

> **PREREQUISITE:** Run `gws auth status` to verify authentication. If missing, run `gws auth login`.

```bash
gws calendar <resource> <method> [flags]
```

## API Resources

### acl

- `delete` — Deletes an access control rule.
- `get` — Returns an access control rule.
- `insert` — Creates an access control rule.
- `list` — Returns the rules in the access control list for the calendar.
- `patch` — Updates an access control rule. This method supports patch semantics.
- `update` — Updates an access control rule.
- `watch` — Watch for changes to ACL resources.

### calendarList

- `delete` — Removes a calendar from the user's calendar list.
- `get` — Returns a calendar from the user's calendar list.
- `insert` — Inserts an existing calendar into the user's calendar list.
- `list` — Returns the calendars on the user's calendar list.
- `patch` — Updates an existing calendar on the user's calendar list. This method supports patch semantics.
- `update` — Updates an existing calendar on the user's calendar list.
- `watch` — Watch for changes to CalendarList resources.

### calendars

- `clear` — Clears a primary calendar.
- `delete` — Deletes a secondary calendar.
- `get` — Returns metadata for a calendar.
- `insert` — Creates a secondary calendar.
- `patch` — Updates metadata for a calendar. This method supports patch semantics.
- `update` — Updates metadata for a calendar.

### channels

- `stop` — Stop watching resources through this channel.

### colors

- `get` — Returns the color definitions for calendars and events.

### events

- `delete` — Deletes an event.
- `get` — Returns an event.
- `import` — Imports an event. This is only used for iCalendar format events.
- `insert` — Creates an event.
- `instances` — Returns instances of the specified recurring event.
- `list` — Returns events on the specified calendar.
- `move` — Moves an event to another calendar.
- `patch` — Updates an event. This method supports patch semantics.
- `quickAdd` — Creates an event based on a simple text string.
- `update` — Updates an event.
- `watch` — Watch for changes to Events resources.

### freebusy

- `query` — Returns free/busy information for a set of calendars and/or groups.

### settings

- `get` — Returns a single user setting.
- `list` — Returns all user settings for the authenticated user.
- `watch` — Watch for changes to Settings resources.

## Discovering Commands

```bash
gws calendar --help
gws schema calendar.<resource>.<method>
```
