---
name: browser-use
description: Browser automation using browser-use MCP server. Automate web tasks, click buttons, fill forms, extract data, and navigate websites with AI agents.
user-invocable: true
metadata:
  emoji: 🌐
  requires:
    bins:
      - python3
      - uv
    env:
      - GEMINI_API_KEY
      - ANTHROPIC_API_KEY
      - OPENAI_API_KEY
  install: |
    # Install browser-use MCP server
    cd /tmp
    git clone https://github.com/Saik0s/mcp-browser-use.git
    cd mcp-browser-use
    uv sync
    uv run playwright install chromium
    
    # Start the server
    uv run mcp-server-browser-use server
---

# Browser Use MCP Skill

AI-driven browser automation using [browser-use](https://github.com/browser-use/browser-use) via MCP.

## Features

- **🤖 Browser Agent** - Execute natural language browser tasks
- **🔍 Deep Research** - Multi-step web research with automated browsing
- **📝 Form Automation** - Fill forms, click buttons, navigate pages
- **🖼️ Vision Support** - Screenshot and visual analysis capabilities
- **🔧 Skill Learning** - Save and reuse browser automation patterns

## Requirements

- Python 3.11+
- Node.js 18+
- LLM API key (Gemini, Anthropic, OpenAI, etc.)

## Configuration

### 1. Set LLM API Key

```bash
# Choose one of the following:
export GEMINI_API_KEY=your-key-here
export ANTHROPIC_API_KEY=your-key-here
export OPENAI_API_KEY=your-key-here
```

### 2. Start the MCP Server

```bash
cd /tmp/mcp-browser-use
uv run mcp-server-browser-use server
```

### 3. Configure MCP Client

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "browser-use": {
      "type": "streamable-http",
      "url": "http://localhost:8383/mcp"
    }
  }
}
```

## Available Tools

### 1. run_browser_agent

Execute a browser automation task using natural language.

**Example:**
```
Go to example.com and find the title of the page.
```

**Parameters:**
- `task` (string, required): Natural language description of the task
- `headless` (boolean, optional): Run browser in headless mode (default: true)
- `max_steps` (integer, optional): Maximum steps for the agent (default: 20)

### 2. run_deep_research

Perform deep web research on a topic.

**Example:**
```
Research the latest advancements in AI browser automation.
```

**Parameters:**
- `research_task` (string, required): Research question or topic
- `max_searches` (integer, optional): Maximum search queries (default: 5)

### 3. health_check

Check server health status.

### 4. skill_list / skill_get / skill_delete

Manage learned browser automation skills.

## Usage Examples

### Basic Browsing
```
Navigate to https://example.com and tell me what you see.
```

### Form Filling
```
Go to login page, enter username 'test' and password 'secret', then click login.
```

### Data Extraction
```
Extract all product prices from https://example.com/products.
```

### Research Task
```
Find information about the best Python web scraping libraries in 2026.
```

## Configuration Options

| Key | Default | Description |
|-----|---------|-------------|
| `llm.provider` | `google` | LLM provider |
| `llm.model_name` | `gemini-3-flash-preview` | Model for agent |
| `browser.headless` | `true` | Run browser without GUI |
| `browser.cdp_url` | - | Connect to existing Chrome |
| `agent.max_steps` | `20` | Max steps per task |
| `agent.use_vision` | `true` | Enable vision capabilities |

## Troubleshooting

### Server won't start
1. Check if already running: `mcp-server-browser-use status`
2. Check logs: `mcp-server-browser-use logs`
3. Kill orphan processes: `pkill -f mcp-server-browser-use`

### Browser issues
1. Reinstall Playwright: `uv run playwright install chromium`
2. Check headless mode: Set `browser.headless` to `false`
3. **"No local browser path found" error**: 
   - Playwright installed but browser-use can't find Chrome
   - Check Chromium installation: `ls -la ~/.cache/ms-playwright/`
   - Set headless mode: `mcp-server-browser-use config set -k browser.headless -v true`

### API key errors
Ensure one of the following environment variables is set:
- `GEMINI_API_KEY`
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `OPENROUTER_API_KEY` (for OpenRouter)

**Important**: Set API keys BEFORE starting the server!

### Environment Limitations

**DNS Resolution Issues:**
Some environments cannot resolve external domains. Test with:
```bash
python3 -c "import socket; print(socket.gethostbyname('news.google.com'))"
```

**Google News 400 Errors:**
Google News may return 400 for direct requests. Use browser automation or Firecrawl API instead.

**Chrome Installation:**
If `playwright install chrome` fails (needs root), use Chromium:
```bash
uv run playwright install chromium
ls -la ~/.cache/ms-playwright/chromium-1200/
```

### ⚠️ Important: uv PATH Issue
If `uv` command not found after installation:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

### ⚠️ Important: API Key Must Be Set Before Starting
Set environment variables BEFORE starting the server:
```bash
export GEMINI_API_KEY=your-key
uv run mcp-server-browser-use server
```

## Architecture

```
User Request
    ↓
Hermes Agent
    ↓
MCP Client
    ↓
browser-use MCP Server (HTTP daemon)
    ↓
Playwright (Chromium)
    ↓
Target Website
```

## References

- GitHub: https://github.com/Saik0s/mcp-browser-use
- browser-use: https://github.com/browser-use/browser-use
- Documentation: https://docs.browser-use.com
