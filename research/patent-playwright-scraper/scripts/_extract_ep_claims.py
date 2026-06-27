#!/usr/bin/env python3
"""
提取 EP 類專利 Claims — 針對 <ol class="claims"><li class="claim"> HTML 結構
用法: python _extract_ep_claims.py <url> <patent_id>
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
        
        # 滾動加載
        for pos in range(0, 35000, 1200):
            page.evaluate('window.scrollTo(0, {})'.format(pos))
            page.wait_for_timeout(500)
        page.wait_for_timeout(5000)
        
        # 針對 EP 專利改進的 JS 提取策略
        js_result = page.evaluate("""() => {
            const claims = [];
            
            // 策略1: <ol class="claims"> -> <li class="claim"> (EP 專利常見格式)
            const claimList = document.querySelector('ol.claims, .claims');
            if (claimList) {
                const items = claimList.querySelectorAll('li.claim, li');
                items.forEach((li, idx) => {
                    const text = li.innerText.trim();
                    if (text) claims.push({num: idx + 1, text: text});
                });
            }
            
            // 策略2: <section id="claims"> 內的 claims
            if (claims.length === 0) {
                const claimsSection = document.querySelector('section#claims');
                if (claimsSection) {
                    const allText = claimsSection.innerText || '';
                    // 去掉標題 "Claims (N)"
                    const cleaned = allText.replace(/^Claims\\s*\\(\\d+\\)\\s*/i, '');
                    claims.push({num: 0, text: cleaned});
                }
            }
            
            // 策略3: 找含 "1." 開頭的 div
            if (claims.length === 0) {
                const allDivs = document.querySelectorAll('div.claim, div.claim-text');
                let currentClaim = null;
                allDivs.forEach(div => {
                    const text = div.innerText.trim();
                    if (text) {
                        if (currentClaim === null) {
                            currentClaim = text;
                        } else {
                            currentClaim += ' ' + text;
                        }
                    }
                });
                if (currentClaim) {
                    claims.push({num: 0, text: currentClaim});
                }
            }
            
            return {claims: claims};
        }""")
        
        claims_list = js_result.get('claims', [])
        
        if claims_list and claims_list[0].get('num', 0) > 0:
            # 結構化 claims（每個 li 是一個 claim）
            for claim in claims_list:
                num = claim['num']
                text = re.sub(r'\s+', ' ', claim['text']).strip()
                if num <= 3:
                    result['claim_{}'.format(num)] = text[:2000]
        elif claims_list:
            # 非結構化 claims — 用正則提取
            full_claims = claims_list[0].get('text', '')
            for n in [1, 2, 3]:
                # 匹配 claim N: ... 到 claim N+1 之前
                pat = r'{}\.\s+([\s\S]{{20,5000}}?)(?=\s+{}\.\s|$)'.format(n, n + 1)
                m = re.search(pat, full_claims)
                if m:
                    c = re.sub(r'\s+', ' ', m.group(1)).strip()
                    result['claim_{}'.format(n)] = c[:2000]
        
        print("  c1={} c2={} c3={}".format(
            len(result['claim_1']), len(result['claim_2']), len(result['claim_3'])
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
