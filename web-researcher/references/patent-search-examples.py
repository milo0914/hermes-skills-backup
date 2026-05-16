# Patent Search Code Examples

Working code patterns for searching patent databases using Playwright-based automation.

## Google Patents Search

```python
from playwright.sync_api import sync_playwright
import time
import re

def search_google_patents(query, max_results=15):
    """
    Search Google Patents and extract patent information.
    
    Args:
        query: Search query (e.g., 'assignee:"Merck KGaA" liquid crystal')
        max_results: Maximum number of patents to extract
    
    Returns:
        List of patent dictionaries with number, title, abstract, etc.
    """
    patents = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = context.new_page()
        
        # Navigate to search
        search_url = f"https://patents.google.com/?q={query.replace(' ', '+')}&sort=new"
        page.goto(search_url, wait_until='domcontentloaded', timeout=60000)
        
        # Wait for content to render (critical for JS-heavy sites)
        time.sleep(5)
        
        # Extract patent items
        patent_items = page.query_selector_all('li[role="listitem"]')
        
        for item in patent_items[:max_results]:
            patent = {}
            
            # Patent number from data-id
            link = item.query_selector('a[data-id]')
            if link:
                patent['number'] = link.get_attribute('data-id')
                patent['url'] = link.get_attribute('href')
            
            # Title
            title_elem = item.query_selector('h3, .title')
            if title_elem:
                patent['title'] = title_elem.text_content().strip()
            
            # Abstract
            abstract_elem = item.query_selector('p, .abstract')
            if abstract_elem:
                patent['abstract'] = abstract_elem.text_content().strip()[:500]
            
            if patent:
                patents.append(patent)
        
        browser.close()
    
    return patents

# Usage
results = search_google_patents('Merck KGaA negative dielectric liquid crystal')
```

## Single Patent Detail Extraction

```python
def get_patent_details(patent_id):
    """
    Extract detailed information from a single patent page.
    
    Args:
        patent_id: Patent number (e.g., 'US20260085041A1')
    
    Returns:
        Dictionary with full patent details
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent='Mozilla/5.0')
        page = context.new_page()
        
        url = f"https://patents.google.com/patent/{patent_id}"
        page.goto(url, wait_until='domcontentloaded', timeout=60000)
        
        # Wait for JavaScript rendering
        time.sleep(5)
        
        info = {'number': patent_id, 'url': url}
        
        # Title
        title_elem = page.query_selector('h1')
        if title_elem:
            info['title'] = title_elem.text_content().strip()
        
        # Abstract
        abstract_elem = page.query_selector('[data-label="abstract"] p')
        if abstract_elem:
            info['abstract'] = abstract_elem.text_content().strip()
        
        # Extract table data (assignee, dates, etc.)
        rows = page.query_selector_all('tr')
        for row in rows:
            text = row.text_content().lower()
            cells = row.query_selector_all('td')
            if cells and len(cells) >= 2:
                value = cells[-1].text_content().strip()
                
                if 'assignee' in text or '申請人' in text:
                    info['assignee'] = value
                elif 'filing' in text or '申請' in text:
                    info['filing_date'] = value
                elif 'publication' in text or '公開' in text:
                    info['publication_date'] = value
        
        # Claim 1
        claim1_elem = page.query_selector('ol[data-label="claims"] li:first-child')
        if claim1_elem:
            info['claim1'] = claim1_elem.text_content().strip()
        
        browser.close()
        return info

# Usage
details = get_patent_details('US20260085041A1')
```

## Batch Processing with Error Handling

```python
def process_patent_batch(patent_ids, delay_seconds=2):
    """
    Process multiple patents with rate limiting.
    
    Args:
        patent_ids: List of patent numbers
        delay_seconds: Delay between requests to avoid rate limiting
    
    Returns:
        List of patent details
    """
    results = []
    
    for i, patent_id in enumerate(patent_ids):
        print(f"[{i+1}/{len(patent_ids)}] Processing {patent_id}")
        
        try:
            details = get_patent_details(patent_id)
            results.append(details)
        except Exception as e:
            results.append({'number': patent_id, 'error': str(e)})
        
        # Rate limiting
        time.sleep(delay_seconds)
    
    return results
```

## Key Technical Notes

1. **Wait Strategy**: Google Patents requires `wait_until='domcontentloaded'` plus additional `time.sleep(5)` for full rendering

2. **Selectors**: Use shadow DOM-aware selectors; Google Patents uses web components

3. **Rate Limiting**: Add 2-5 second delays between requests to avoid blocking

4. **Screenshot Debugging**: 
   ```python
   page.screenshot(path=f'/tmp/patent_{patent_id}.png')
   ```

5. **Common Pitfalls**:
   - Simple HTTP fetchers return minimal HTML
   - Must wait for JavaScript execution
   - Patent numbers in URLs may need URL-encoding
   - Some pages redirect to search results if patent not found

## Alternative Databases

### WIPO PATENTSCOPE
```python
url = "https://patentscope.wipo.int/search/en/search.jsf"
# Requires form submission, more complex automation
```

### Espacenet
```python
url = "https://worldwide.espacenet.com/patent/search"
# Also requires JavaScript, similar pattern to Google Patents
```
