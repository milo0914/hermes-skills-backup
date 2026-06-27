---
name: gws
description: "Google Workspace CLI: manage Calendar, Docs, Drive, Gmail, and Sheets via the `gws` command-line tool."
metadata:
  version: 0.22.5
  openclaw:
    category: "productivity"
  requires:
    bins:
    - gws
---

# Google Workspace (`gws`)

Unified skill for Google Workspace CLI operations — Calendar, Docs, Drive, Gmail, and Sheets.

## Prerequisites

```bash
# Verify gws is installed and authenticated
gws --help
gws auth status
```

If auth is not configured, run:
```bash
gws auth login
```

## Service Quick Reference

| Service | Command | Key Resources | Details |
|---------|---------|---------------|---------|
| Calendar | `gws calendar` | acl, calendarList, calendars, channels, colors, events, freebusy, settings | [references/calendar.md](references/calendar.md) |
| Docs | `gws docs` | documents | [references/docs.md](references/docs.md) |
| Drive | `gws drive` | about, accessproposals, approvals, apps, changes, channels, comments, drives, files, operations, permissions, replies, revisions, teamdrives | [references/drive.md](references/drive.md) |
| Gmail | `gws gmail` | users | [references/gmail.md](references/gmail.md) |
| Sheets | `gws sheets` | spreadsheets | [references/sheets.md](references/sheets.md) |

## Common Patterns

### Inspect any service/resource/method

```bash
# Browse resources and methods for a service
gws <service> --help

# Inspect a method's required params, types, and defaults
gws schema <service>.<resource>.<method>
```

Use `gws schema` output to build your `--params` and `--json` flags.

### Typical workflows

**Calendar**: List upcoming events, create events, manage ACL, check free/busy.
```bash
gws calendar events list --params calendarId=primary
gws calendar events insert --params calendarId=primary --json '{...}'
```

**Docs**: Create blank documents, get content, batch-update.
```bash
gws docs documents create --params '{...}'
gws docs documents get --params documentId=<ID>
```

**Drive**: Upload/download files, manage permissions, handle shared drives.
```bash
gws drive files list --params corpora=user
gws drive files get --params fileId=<ID>
```

**Gmail**: Send messages, read threads, manage labels and filters.
```bash
gws gmail users.messages list --params userId=me
gws gmail users.messages.send --params userId=me --json '{...}'
```

**Sheets**: Read/write spreadsheet data, manage properties.
```bash
gws sheets spreadsheets.get --params spreadsheetId=<ID>
gws sheets spreadsheets.values.get --params spreadsheetId=<ID> range=Sheet1!A1:D10
```

## Per-Service API Reference

Each service has a detailed reference file with all resources and methods:

- **Calendar**: see [references/calendar.md](references/calendar.md) — 8 resource groups (acl, calendarList, calendars, channels, colors, events, freebusy, settings)
- **Docs**: see [references/docs.md](references/docs.md) — documents resource (batchUpdate, create, get)
- **Drive**: see [references/drive.md](references/drive.md) — 14 resource groups (about, files, permissions, revisions, etc.)
- **Gmail**: see [references/gmail.md](references/gmail.md) — users resource (messages, threads, labels, filters, settings)
- **Sheets**: see [references/sheets.md](references/sheets.md) — spreadsheets resource (developerMetadata, sheets, values)

## Security Notes

- Never include API keys, tokens, or credentials in commands — use `gws auth` for credential management.
- Prefer `gws auth status` to verify authentication before operations.
- For destructive operations (delete, update), always confirm the target resource ID first with a `get` or `list` call.
