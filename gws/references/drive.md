# Google Drive (`gws drive`)

> **PREREQUISITE:** Run `gws auth status` to verify authentication.

```bash
gws drive <resource> <method> [flags]
```

## API Resources

### about

- `get` — Gets information about the user, the user's Drive, and system capabilities.

### accessproposals

- `get` — Retrieves an access proposal by ID.
- `list` — List the access proposals on a file. Only approvers can list; 403 for non-approvers.
- `resolve` — Approves or denies an access proposal.

### approvals

- `get` — Gets an Approval by ID.
- `list` — Lists the Approvals on a file.

### apps

- `get` — Gets a specific app.
- `list` — Lists a user's installed apps.

### changes

- `getStartPageToken` — Gets the starting pageToken for listing future changes.
- `list` — Lists the changes for a user or shared drive.
- `watch` — Subscribes to changes for a user.

### channels

- `stop` — Stops watching resources through this channel.

### comments

- `create` — Creates a comment on a file. Requires `fields` parameter.
- `delete` — Deletes a comment.
- `get` — Gets a comment by ID. Requires `fields` parameter.
- `list` — Lists a file's comments. Requires `fields` parameter.
- `update` — Updates a comment with patch semantics. Requires `fields` parameter.

### drives

- `create` — Creates a shared drive.
- `get` — Gets a shared drive's metadata by ID.
- `hide` — Hides a shared drive from the default view.
- `list` — Lists the user's shared drives. Accepts `q` search parameter.
- `unhide` — Restores a shared drive to the default view.
- `update` — Updates the metadata for a shared drive.

### files

- `copy` — Creates a copy of a file with patch semantics.
- `create` — Creates a file. Supports upload URI; max 5,120 GB; any MIME type.
- `download` — Downloads the content of a file. Operations valid for 24 hours.
- `export` — Exports a Google Workspace document to requested MIME type. Max 10 MB.
- `generateIds` — Generates file IDs for create/copy requests.
- `get` — Gets a file's metadata or content by ID. Use `alt=media` for content.
- `list` — Lists the user's files. Accepts `q` search parameter. Returns all files including trashed by default; use `trashed=false`.
- `listLabels` — Lists the labels on a file.
- `modifyLabels` — Modifies the set of labels applied to a file.
- `update` — Updates a file's metadata, content, or both. Supports upload URI; max 5,120 GB.
- `watch` — Subscribes to changes to a file.

### operations

- `get` — Gets the latest state of a long-running operation.

### permissions

- `create` — Creates a permission for a file or shared drive. **Warning:** Concurrent ops unsupported; last write wins.
- `delete` — Deletes a permission. Same concurrency warning.
- `get` — Gets a permission by ID.
- `list` — Lists a file's or shared drive's permissions.
- `update` — Updates a permission with patch semantics. Same concurrency warning.

### replies

- `create` — Creates a reply to a comment.
- `delete` — Deletes a reply.
- `get` — Gets a reply by ID.
- `list` — Lists a comment's replies.
- `update` — Updates a reply with patch semantics.

### revisions

- `delete` — Permanently deletes a file version. Only for binary content (images/videos); not for Docs/Sheets.
- `get` — Gets a revision's metadata or content by ID.
- `list` — Lists a file's revisions. May be incomplete for large revision histories.
- `update` — Updates a revision with patch semantics.

### teamdrives

- `create` — **Deprecated:** Use `drives.create` instead.
- `get` — **Deprecated:** Use `drives.get` instead.
- `list` — **Deprecated:** Use `drives.list` instead.
- `update` — **Deprecated:** Use `drives.update` instead.

## Discovering Commands

```bash
gws drive --help
gws schema drive.<resource>.<method>
```

Use `gws schema` output to build your `--params` and `--json` flags.
