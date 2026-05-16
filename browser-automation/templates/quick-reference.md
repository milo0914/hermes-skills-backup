# Browser Automation Quick Reference

## Quick Start Commands

### Start browser-use Server
```bash
cd /tmp/mcp-browser-use
uv run mcp-server-browser-use server
```

### Check if Running
```bash
uv run mcp-server-browser-use status
```

### View Logs
```bash
uv run mcp-server-browser-use logs -f
```

### Stop Server
```bash
uv run mcp-server-browser-use stop
```

## Environment Setup (One-Time)

```bash
# Set API keys (add to ~/.bashrc or ~/.zshrc)
export GEMINI_API_KEY=your-key-here
export ANTHROPIC_API_KEY=your-key-here  # alternative
export OPENAI_API_KEY=your-key-here     # alternative
export FIRECRAWL_API_KEY=fc-your-key-here

# Add uv to PATH
export PATH="$HOME/.local/bin:$PATH"
```

## Common Tasks

### Basic Browser Automation
```
"Go to https://example.com and tell me what you see"
```

### Form Filling
```
"Navigate to login page, enter username 'test' and password 'secret', click login"
```

### Data Extraction
```
"Extract all product prices from https://shop.example.com/products"
```

### Web Research
```
"Research the top 5 AI browser automation tools and create a comparison"
```

### Scrape with Firecrawl
```
"Scrape https://example.com/article and extract the main content"
```

### Search and Summarize
```
"Search for 'Python web scraping best practices' and summarize top 3 results"
```

## Configuration Commands

### View Current Config
```bash
uv run mcp-server-browser-use config view
```

### Set Config Value
```bash
uv run mcp-server-browser-use config set -k browser.headless -v false
uv run mcp-server-browser-use config set -k agent.max_steps -v 30
```

### Reset to Defaults
```bash
rm ~/.config/mcp-server-browser-use/config.json
```

## Troubleshooting

### Server Won't Start
```bash
# Check if already running
uv run mcp-server-browser-use status

# Kill orphan processes
pkill -f mcp-server-browser-use

# Check logs
uv run mcp-server-browser-use logs
```

### Browser Crashes
```bash
# Reinstall Playwright browsers
cd /tmp/mcp-browser-use
uv run playwright install chromium

# Try non-headless mode
uv run mcp-server-browser-use config set -k browser.headless -v false
```

### API Key Errors
```bash
# Check if key is set
echo $GEMINI_API_KEY
echo $FIRECRAWL_API_KEY

# If empty, set it
export GEMINI_API_KEY=your-key
```

### Port Already in Use
```bash
# Default port is 8383, change it:
uv run mcp-server-browser-use config set -k server.port -v 8384
```

## Health Checks

```bash
# Check server health
uv run mcp-server-browser-use health

# List recent tasks
uv run mcp-server-browser-use tasks

# Get specific task
uv run mcp-server-browser-use task <task-id>
```

## Advanced: Direct Tool Calls

```bash
# Health check
uv run mcp-server-browser-use call health_check

# Run browser agent
uv run mcp-server-browser-use call run_browser_agent \
  --task "Go to https://example.com"

# Run deep research
uv run mcp-server-browser-use call run_deep_research \
  --research_task "AI browser automation trends 2026"
```

## Resource Usage

- **Browser cache**: `~/.cache/ms-playwright/` (~275MB)
- **Server process**: ~200-500MB RAM when idle
- **Browser process**: ~300-800MB RAM per task
- **CPU**: Spikes during page loads, otherwise minimal

## Security Notes

- Never commit API keys to version control
- Use dedicated browser profiles for automation
- CDP connections restricted to localhost only
- Private IPs blocked in direct execution (SSRF protection)
- Sensitive headers redacted before skill storage
