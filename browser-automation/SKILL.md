---
name: browser-automation
description: Unified browser automation and web scraping skill combining browser-use and Firecrawl. Automate browser interactions, scrape websites, extract structured data, and perform web research tasks.
user-invocable: true
metadata:
  emoji: 🤖
  requires:
    bins:
      - python3
      - node
      - npx
      - uv
    env:
      - GEMINI_API_KEY
      - ANTHROPIC_API_KEY
      - OPENAI_API_KEY
      - FIRECRAWL_API_KEY
  install: |
    # Install browser-use
    cd /tmp
    git clone https://github.com/Saik0s/mcp-browser-use.git
    cd mcp-browser-use
    uv sync
    uv run playwright install chromium
    
    # Install Firecrawl MCP
    npx -y firecrawl-mcp
    
    echo "Browser automation tools installed"
---

# Browser Automation Skill

Unified browser automation combining [browser-use](https://github.com/Saik0s/mcp-browser-use) and [Firecrawl](https://github.com/firecrawl/firecrawl) for comprehensive web interaction and data extraction.

## ⚠️ Critical Pitfalls Discovered

### Pitfall 1: OpenClaw-Specific Skills Won't Work in Hermes
**Problem**: The `firecrawl-mcp-skill` repository (github.com/MaksimLokhmakov/firecrawl-mcp-skill) is designed for OpenClaw agent framework and requires `@openclaw/core` which doesn't exist in Hermes.

**Symptom**: `npm install` fails with:
```
npm error 404 Not Found - GET https://registry.npmjs.org/@openclaw%2fcore
```

**Solution**: Use the official Firecrawl MCP server via npx instead:
```bash
npx -y firecrawl-mcp
```

The official MCP server works standalone without OpenClaw dependencies.

### Pitfall 2: API Key Requirements
**Problem**: Both tools require API keys but fail silently or with unclear errors.

**Symptoms**:
- browser-use: "Server is not running" or LLM provider errors
- Firecrawl: "Either FIRECRAWL_API_KEY or FIRECRAWL_API_URL must be provided"

**Solution**: Set environment variables BEFORE starting services:
```bash
# For browser-use (choose one)
export GEMINI_API_KEY=your-key
export ANTHROPIC_API_KEY=your-key  
export OPENAI_API_KEY=your-key

# For Firecrawl
export FIRECRAWL_API_KEY=fc-your-key
```

### Pitfall 3: uv PATH Issues
**Problem**: After installing uv via pip, the `uv` command may not be in PATH.

**Symptom**: `uv: command not found`

**Solution**: Add to PATH:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Features

### Browser Automation (browser-use)
- 🤖 **AI Agent Control** - Natural language browser automation
- 🖱️ **Interactive Actions** - Click, type, scroll, navigate
- 🖼️ **Vision Support** - Screenshot and visual analysis
- 📝 **Form Automation** - Fill forms, submit, handle logins
- 🔍 **Deep Research** - Multi-step web investigation

### Web Scraping (Firecrawl)
- 🔍 **Smart Search** - AI-powered web search with extraction
- 📄 **Content Scraping** - Clean markdown/HTML extraction
- 🕷️ **Website Crawling** - Crawl with depth limits
- 🤖 **LLM Extraction** - Structured data extraction
- 📊 **Batch Processing** - Process multiple URLs

## Requirements

- Python 3.11+
- Node.js 18+
- LLM API key (Gemini, Anthropic, or OpenAI)
- Firecrawl API key (optional, for Firecrawl features)

## Installation Workflow (Verified)

### Step 1: Install Prerequisites
```bash
# Install uv (Python package manager)
pip install uv

# Ensure Node.js 18+ is installed
node --version  # Should be v18+

# Add uv to PATH
export PATH="$HOME/.local/bin:$PATH"
```

### Step 2: Install browser-use MCP Server
```bash
# Clone the repository
cd /tmp
git clone https://github.com/Saik0s/mcp-browser-use.git
cd mcp-browser-use

# Install dependencies with uv
uv sync

# Install Playwright browsers (Chromium)
uv run playwright install chromium
```

### Step 3: Install Firecrawl MCP (Optional)
```bash
# No installation needed - runs via npx
# Just ensure you have the API key
export FIRECRAWL_API_KEY=fc-your-key
```

### Step 4: Verify Installation
```bash
# Check browser-use
cd /tmp/mcp-browser-use
uv run mcp-server-browser-use --help

# Check Firecrawl
npx -y firecrawl-mcp --help  # Will show API key error = success
```

## Usage Patterns

### Pattern 1: Simple Browser Task
```
Go to https://example.com and tell me what you see.
```

### Pattern 2: Form Automation
```
Navigate to login page, enter credentials, click login, and capture the dashboard.
```

### Pattern 3: Data Extraction
```
Extract all product prices and names from https://shop.example.com/products
```

### Pattern 4: Research Task
```
Research the top 5 AI browser automation tools and create a comparison table.
```

### Pattern 5: Scraping + Analysis\n```\nScrape https://techcrunch.com and summarize the top 3 AI news articles.\n```\n\n### Pattern 6: Patent Database Search (NEW)\n```\nSearch Google Patents for \"Merck KGaA negative dielectric liquid crystal\"\nExtract patent numbers, titles, filing dates, and claim 1 text\n```\n**Critical requirements for patent search:**\n- All major patent databases (Google Patents, USPTO, WIPO, Espacenet) require full JavaScript rendering\n- Simple HTTP requests (curl/requests) return only minimal HTML without search results\n- Must use browser automation (browser-use or Playwright directly)\n- Wait strategy: `networkidle` + 5-10 seconds for content rendering\n- Before starting, verify environment readiness (see Environment Readiness Check below)

## Available Tools

### Browser Use Tools

#### run_browser_agent
Execute browser automation with natural language.

**Parameters:**
- `task` (string): Task description
- `headless` (boolean): Run in headless mode
- `max_steps` (integer): Maximum agent steps

**Example:**
```
run_browser_agent("Go to google.com, search for 'Python tutorials', click first result")
```

#### run_deep_research
Multi-step web research.

**Parameters:**
- `research_task` (string): Research question
- `max_searches` (integer): Max search queries

**Example:**
```
run_deep_research("What are the best Python web scraping libraries in 2026?")
```

### Firecrawl Tools

#### scrape
Extract content from a webpage.

**Parameters:**
- `url` (string): Page URL
- `formats` (array): Output formats
- `onlyMainContent` (boolean): Extract main content only

**Example:**
```
scrape("https://example.com/article", formats=["markdown"])
```

#### search
Web search with content extraction.

**Parameters:**
- `query` (string): Search query
- `limit` (integer): Max results

**Example:**
```
search("Python async web scraping", limit=5)
```

#### crawl
Crawl website with depth control.

**Parameters:**
- `url` (string): Starting URL
- `limit` (integer): Max pages
- `maxDepth` (integer): Max depth

**Example:**
```
crawl("https://docs.python.org", limit=20, maxDepth=2)
```

#### extract
LLM-powered structured extraction.

**Parameters:**
- `urls` (array): URLs to process
- `prompt` (string): Extraction instructions
- `schema` (object): JSON schema

**Example:**
```
extract(
  urls=["https://shop.example.com"],
  prompt="Extract product name, price, rating",
  schema={"type": "object", "properties": {...}}
)
```

## Workflow Examples

### Example 1: Automated Testing
```
1. Navigate to test page
2. Fill form fields
3. Submit form
4. Verify result
5. Capture screenshot
```

### Example 2: Price Monitoring
```
1. Scrape product pages
2. Extract prices
3. Compare with historical data
4. Alert on changes
```

### Example 3: Content Aggregation
```
1. Search for topic
2. Scrape top results
3. Extract key information
4. Generate summary report
```

### Example 4: Lead Generation
```
1. Crawl company websites
2. Extract contact information
3. Validate emails
4. Export to CSV
```

## Configuration Reference

### Browser Use Settings

| Key | Default | Description |
|-----|---------|-------------|
| `llm.provider` | `google` | LLM provider |
| `llm.model_name` | `gemini-3-flash-preview` | Model for agent |
| `browser.headless` | `true` | Headless mode |
| `browser.cdp_url` | - | External Chrome CDP URL |
| `agent.max_steps` | `20` | Max steps per task |
| `agent.use_vision` | `true` | Enable vision |

### Firecrawl Settings

| Key | Default | Description |
|-----|---------|-------------|
| `FIRECRAWL_API_KEY` | - | API key (required) |
| `FIRECRAWL_BASE_URL` | - | Self-hosted URL |
| `formats` | `["markdown"]` | Output format |
| `onlyMainContent` | `true` | Main content only |

## Troubleshooting\n\n### Environment Readiness Check (CRITICAL - Run Before Starting)\n\nBefore attempting patent database searches or complex browser automation, verify:\n\n```bash\n# 1. Check if Playwright/Chromium is installed\nls -la ~/.cache/ms-playwright/ | grep chromium\n# Should show chromium-XXXX/ directory\n\n# 2. Check if browser-use MCP server is installed\ncd /tmp/mcp-browser-use && uv run mcp-server-browser-use --help\n# If fails, install: git clone https://github.com/Saik0s/mcp-browser-use.git && cd mcp-browser-use && uv sync\n\n# 3. Check required API keys (at least one must be set)\necho \"OPENROUTER_API_KEY: ${OPENROUTER_API_KEY:-NOT SET}\"\necho \"GEMINI_API_KEY: ${GEMINI_API_KEY:-NOT SET}\"\necho \"ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-NOT SET}\"\necho \"FIRECRAWL_API_KEY: ${FIRECRAWL_API_KEY:-NOT SET}\"\n\n# 4. Check if uv is in PATH\nwhich uv || echo \"uv not found - install with: pip install uv && export PATH=\"$HOME/.local/bin:$PATH\"\n```\n\n**If any check fails**, inform the user immediately with specific installation instructions rather than attempting futile requests.\n\n### Browser Use Issues

**Server won't start:**
```bash
cd /tmp/mcp-browser-use
uv run mcp-server-browser-use status
uv run mcp-server-browser-use logs
pkill -f mcp-server-browser-use
```

**Browser crashes:**
```bash
# Reinstall Playwright
uv run playwright install chromium

# Try non-headless mode
mcp-server-browser-use config set -k browser.headless -v false
```

**"No local browser path found" error:**
Playwright 已安裝但 browser-use 找不到瀏覽器路徑。確認 Chromium 安裝位置：
```bash
ls -la ~/.cache/ms-playwright/
# 應包含 chromium-1200/ 目錄
```

**API Key 未生效：**
確保在啟動 server「之前」設置環境變數：
```bash
export OPENROUTER_API_KEY=sk-or-v1-xxx
uv run mcp-server-browser-use server
```

### Firecrawl Issues

**API key error:**
```bash
echo $FIRECRAWL_API_KEY
# If empty, set it:
export FIRECRAWL_API_KEY=fc-your-key
```

**Rate limiting:**
- Reduce concurrent requests
- Implement retry logic
- Consider upgrading plan

### Environment Limitations (重要)

**DNS 解析問題：**
某些環境可能無法解析外部域名（如 `rss.udn.com`、`news.google.com`）。
徵兆：`socket.gaierror: [Errno -2] Name or service not known`
解決方案：
- 使用有 DNS 解析的環境
- 或通過 CDP 連接到有網路訪問的瀏覽器

**Google News 400 錯誤：**
Google News 需要有效的會話和請求頭，直接抓取可能返回 400。
解決方案：
- 使用 Firecrawl API 而非直接抓取
- 或使用 browser-use 的瀏覽器自動化功能

**網站年齡驗證：**
某些網站（如 PTT）需要年滿 18 歲確認。
解決方案：
- 使用 CDP 連接到已登入的瀏覽器會話
- 或設置 persistent user data directory

**HTTP2 協議錯誤：**
某些網站可能返回 `ERR_HTTP2_PROTOCOL_ERROR`。
解決方案：
- 使用不同的瀏覽器配置
- 或改用其他新聞來源

## Best Practices

1. **Use headless mode** for production (faster, less resource)
2. **Set appropriate timeouts** for long-running tasks
3. **Implement retry logic** for network operations
4. **Cache results** when possible to reduce API calls
5. **Respect robots.txt** and website terms
6. **Use structured extraction** for consistent output
7. **Monitor API usage** to avoid surprises

## Security Considerations

- Never commit API keys to version control
- Use environment variables for sensitive data
- Validate URLs before processing
- Sanitize user inputs
- Implement rate limiting
- Use dedicated browser profiles for automation

## Architecture

```
User Request
    ↓
Hermes Agent
    ├─→ Browser Use MCP → Playwright → Browser
    └─→ Firecrawl MCP → Firecrawl API → Target Site
```

## References

- [browser-use GitHub](https://github.com/Saik0s/mcp-browser-use)
- [Firecrawl Documentation](https://docs.firecrawl.dev)
- [Playwright Documentation](https://playwright.dev)
- [MCP Protocol](https://modelcontextprotocol.io)

## Support Files

- **Patent Database Requirements**: `references/patent-database-requirements.md` — Technical requirements, API authentication, and access patterns for Google Patents, USPTO, WIPO, Espacenet (verified 2026-05)
- **Installation Notes**: Detailed session notes, troubleshooting, and environment setup at `references/installation-notes.md`
- **Quick Reference**: Common commands and usage patterns at `templates/quick-reference.md`

## Support Files

- **Installation Notes**: Detailed session notes, troubleshooting, and environment setup at `references/installation-notes.md`
- **Quick Reference**: Common commands and usage patterns at `templates/quick-reference.md`

## Consolidated Skills

## Session Patterns Captured

### Automated Backup System Creation (2026-05-12)

This session established a pattern for creating automated backup systems for Hermes Agent session data:

**Key Components:**
1. **Core backup script** (`backup_sessions.py`) - Python script with incremental sync, MD5 hashing, locking
2. **Startup wrapper** (`startup_backup.sh`) - Bash script for system startup execution
3. **Installation script** (`install_backup_system.sh`) - Automated setup with environment validation
4. **Cron configuration** - Scheduled execution every 6 hours
5. **State tracking** - JSON-based backup state with session hashes
6. **Documentation** - Comprehensive guides and README files

**Workflow Pattern:**
```
1. Analyze existing persistence mechanism (SQLite + JSON)
2. Create incremental backup script with:
   - MD5 hash comparison for change detection
   - Lock file mechanism to prevent concurrent execution
   - Optional HuggingFace push with rate limiting
   - Timeout protection (300s)
3. Create startup wrapper for system boot execution
4. Set up cron job for periodic execution
5. Create installation script for reproducibility
6. Document everything with examples and troubleshooting
```

**GitHub Push Pattern:**
When preparing code for GitHub:
1. Create temporary git repository with all files
2. Add comprehensive README, LICENSE, .gitignore, requirements.txt
3. Initialize git and commit with descriptive message
4. Provide multiple push options (GitHub CLI, manual, API)
5. Document the process for future reference

**Files Created:**
- `/data/.hermes/bin/backup_sessions.py` - Main backup script
- `/data/.hermes/bin/startup_backup.sh` - Startup wrapper
- `/data/.hermes/bin/install_backup_system.sh` - Installation script
- `/data/.hermes/bin/prepare_github_push.sh` - GitHub preparation
- `/data/.hermes/bin/push_to_github.sh` - GitHub push script
- `/data/.hermes/bin/push_to_github_api.py` - API-based push
- `/data/.hermes/bin/README.md` - Documentation
- `/data/.hermes/AUTO_BACKUP_GUIDE.md` - User guide
- `/data/.hermes/BACKUP_README.md` - Quick reference

**Key Learnings:**
- Incremental backups reduce I/O and API calls significantly
- Lock files prevent data corruption from concurrent executions
- Rate limiting is critical for external API integration (HuggingFace: 5 commits/hour)
- Dual storage (SQLite + JSON) provides redundancy
- Comprehensive documentation reduces future support burden
- GitHub CLI simplifies repository creation and pushing

**Pitfalls to Avoid:**
- systemd service files cannot be written to `/etc/systemd/system/` without sudo
- Alternative: use `~/.bashrc` or modify application launch script
- HuggingFace has strict rate limits (5 commits/hour, 10min intervals)
- Lock files must be cleaned up manually if backup crashes
- All sessions in DB may not have corresponding JSON files (sync gap)

This pattern applies to any automated backup/data sync workflow for Hermes Agent.

### browser-use (archived)
The `browser-use` skill focused exclusively on browser-use MCP server installation and configuration. Its key contributions:
- Detailed MCP server startup workflow (`uv run mcp-server-browser-use server`)
- MCP client configuration JSON snippet
- Skill learning tools (skill_list, skill_get, skill_delete)
- Architecture diagram showing MCP Client → browser-use MCP Server → Playwright chain

All unique content has been absorbed into this umbrella skill's installation and usage sections.

### firecrawl-mcp (archived)
The `firecrawl-mcp` skill focused exclusively on Firecrawl MCP server. Its key contributions:
- Interactive browser tools (browser_action, browser_screenshot, browser_wait)
- Cost optimization tips (onlyMainContent reduces tokens ~40%)
- Automatic retry logic configuration
- Map tool for website structure discovery

All unique content has been absorbed into this umbrella skill's tools and best practices sections.
