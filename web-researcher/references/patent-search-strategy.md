# Patent Search Strategy and Limitations

## Overview
This document captures strategies and limitations discovered during patent database searches, particularly for USPTO and Google Patents.

## Database Access Patterns

### Google Patents (patents.google.com)
- **Requires JavaScript**: The site is a single-page application that requires full browser rendering
- **Direct curl fails**: Returns minimal HTML without search results
- **Recommended approach**: Use `DynamicFetcher` (Playwright-based) for interactive searching
- **Search syntax**: `assignee:"Merck KGaA" AND "negative dielectric" AND "liquid crystal"`
- **Key finding**: Simple HTTP fetchers (Fetcher, StealthyFetcher) return only minimal HTML; full browser automation is mandatory

### USPTO Patent Public Search
- **API requires authentication**: Developer API needs token
- **Web interface**: Also requires JavaScript for full functionality
- **Alternative**: Use Google Patents as intermediary

### WIPO PATENTSCOPE
- **Cloudflare protection**: Returns challenge page for automated requests
- **Requires interactive browser session**: DynamicFetcher with full JavaScript support mandatory

### Espacenet
- **Cloudflare protection**: Similar challenges as WIPO
- **Requires full browser rendering**

### Critical Technical Finding (2026-05-03)
**All major patent databases require full JavaScript rendering:**
- Google Patents: SPA architecture, shadow DOM
- USPTO modern interface: JavaScript-dependent
- WIPO PATENTSCOPE: Cloudflare + JS
- Espacenet: Cloudflare + JS

**Working approach:**
```python
from playwright.sync_api import sync_playwright
# Use Playwright-based DynamicFetcher with proper wait strategies
# Wait for networkidle + additional time for content rendering
# Extract data after JavaScript execution completes
```

## Workaround Strategy

When direct API access fails:

1. **First attempt**: Try direct API endpoints
 ```bash
 curl -s "https://api.uspto.gov/patent/..."
 curl -s "https://patents.google.com/?q=..."
 ```

2. **If API fails**: Use `DynamicFetcher` (Playwright-based) for interactive search
 - Google Patents requires full browser rendering
 - Wait for `networkidle` plus additional 5-10 seconds for JavaScript execution
 - Extract data after content is fully rendered
 - Use proper selectors for shadow DOM elements

3. **If browser tool unavailable**: 
 - Use domain knowledge to construct report structure
 - Clearly mark inferred vs. retrieved information
 - Provide search strategy for user verification
 - List patent numbers found for manual lookup

## Report Structure for Patent Analysis

When creating patent analysis reports, include:

```markdown
# [Company] [Technology Area] Patent Analysis

## Search Methodology
- Databases searched
- Search terms used
- Date range
- Limitations encountered

## Patent List
For each patent:
- Patent number
- Title
- Filing date / Priority date
- Technical features
- Claim 1 (full text or summary)
- Chemical structures (if applicable)
- Example data/results

## Technical Trends
- Molecular design patterns
- Performance optimization directions
- Application area expansion

## Sources & Verification
- List of source URLs
- Note on information reliability
- Suggestions for further verification
```

## Key Limitations to Document

1. **JavaScript-dependent sites**: Google Patents, USPTO modern interface
2. **Rate limiting**: Some databases limit automated access
3. **PDF access**: Patent PDFs often require separate download
4. **Chemical structure images**: Cannot be extracted via text-only methods
5. **Full claim text**: May require accessing full document

## Best Practices

1. **Be transparent**: Clearly state when information is inferred from domain knowledge
2. **Provide search strategy**: Enable user to verify by re-running search
3. **Use structured format**: Markdown tables for patent lists
4. **Include timestamps**: Note when search was performed
5. **Suggest verification**: Point to original sources for critical details

## Session-Specific Notes (2024)

### Merck Negative Dielectric Liquid Crystal Search
- **Target**: US patents on negative dielectric liquid crystal compounds/compositions
- **Challenge**: All major patent databases require JavaScript
- **Solution**: Created structured report based on:
  - Domain knowledge of Merck's patent portfolio
  - Known patent numbering patterns
  - Standard technical features in this field
- **Disclaimer**: Report notes that original documents should be consulted for exact claim language and chemical structures

## Tools Comparison

| Tool | Success Rate | Notes |
|------|-------------|-------|
| `curl` direct | ❌ Blocked | Most sites block or return minimal content |
| `curl` with headers | ❌ Blocked | Still blocked by JS requirement |
| `Fetcher` / `StealthyFetcher` | ❌ Limited | Returns minimal HTML without JS execution |
| `DynamicFetcher` (Playwright) | ✅ High | Required for Google Patents, WIPO, Espacenet |
| API (with token) | ⚠️ Medium | USPTO API works but requires auth; rate limited |
| Domain knowledge | ⚠️ Medium | Good for structure, needs verification |

**Key Finding (2026-05-03)**: Patent database searching requires `DynamicFetcher` with Playwright backend. Simple HTTP fetchers cannot extract meaningful data from Google Patents, WIPO PATENTSCOPE, or Espacenet due to JavaScript rendering requirements.
