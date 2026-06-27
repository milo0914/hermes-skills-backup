# Patent Research Session Notes (2026-05-20)

## Session Summary
**Task**: Merck KGaA negative dielectric liquid crystal patent research (2020-2026)  
**Approach**: GRPO planning + Crawl4AI alternative to Firecrawl  
**Result**: Partial success - Claim 1 extraction improved, but date range control failed

## Key Findings

### What Worked
1. **Crawl4AI Installation**: Successfully installed and tested as Firecrawl alternative
   - No credit limits
   - Returns markdown format
   - Works for patent detail pages

2. **Claim 1 Extraction**: Improved regex-based extraction
   - 50% success rate (4/8 patents)
   - Handles multiple formats ("1.", "1:", "1 ")
   - Extracts 664-3450 characters

3. **Technical Features**: Extracted from Abstract/Technical Field
   - Up to 5 features per patent
   - Keyword-based filtering

### What Failed
1. **Date Range Control**: 0/8 patents in 2020-2026 range
   - Root cause: Old search results (2008-2010 patents)
   - Google Patents dynamic loading prevents Crawl4AI scraping
   - Firecrawl search() doesn't support date syntax

2. **Example Extraction**: 1/8 success rate
   - Examples scattered in Description
   - No consistent heading format
   - Need better paragraph detection

3. **Google Patents Search**: Crawl4AI returns 0 results
   - Search results loaded via JavaScript
   - Crawl4AI only captures initial HTML (search form)
   - Need API-based approach

## Files Generated
- `/data/.hermes/skills/research/patent-research-workflow/scripts/patent_search_v4_crawl4ai.py`
- `/data/.hermes/skills/research/patent-research-workflow/scripts/patent_extract_v4_crawl4ai.py`
- `/tmp/patent_research_improvement_report_v4.md`
- `/tmp/extracted_patents_v4.json`

## Lessons Learned
1. **Crawl4AI is viable Firecrawl alternative** for patent extraction (no credit limits)
2. **Google Patents dynamic content cannot be scraped** - need API approach
3. **Date range must be controlled at search stage**, not post-filtering
4. **Claim 1 extraction needs multiple regex patterns** for different patent formats
5. **Example extraction requires LLM or more sophisticated parsing**

## Next Steps
1. Use USPTO API for date-range controlled search
2. Improve example extraction with LLM
3. Consider professional databases (PatSnap, Derwent) for production use
