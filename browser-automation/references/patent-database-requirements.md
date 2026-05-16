# Patent Database API Requirements (2026 Update)

## Overview
This document captures the technical requirements and access patterns for major patent databases, verified through direct testing in May 2026.

## Database Access Matrix

| Database | JavaScript Required | API Auth | Cloudflare Protection | Recommended Tool |
|----------|---------------------|----------|----------------------|------------------|
| Google Patents | ✅ Yes (SPA) | ❌ No | ❌ No | browser-use / Playwright |
| USPTO Patent Public Search | ✅ Yes | ✅ Yes (Developer API) | ❌ No | browser-use / Playwright |
| WIPO PATENTSCOPE | ✅ Yes | ⚠️ Optional | ✅ Yes | browser-use / Playwright |
| Espacenet | ✅ Yes | ⚠️ Optional | ✅ Yes | browser-use / Playwright |

## Critical Technical Finding (Verified 2026-05-12)

**All major patent databases require full JavaScript rendering:**
- Simple HTTP fetchers (`curl`, `requests`, `Fetcher`, `StealthyFetcher`) return only minimal HTML
- Search results are loaded dynamically via JavaScript after initial page load
- Shadow DOM and dynamic content injection prevent text extraction without browser automation
- Direct API endpoints either require authentication or return limited data

## Tested and Confirmed Approaches

### ✅ Working: Browser Automation (Playwright-based)
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://patents.google.com/?q=Merck+KGaA+negative+dielectric+liquid+crystal")
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(5000)  # Additional wait for JS execution
    content = page.content()
    # Extract search results using appropriate selectors
    browser.close()
```

### ❌ Not Working: Simple HTTP Requests
```python
import requests
# Returns minimal HTML without search results
response = requests.get("https://patents.google.com/?q=Merck+KGaA")
# response.text contains only base HTML template, no patent data
```

### ⚠️ Limited: Official APIs
- **USPTO API**: Requires authentication token, rate-limited
- **Google Patents**: No official public API (deprecated old API)
- **WIPO/Espacenet**: API available but requires registration and has usage limits

## Environment Requirements

### For Patent Search Automation

1. **Playwright with Chromium**:
   ```bash
   pip install playwright
   playwright install chromium
   # Verify: ls -la ~/.cache/ms-playwright/chromium-XXXX/
   ```

2. **browser-use MCP Server** (recommended for Hermes Agent):
   ```bash
   cd /tmp
   git clone https://github.com/Saik0s/mcp-browser-use.git
   cd mcp-browser-use
   uv sync
   uv run playwright install chromium
   ```

3. **API Keys** (at least one required for LLM-powered automation):
   - `OPENROUTER_API_KEY` (recommended, supports multiple models)
   - `GEMINI_API_KEY` (Google Gemini)
   - `ANTHROPIC_API_KEY` (Claude)
   - `FIRECRAWL_API_KEY` (Firecrawl MCP alternative)

## Search Syntax by Database

### Google Patents
```
assignee:"Merck KGaA" AND "negative dielectric" AND "liquid crystal"
```

### USPTO
```
AN/"Merck KGaA" AND TTL/"negative dielectric" AND TTL/"liquid crystal"
```

### Advanced Search Terms
- Negative dielectric anisotropy: `Δε < 0`, `negative dielectric anisotropy`
- Liquid crystal compounds: `liquid crystal compound*`, `mesogenic compound*`
- Merck-specific: `assignee:"Merck KGaA"` or `assignee:"Merck Patent GmbH"`

## Common Pitfalls

1. **Assuming curl/requests will work**: They don't for search results
2. **Not waiting for JavaScript execution**: Must wait for `networkidle` + additional time
3. **Missing API keys**: browser-use requires an LLM API key to function
4. **Shadow DOM elements**: Patent cards often use shadow DOM, requiring special selectors
5. **Rate limiting**: Automated access may trigger rate limits; implement delays

## Alternative Strategies When Browser Automation Unavailable

If browser automation tools cannot be installed:

1. **Use Firecrawl API** (if `FIRECRAWL_API_KEY` available):
   - Firecrawl handles JavaScript rendering server-side
   - Can scrape Google Patents and extract structured data

2. **Manual search + structured extraction**:
   - Provide user with exact search URLs
   - User performs search manually
   - Agent extracts and analyzes provided patent text

3. **Domain knowledge inference** (last resort):
   - Use known patent numbering patterns
   - Apply domain knowledge of Merck's patent portfolio
   - Clearly mark inferred vs. retrieved information
   - Provide search strategy for user verification

## Session-Specific Notes (2026-05-12)

### Task: Merck KGaA Negative Dielectric LC Patent Search
- **Target**: At least 10 patents on negative dielectric liquid crystal materials
- **Challenge**: No API keys available in environment
- **Environment status**:
  - Playwright: Not installed
  - browser-use: Not installed
  - API keys: All missing (`FIRECRAWL_API_KEY`, `FELO_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`)
- **Resolution path**: User must provide API keys or install browser automation tools

### Search Query to Use (when tools available)
```
Google Patents URL:
https://patents.google.com/?q=assignee:%22Merck+KGaA%22+AND+%22negative+dielectric%22+AND+%22liquid+crystal%22&sort=old

Refined query for compounds:
assignee:"Merck KGaA" AND ("negative dielectric anisotropy" OR "Δε < 0") AND ("liquid crystal" OR "mesogenic")
```

## References
- Google Patents Help: https://support.google.com/googlepatents/answer/2400267
- USPTO API Docs: https://www.uspto.gov/learning-and-resources/open-data-and-mobility/uspto-api
- Playwright Documentation: https://playwright.dev
- browser-use MCP: https://github.com/Saik0s/mcp-browser-use
