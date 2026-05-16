# Browser Automation Installation Notes

## Session Summary (2026-05-03)

Successfully installed and tested browser automation tools for Hermes Agent.

## Installed Components

### 1. browser-use MCP Server
- **Source**: https://github.com/Saik0s/mcp-browser-use
- **Location**: `/tmp/mcp-browser-use/`
- **Dependencies**: Python 3.11+, uv, Playwright (Chromium)
- **Status**: ✅ Installed and verified

**Key Files**:
- Server: `/tmp/mcp-browser-use/src/mcp_server_browser_use/`
- CLI entry: `/tmp/mcp-browser-use/scripts/mcp-server.py`
- Config: `~/.config/mcp-server-browser-use/config.json`

**Verification Command**:
```bash
cd /tmp/mcp-browser-use
uv run mcp-server-browser-use --help
# Output: Shows CLI commands (server, stop, status, logs, tools, etc.)
```

### 2. Firecrawl MCP Server
- **Source**: Official npm package `firecrawl-mcp`
- **Installation**: On-demand via `npx -y firecrawl-mcp`
- **Dependencies**: Node.js 18+
- **Status**: ✅ Verified (requires API key)

**Verification Command**:
```bash
npx -y firecrawl-mcp --help
# Output: "Either FIRECRAWL_API_KEY or FIRECRAWL_API_URL must be provided"
# This error = success (means package loaded)
```

## Critical Issues Encountered

### Issue 1: OpenClaw-Specific Skill Incompatibility
**Problem**: Attempted to install `firecrawl-mcp-skill` from GitHub (github.com/MaksimLokhmakov/firecrawl-mcp-skill) but it failed.

**Root Cause**: The skill is designed for OpenClaw agent framework, not Hermes Agent.

**Error Message**:
```
npm error 404 Not Found - GET https://registry.npmjs.org/@openclaw%2fcore
npm error 404 '@openclaw/core@^2026.2.0' is not in this registry.
```

**Resolution**: Use official Firecrawl MCP server via npx instead of GitHub skill.

**Lesson**: Always check if a skill is framework-specific before installation. Look for:
- Dependencies on specific agent frameworks (`@openclaw/*`, `@anthropic/*`, etc.)
- Peer dependencies mentioning specific platforms
- Repository description mentioning other frameworks

### Issue 2: uv PATH Not Set
**Problem**: After installing uv via pip, command not found.

**Error**:
```
/usr/bin/bash: line 3: uv: command not found
```

**Resolution**:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Issue 3: Playwright Browser Download
**Problem**: Large download (164MB for Chromium) may fail or timeout.

**Resolution**: 
- Download is automatic on first `playwright install`
- Cached in `~/.cache/ms-playwright/`
- Three components: Chromium (164MB), FFMPEG (2.3MB), Headless Shell (109MB)

## Environment Setup

### Required Environment Variables
```bash
# For browser-use LLM provider (choose one)
export GEMINI_API_KEY=your-gemini-key
export ANTHROPIC_API_KEY=your-anthropic-key
export OPENAI_API_KEY=your-openai-key

# For Firecrawl (required for Firecrawl tools)
export FIRECRAWL_API_KEY=fc-your-api-key

# Optional: For custom browser configuration
export MCP_BROWSER_HEADLESS=true
export MCP_BROWSER_CDP_URL=http://localhost:9222
```

### Installed Packages
```
# Python packages (via uv in /tmp/mcp-browser-use/.venv)
browser-use==0.11.2
browser-use-sdk==2.0.12
mcp-server-browser-use==0.3.0
playwright==1.57.0
fastmcp==2.14.0 (from git+https://github.com/jlowin/fastmcp.git)

# Node.js packages (global, via npx)
firecrawl-mcp@3.14.1
```

## Usage Examples

### Start browser-use Server
```bash
cd /tmp/mcp-browser-use
uv run mcp-server-browser-use server
# Server starts on http://localhost:8383
```

### Check Server Status
```bash
uv run mcp-server-browser-use status
# Output: "Server is running" or "Server not running"
```

### List Available Tools
```bash
uv run mcp-server-browser-use tools
# Lists: run_browser_agent, run_deep_research, health_check, etc.
```

### Call a Tool
```bash
uv run mcp-server-browser-use call run_browser_agent \
  --task "Go to https://example.com and tell me what you see"
```

### Use Firecrawl
```bash
# Requires API key set
export FIRECRAWL_API_KEY=fc-your-key

# Run via npx (stdio transport)
npx -y firecrawl-mcp
```

## File Locations

| Component | Location |
|-----------|----------|
| browser-use source | `/tmp/mcp-browser-use/` |
| browser-use skills | `/data/.hermes/skills/browser-use/` |
| Firecrawl skill | `/data/.hermes/skills/firecrawl-mcp/` |
| Browser cache | `~/.cache/ms-playwright/` |
| Server config | `~/.config/mcp-server-browser-use/config.json` |
| Server logs | `~/.local/state/mcp-server-browser-use/server.log` |
| Skills storage | `~/.config/browser-skills/` |

## Next Steps for Future Sessions

1. **Set API keys** before using browser automation:
   ```bash
   export GEMINI_API_KEY=your-key
   export FIRECRAWL_API_KEY=your-key
   ```

2. **Start browser-use server** before running tasks:
   ```bash
   cd /tmp/mcp-browser-use
   uv run mcp-server-browser-use server
   ```

3. **Test basic functionality**:
   ```
   "Go to https://example.com and extract the title"
   ```

4. **For Firecrawl tasks**, ensure API key is set and use:
   ```
   "Scrape https://example.com using Firecrawl"
   ```

## References

- browser-use documentation: https://github.com/Saik0s/mcp-browser-use
- Firecrawl documentation: https://docs.firecrawl.dev
- Playwright documentation: https://playwright.dev
- MCP Protocol: https://modelcontextprotocol.io
