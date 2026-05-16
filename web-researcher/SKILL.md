---
name: web-researcher
description: Advanced web research — search, extract, and synthesize information from multiple sources. Use when the user needs research, fact-checking, competitive analysis, or information gathering.
version: "1.0.0"
license: MIT
compatibility: Works with all Hermes backends. Optional TAVILY_API_KEY for enhanced results.
metadata:
  author: hermeshub
  hermes:
    tags: [research, web-search, extraction, summarization]
    category: research
    fallback_for_toolsets: [web]
required_environment_variables:
  - name: TAVILY_API_KEY
    prompt: Tavily API key (optional, enhances search quality)
    help: Get a free key at https://tavily.com
    required_for: enhanced search quality
---

# Web Researcher

Multi-source research agent with structured synthesis.

## Support Files
- `references/patent-search-strategy.md` — Strategies and limitations for patent database searches (USPTO, Google Patents, WIPO)
- `references/patent-search-examples.py` — Working code examples for patent database automation

## When to Use
- User asks to research a topic, company, person, or technology
- User needs competitive analysis or market research
- User wants fact-checking or source verification
- User needs summarized information from multiple web sources

## Procedure
1. Parse the research query to identify key topics and constraints
2. Generate 3-5 diverse search queries covering different angles
3. Execute searches in parallel using available search tools
4. For each promising result, extract the full page content
5. Cross-reference facts across multiple sources
6. Synthesize findings into a structured report with citations
7. Flag any conflicting information between sources

### Patent Search Specific Procedure\nWhen the research task involves patent analysis:\n1. **Attempt direct API access first** (USPTO API, Google Patents API)\n2. **If API fails due to JavaScript requirements**, use `DynamicFetcher` (Playwright-based) for interactive search\n3. **Critical**: All major patent databases (Google Patents, USPTO, WIPO PATENTSCOPE, Espacenet) require full JavaScript rendering - simple HTTP fetchers will fail\n4. **Wait strategy**: Use `wait_until='domcontentloaded'` plus 5-10 seconds additional wait for content rendering\n5. **Document limitations** when original documents cannot be fully accessed\n6. **Structure the report** following the template in `references/patent-search-strategy.md`\n7. **Clearly distinguish** between retrieved information and domain-knowledge inferences\n8. **Provide search strategy** so users can verify by re-running the search

## Research Output Format
```markdown
# Research: [Topic]

## Key Findings
- Finding 1 (Source: [url])
- Finding 2 (Source: [url])

## Detailed Analysis
[Structured analysis with inline citations]

## Sources
1. [Title](url) - Relevance: High/Medium/Low
2. [Title](url) - Relevance: High/Medium/Low

## Confidence & Gaps
- Confidence: High/Medium/Low
- Information gaps: [what couldn't be verified]
```

## Pitfalls\n- Always cite sources — never present research without attribution\n- Cross-reference claims across at least 2 sources\n- Note when information is from a single source only\n- Be explicit about information freshness and publication dates\n- Distinguish between facts, analysis, and speculation\n- **Patent search specific**: \n - All major patent databases (Google Patents, USPTO, WIPO PATENTSCOPE, Espacenet) require full JavaScript rendering\n - Simple HTTP fetchers (`Fetcher`, `StealthyFetcher`) return minimal HTML without JavaScript execution\n - Must use `DynamicFetcher` (Playwright-based) with proper wait strategies\n - Wait for `networkidle` or `domcontentloaded` plus 5-10 seconds for full content rendering\n - When original documents cannot be retrieved, clearly distinguish between information from actual retrieval vs. domain knowledge inference\n- **Environment readiness check (CRITICAL)**: Before starting patent search, verify:\n - Playwright/Chromium is installed: `playwright --version` or check `~/.cache/ms-playwright/`\n - Required API keys are set: `FIRECRAWL_API_KEY`, `FELO_API_KEY`, `OPENROUTER_API_KEY`, or `GEMINI_API_KEY`\n - If using browser-use MCP: `uv` is in PATH, server is running\n - If no browser automation tools available, inform user immediately rather than attempting futile curl requests

## Verification
- Every claim should have at least one source URL
- Key facts should be cross-referenced across sources
- Report should explicitly state confidence level
