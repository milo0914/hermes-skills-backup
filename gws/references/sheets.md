# Google Sheets (`gws sheets`)

> **PREREQUISITE:** Run `gws auth status` to verify authentication.

```bash
gws sheets <resource> <method> [flags]
```

## Helper Commands

| Command | Description |
|---------|-------------|
| `+append` | Append a row to a spreadsheet |
| `+read` | Read values from a spreadsheet |

## API Resources

### spreadsheets

- `batchUpdate` — Applies one or more updates to the spreadsheet. Each request is validated before being applied.
- `create` — Creates a spreadsheet, returning the newly created spreadsheet.
- `get` — Returns the spreadsheet at the given ID. By default, data within grids is not returned.
- `getByDataFilter` — Returns the spreadsheet at the given ID, allowing selective data subset retrieval via dataFilters.
- `developerMetadata` — Operations on the 'developerMetadata' resource
- `sheets` — Operations on the 'sheets' resource
- `values` — Operations on the 'values' resource

## Discovering Commands

```bash
gws sheets --help
gws schema sheets.<resource>.<method>
```

Use `gws schema` output to build your `--params` and `--json` flags.
