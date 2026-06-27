# Google Docs (`gws docs`)

> **PREREQUISITE:** Run `gws auth status` to verify authentication.

```bash
gws docs <resource> <method> [flags]
```

## API Resources

### documents

- `batchUpdate` — Applies one or more updates to the document. Each request is validated before being applied. If any request is not valid, then the entire request will fail and nothing is applied.
- `create` — Creates a blank document using the title given in the request. Other fields in the request, including any provided content, are ignored. Returns the created document.
- `get` — Gets the latest version of the specified document.

## Discovering Commands

```bash
gws docs --help
gws schema docs.<resource>.<method>
```

Use `gws schema` output to build your `--params` and `--json` flags.
