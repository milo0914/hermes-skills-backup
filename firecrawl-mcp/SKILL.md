---
name: firecrawl-mcp
description: Firecrawl MCP Server for web scraping, crawling, search, and LLM-powered content extraction. Official Firecrawl MCP integration.
user-invocable: true
metadata:
  emoji: 🔥
  requires:
    bins:
      - node
      - npx
    env:
      - FIRECRAWL_API_KEY
  install: |
    # Firecrawl MCP Server - requires Node.js 18+ and FIRECRAWL_API_KEY
    # Install via npx: npx -y firecrawl-mcp
    echo "Firecrawl MCP Skill installed"
---

# Firecrawl MCP Skill

Official Firecrawl MCP Server integration for powerful web scraping, crawling, and AI-powered content extraction.

## Features

- **🔍 Web Search** — Search the web with AI-powered content extraction
- **📝 Scraping** — Extract clean content from any webpage
- **🕷️ Crawling** — Crawl entire websites with smart limits
- **🤖 LLM Extraction** — Extract structured data using AI
- **🌐 Browser Automation** — Interactive page manipulation
- **📊 Batch Processing** — Process multiple URLs efficiently

## Requirements

- Node.js 18+
- Firecrawl API key (get from https://firecrawl.dev)
- Internet access

## Installation

### 1. Get API Key

Sign up at https://firecrawl.dev to get your API key.

### 2. Set Environment Variable

```bash
export FIRECRAWL_API_KEY=fc-your-api-key-here
```

### 3. Run via npx

```bash
npx -y firecrawl-mcp
```

## MCP Configuration

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "firecrawl": {
      "command": "npx",
      "args": ["-y", "firecrawl-mcp"],
      "transport": "stdio",
      "env": {
        "FIRECRAWL_API_KEY": "${FIRECRAWL_API_KEY}"
      }
    }
  }
}
```

## Available Tools

### 1. search

Search the web and extract content from results.

**Example:**
```
Search for "Python web scraping best practices 2026"
```

**Parameters:**
- `query` (string, required): Search query
- `limit` (number, optional): Max results (default: 5)
- `lang` (string, optional): Language code
- `country` (string, optional): Country code

### 2. scrape

Extract clean content from a webpage.

**Example:**
```
Scrape https://example.com/article
```

**Parameters:**
- `url` (string, required): Page URL
- `formats` (array, optional): ["markdown", "html", "rawHtml", "screenshot"]
- `onlyMainContent` (boolean, optional): Extract only main content
- `waitFor` (number, optional): Wait time in ms

### 3. crawl

Crawl entire websites.

**Example:**
```
Crawl https://docs.python.org with depth 2
```

**Parameters:**
- `url` (string, required): Starting URL
- `limit` (number, optional): Max pages (default: 10)
- `maxDepth` (number, optional): Max depth (default: 2)
- `allowExternalLinks` (boolean, optional): Allow external links

### 4. extract

LLM-powered structured data extraction.

**Example:**
```
Extract all products with name, price, rating from https://example.com
```

**Parameters:**
- `urls` (array, required): URLs to extract from
- `prompt` (string, optional): Extraction prompt
- `systemPrompt` (string, optional): System prompt
- `schema` (object, optional): JSON schema for output

### 5. map

Map out website structure.

**Example:**
```
Map https://example.com to discover all pages
```

**Parameters:**
- `url` (string, required): Website URL
- `search` (string, optional): Search pattern
- `ignoreRobotsTxt` (boolean, optional): Ignore robots.txt

### 6. Interactive Browser Tools

- `browser_action` — Execute browser actions (click, type, scroll)
- `browser_screenshot` — Take screenshots
- `browser_wait` — Wait for conditions

## Usage Examples

### Basic Scraping
```
Scrape the main content from https://example.com/blog/post
```

### Search with Extraction
```
Search for "AI browser automation tools" and summarize top 5 results
```

### Structured Extraction
```
Extract product information from https://shop.example.com:
- Product name
- Price
- Rating
- Review count
```

### Website Crawling
```
Crawl https://docs.example.com with max depth 3, extract all API endpoints
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `FIRECRAWL_API_KEY` | Your Firecrawl API key | Yes |
| `FIRECRAWL_BASE_URL` | Self-hosted instance URL | No |
| `FIRECRAWL_TIMEOUT` | Request timeout (ms) | No |

## Cost Optimization

1. **Use `onlyMainContent: true`** - Reduces token usage by ~40%
2. **Choose markdown format** - More compact than HTML
3. **Set appropriate limits** - Don't crawl more than needed
4. **Batch operations** - Process multiple URLs together

## Error Handling

The skill includes automatic retry logic:
- Max attempts: 3
- Initial delay: 1 second
- Max delay: 10 seconds
- Backoff factor: 2x

## Troubleshooting

### API Key Error
```bash
# Ensure API key is set
echo $FIRECRAWL_API_KEY
```

### Rate Limiting
- Implement exponential backoff
- Use batch operations
- Consider upgrading your Firecrawl plan

### Timeout Issues
- Increase timeout settings
- Use `waitFor` for dynamic content
- Try headless mode

## Architecture

```
User Request
    ↓
Hermes Agent
    ↓
Firecrawl MCP Skill
    ↓
Firecrawl MCP Server (npx)
    ↓
Firecrawl API
    ↓
Target Website
```

## References

- Official Docs: https://docs.firecrawl.dev
- GitHub: https://github.com/firecrawl/firecrawl
- npm Package: https://www.npmjs.com/package/firecrawl-mcp
- Firecrawl: https://firecrawl.dev
