#!/usr/bin/env python3
"""
提取單篇專利的 Claims + Description — 獨立腳本避免 f-string dict 問題
用法: python _extract_single_patent.py <url> <patent_id>
"""
import sys
import json
import re
from playwright.sync_api import sync_playwright

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)

def main():
    url = sys.argv[1]
    pid = sys.argv[2]
    
    result = {
        'claim_1': '',
        'claim_2': '',
        'claim_3': '',
        'description': '',
        'abstract': '',
        'title': '',
        'patent_number': ''
    }
    
    browser = None
    try:
        p = sync_playwright().start()
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        page = browser.new_page()
        page.set_extra_http_headers({
            'User-Agent': USER_AGENT,
            'Accept-Language': 'en-US,en;q=0.9',
        })
        page.goto(url, wait_until='domcontentloaded', timeout=60000)
        
        try:
            page.wait_for_load_state('networkidle', timeout=15000)
        except Exception:
            pass
        
        # 多滾動
        for pos in range(0, 35000, 1200):
            page.evaluate('window.scrollTo(0, {})'.format(pos))
            page.wait_for_timeout(500)
        page.wait_for_timeout(5000)
        
        # 改進的 JS 提取
        js_result = page.evaluate("""() => {
            const output = {
                claims: '',
                description: '',
                abstract: '',
                title: '',
                patentNumber: ''
            };
            
            // 方法1: 找包含 claims 的 section
            const sections = document.querySelectorAll('section, article, div');
            for (const el of sections) {
                const text = el.innerText || '';
                if (text.match(/^1\\.\\s/m) && text.length > 300 && text.length < 150000 &&
                    (text.includes('claim') || text.includes('comprising') || text.includes('according to'))) {
                    if (output.claims.length === 0 || text.length < output.claims.length * 1.5) {
                        output.claims = text;
                    }
                }
                
                if ((text.includes('[0001]') || text.includes('[0002]') || text.includes('BACKGROUND')) &&
                    text.length > output.description.length && text.length < 500000) {
                    output.description = text;
                }
            }
            
            // 方法2: 找 itemprop="claims" 或 .claims
            if (!output.claims) {
                const claimElements = document.querySelectorAll('[itemprop="claims"], .claims, #claims, claims');
                for (const el of claimElements) {
                    const text = el.innerText || '';
                    if (text.length > 100) {
                        output.claims = text;
                        break;
                    }
                }
            }
            
            // 方法3: 找 patent-text 元素
            if (!output.claims) {
                const patTexts = document.querySelectorAll('patent-text, .patent-text, .claim');
                for (const el of patTexts) {
                    const text = el.innerText || '';
                    if (text.match(/^1\\./m) && text.length > 100) {
                        output.claims = text;
                        break;
                    }
                }
            }
            
            // 方法4: 嘗試從所有 text 中找 claims 區域
            if (!output.claims) {
                const allText = document.body.innerText || '';
                const claimsMatch = allText.match(/Claims[\\s\\S]{50,80000}(?:Description|Classifications|Citations|$)/i);
                if (claimsMatch) {
                    output.claims = claimsMatch[0].substring(0, 80000);
                }
            }
            
            // Abstract
            const absEls = document.querySelectorAll('[itemprop="abstract"], .abstract, #abstract, abstract');
            for (const el of absEls) {
                const text = el.innerText || '';
                if (text.length > 30 && text.length < 5000) {
                    output.abstract = text.replace(/^Abstract\\s*/i, '').trim();
                    break;
                }
            }
            
            // Title
            const titleEl = document.querySelector('h1, [itemprop="title"], invention-title');
            if (titleEl) output.title = titleEl.textContent.trim().substring(0, 200);
            
            // Patent number
            const urlMatch = window.location.href.match(/patent\\/([A-Z]{2}\\d+[A-Z]?\\d?)/i);
            if (urlMatch) output.patentNumber = urlMatch[1].toUpperCase();
            
            output.description = output.description.substring(0, 500000);
            output.claims = output.claims.substring(0, 80000);
            output.abstract = output.abstract.substring(0, 3000);
            
            return output;
        }""")
        
        result['abstract'] = js_result.get('abstract', '')
        result['description'] = js_result.get('description', '')
        result['title'] = js_result.get('title', '')
        result['patent_number'] = js_result.get('patentNumber', '')
        
        claims_text = js_result.get('claims', '')
        
        # 提取 Claim 1-3
        for n in [1, 2, 3]:
            pat = r'(?:^|\n)\s*{}{}\s+([\s\S]{{20,5000}}?)(?=\n\s*{}{}\s|$)'.format(
                n, r'\.', n + 1, r'\.'
            )
            m = re.search(pat, claims_text)
            if m:
                c = re.sub(r'\s+', ' ', m.group(1)).strip()
                result['claim_{}'.format(n)] = c[:2000]
        
        # 統計
        print("  desc={} c1={} c2={} abs={}".format(
            len(result['description']),
            len(result['claim_1']),
            len(result['claim_2']),
            len(result['abstract'])
        ), flush=True)
        
        print(json.dumps(result, ensure_ascii=False))
        
    except Exception as e:
        print("ERROR: {}".format(e), file=sys.stderr)
        sys.exit(1)
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass


if __name__ == '__main__':
    main()
