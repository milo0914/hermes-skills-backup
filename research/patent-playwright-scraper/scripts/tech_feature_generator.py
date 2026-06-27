#!/usr/bin/env python3
"""
技術特點 LLM 摘要生成器 — patent-playwright-scraper v1.2.0

從 Google Patents 提取結構化段落（Background/Summary/Claim1/Claim2/Examples），
然後由 LLM 生成 5 維度技術特點摘要。

使用方式：
  python tech_feature_generator.py --url "https://patents.google.com/patent/US20250284151A1/en"
  python tech_feature_generator.py --json /path/to/extracted_patents.json
  python tech_feature_generator.py --test   # 用內建測試專利驗證
"""

import re
import json
import argparse
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# ========== 常量 ==========

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)

# Description 標題匹配模式（不限於段落號之後）
HEADING_PATTERNS = [
    r'BACKGROUND\s+(?:OF\s+)?THE\s+INVENTION',
    r'SUMMARY\s+(?:OF\s+)?THE\s+INVENTION',
    r'DETAILED\s+DESCRIPTION\s+(?:OF\s+)?(?:THE\s+)?(?:PREFERRED\s+)?(?:EMBODIMENTS?\s+)?(?:OF\s+)?(?:THE\s+)?INVENTION?',
    r'FIELD\s+(?:OF\s+)?(?:THE\s+)?INVENTION',
    r'TECHNICAL\s+FIELD',
    r'PRIOR\s+ART',
    r'CROSS-REFERENCE\s+TO\s+RELATED\s+APPLICATIONS',
    r'DISCLOSURE\s+OF\s+THE\s+INVENTION',
]

# LLM Prompt 模板
TECH_FEATURE_PROMPT_TEMPLATE = """請根據以下專利文件內容，融會理解後撰寫一份具有「判斷性與洞見」的技術要點摘要。

⚠️ 關鍵要求：每個維度的內容必須是你對提取資料的融會理解與分析判斷，而非簡單的項目標題或關鍵詞列舉。
❌ 錯誤示範（流水線式、無洞見）：
  - 提升透射率
  - 改善對比度（contrast ratio）
  - 維持電壓保持率（VHR）
✅ 正確示範（融會理解、有判斷）：
  現有 VA 模式液晶介質在追求高 |Δε| 時，常伴隨旋轉粘度 γ1 上升及低溫穩定性下降的取捨困境。本發明通過將含 CF₂O/OCF₂ 連接基的式 I 化合物與特定共混組分（式 IIA-IID）組合，在維持 |Δε|≥3.0 的同時將 γ1 控制在 100 mPa·s 以下，並確保 −20°C 低溫下無結晶析出，突破了先前技術中負介電與低粘度不可兼得的瓶頸。

必須包含以下 5 個維度，每項撰寫 1-2 段連貫論述：

1. **解決的問題**：從 Background 推導出此專利針對的現有技術缺陷的本質，說明該問題為何重要、其技術根因是什麼，而非僅複述「現有技術有缺陷」。需指出具體的參數矛盾或性能取捨困境。
2. **核心發明**：從 Summary + Claim 1 綜合判斷此專利的主要技術貢獻，說明其創新機制（如特定化學結構組合如何突破前述困境），而非僅列出「包含 Formula X 化合物」。
3. **關鍵技術特徵**：從 Claim 2 提取進一步限定的技術特徵，分析這些限定如何收窄發明範圍、為何如此限定（對性能的影響），而非僅抄錄從屬項文字。
4. **實施方式**：從實施例提取具體化合物/組成物/方法/性能參數，分析配方設計邏輯（如核心化合物與稀釋化合物的配比策略），而非僅列出數據表。
5. **與先前技術的差異**：從 Background + Summary 推導相較於 Prior Art 的改進，需說明改進的定量或定性幅度及背後的物理/化學原理，而非僅說「優於先前技術」。

格式要求：
- 每項至少 30 字的連貫論述（不要用 bullet point 列舉），總長至少 150 字
- 使用繁體中文撰寫
- 嚴格基於提供的文件內容，不要推測或編造未提及的技術內容
- 如某段落未提取到，標註「[未提取到 N 段落，無法判斷]」，但其餘維度仍應給出洞見
- 語氣應如專利分析師的專業意見，具有判斷性和洞察力

---

**Abstract**: {abstract}

**Background of the Invention**:
{background}

**Summary of the Invention**:
{summary}

**Claim 1**:
{claim_1}

**Claim 2**:
{claim_2}

**重要實施例**:
{examples}

---

請融會理解以上內容，撰寫具有判斷性與洞見的技術要點摘要。"""


# ========== 段落提取函數 ==========

def split_description_sections(text: str) -> Dict[str, str]:
    """
    將 Description 文本按標題行分割為 background/summary/detailed/prior_art。

    策略：
    1. 先用正則找所有「標題行 + 後續段落」的邊界
    2. 根據標題名歸類到 background/summary/detail
    3. 段落號 [NNNN] 僅作為內容標記，不依賴它定位標題

    陷阱處理：
    - 已授權專利(B2)的「BACKGROUND OF THE INVENTION」是獨立行標題
    - 公開申請(A1)的標題可能嵌在段落號 [NNNN] 的文字中
    - 兩種情況都用正則匹配標題行位置，再分段
    """
    sections = {
        'background': '',
        'summary': '',
        'detailed': '',
        'prior_art': '',
    }

    # 找所有標題行的位置
    # 陷阱：只在 Description 前 50000 字搜索標題行，
    #       避免匹配到內文中的 "prior art" 等零散詞彙
    #       標題行必須：出現在行首(^)，或緊跟在 \n 之後
    search_text = text[:50000]
    heading_positions = []
    for pat in HEADING_PATTERNS:
        # 加上行首/換行後的錨定
        anchored_pat = r'(?:^|\n)\s*' + pat
        for m in re.finditer(anchored_pat, search_text, re.IGNORECASE):
            heading_positions.append((m.start(), m.group().upper()))

    # 按位置排序
    heading_positions.sort(key=lambda x: x[0])

    if not heading_positions:
        # 沒找到標題行 — 嘗試啟發式分段
        # Merck 液晶專利常見格式：無標題行，Background/Summary 
        # 靠段落號範圍和內容特徵詞推斷
        result = _split_by_heuristics(text)
        if result['background'] or result['summary']:
            return result
        # 最終回退：段落號匹配
        return _split_by_paragraph_numbers(text)

    # 分段
    for idx, (pos, heading) in enumerate(heading_positions):
        end_pos = (
            heading_positions[idx + 1][0]
            if idx + 1 < len(heading_positions)
            else min(pos + 50000, len(text))
        )
        section_text = text[pos:end_pos].strip()

        heading_upper = heading.upper()
        if 'BACKGROUND' in heading_upper:
            sections['background'] = section_text[:5000]
        elif 'DISCLOSURE' in heading_upper or 'SUMMARY' in heading_upper:
            sections['summary'] = section_text[:4000]
        elif 'DETAILED DESCRIPTION' in heading_upper:
            sections['detailed'] = section_text[:3000]
        elif 'PRIOR ART' in heading_upper:
            sections['prior_art'] = section_text[:3000]

    return sections


def _split_by_heuristics(text: str) -> Dict[str, str]:
    """
    啟發式分段：當標題行匹配失敗時，根據段落號範圍和內容特徵詞推斷。

    Merck 液晶專利常見格式（無標題行）：
    - [0001]-[0020]：Background（描述現有技術、VA/IPS/FFS 顯示模式問題）
    - [0021]：過渡段 "The invention is based on the object of..."
    - [0022]-[0039]：Summary（核心發明、化合物結構）
    - [0040]+：Detailed Description（實施方式、應用）

    策略：
    1. 找「過渡段」— 含 "invention is based on the object" 或
       "Surprisingly, it has now been found" 的段落號
    2. 過渡段之前 = Background
    3. 過渡段之後到下一個特徵變化 = Summary
    4. Summary 之後 = Detailed
    """
    sections = {
        'background': '',
        'summary': '',
        'detailed': '',
        'prior_art': '',
    }

    segments = re.split(r'\[(\d{4,5})\]\s*', text)

    if len(segments) < 4:
        return sections

    # 建構段落列表：[(para_num, para_text), ...]
    paragraphs = []
    for i in range(1, len(segments) - 1, 2):
        para_num = int(segments[i])
        para_text = segments[i + 1].strip() if i + 1 < len(segments) else ''
        paragraphs.append((para_num, para_text))

    if not paragraphs:
        return sections

    # 尋找過渡段
    transition_idx = None
    TRANSITION_PATTERNS = [
        r'invention\s+is\s+based\s+on\s+the\s+object',
        r'Surprisingly,\s+it\s+has\s+now\s+been\s+found',
        r'Accordingly,\s+it\s+is\s+an\s+object',
        r'The\s+present\s+invention\s+provides',
        r'it\s+is\s+an\s+object\s+of\s+the\s+present\s+invention',
        r'The\s+invention\s+relates\s+to\s+a\s+liquid\s+crystal\s+medium\s+comprising',
    ]

    for idx, (num, ptext) in enumerate(paragraphs):
        for pat in TRANSITION_PATTERNS:
            if re.search(pat, ptext, re.IGNORECASE):
                transition_idx = idx
                break
        if transition_idx is not None:
            break

    if transition_idx is None:
        # 找不到過渡段 — 嘗試用段落號推斷
        # 如果段落號從 1 開始且總數 > 30，假設前 20 段是 Background
        if len(paragraphs) > 30 and paragraphs[0][0] <= 2:
            transition_idx = min(20, len(paragraphs) // 3)
        else:
            return sections

    # 過渡段之前 = Background
    bg_parts = [ptext for _, ptext in paragraphs[:transition_idx]]
    sections['background'] = '\n'.join(bg_parts)[:5000]

    # 過渡段開始 = Summary（到段落號跳躍或內容特徵變化）
    sum_parts = []
    for idx in range(transition_idx, min(transition_idx + 20, len(paragraphs))):
        num, ptext = paragraphs[idx]
        # 如果出現 "The invention furthermore relates to" 表示進入 Detailed
        if idx > transition_idx and re.search(
            r'The\s+invention\s+furthermore\s+relates\s+to',
            ptext, re.IGNORECASE
        ):
            break
        # 如果段落號跳躍 > 5（如 [0039]→[0040] 但 [0022]→[0040] 不合理）
        if idx > transition_idx + 1 and num > paragraphs[idx - 1][0] + 10:
            break
        sum_parts.append(ptext)

    sections['summary'] = '\n'.join(sum_parts)[:4000]

    return sections


def _split_by_paragraph_numbers(text: str) -> Dict[str, str]:
    """
    回退方案：按段落號 [NNNN] 分割 Description。

    用於標題行匹配和啟發式分段都失敗時。
    """
    sections = {
        'background': '',
        'summary': '',
        'detailed': '',
        'prior_art': '',
    }

    segments = re.split(r'\[(\d{4,5})\]\s*', text)

    bg_parts = []
    sum_parts = []
    mode = 'pre'

    for i in range(1, len(segments) - 1, 2):
        para_text = segments[i + 1].strip() if i + 1 < len(segments) else ''

        if mode == 'pre':
            if 'BACKGROUND' in para_text.upper():
                mode = 'bg'
                continue

        if mode == 'bg':
            if 'SUMMARY' in para_text.upper() or 'DISCLOSURE' in para_text.upper():
                mode = 'summary'
                continue
            bg_parts.append(para_text)
            if len(bg_parts) > 30:
                mode = 'skip'

        if mode == 'summary':
            if 'DETAILED DESCRIPTION' in para_text.upper():
                mode = 'detail'
                continue
            sum_parts.append(para_text)
            if len(sum_parts) > 20:
                mode = 'detail'

    sections['background'] = '\n'.join(bg_parts)[:5000]
    sections['summary'] = '\n'.join(sum_parts)[:4000]
    return sections



def _extract_ep_claims_dom(page) -> Dict[str, str]:
    """
    EP 專利 Claims DOM 提取 — 針對 <ol class="claims"><li class="claim"> HTML 結構。
    當正則提取 claim_1 失敗時調用（EP 專利 Google Patents 頁面使用列表結構而非純文字）。
    
    移植自 scripts/_extract_ep_claims.py，整合到 tech_feature_generator.py 中，
    使 EP 專利無需獨立腳本即可正確提取 Claims。
    
    參見 SKILL.md 陷阱 24: EP 類專利 Claims 提取 — 需用 DOM 策略而非正則
    
    參數:
        page: Playwright page 物件（已加載專利頁面）
    
    返回:
        {'claim_1': str, 'claim_2': str, 'claim_3': str}
    """
    result = {'claim_1': '', 'claim_2': '', 'claim_3': ''}
    
    try:
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
            
            // 策略2: <section id="claims"> (回退)
            if (claims.length === 0) {
                const claimsSection = document.querySelector('section#claims');
                if (claimsSection) {
                    const allText = claimsSection.innerText || '';
                    const cleaned = allText.replace(/^Claims\\s*\\(\\d+\\)\\s*/i, '');
                    claims.push({num: 0, text: cleaned});
                }
            }
            
            // 策略3: div.claim / div.claim-text
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
                pat = r'{}\.\s+([\s\S]{{20,5000}}?)(?=\s+{}\.\s|$)'.format(n, n + 1)
                m = re.search(pat, full_claims)
                if m:
                    c = re.sub(r'\s+', ' ', m.group(1)).strip()
                    result['claim_{}'.format(n)] = c[:2000]
    
    except Exception as e:
        print(f"  EP DOM 提取回退失敗: {e}")
    
    return result

def _extract_ep_description_fallback(page) -> Dict:
    """
    EP 專利 Description 回退提取 -- 當 JS evaluate 的 description 為空時，
    使用 page.inner_text('body') 全文提取，再用正則分段。

    根因：Google Patents 對 EP 專利的 section DOM 結構與 US 專利不同，
    JS evaluate 的 section 選擇器可能無法匹配 EP 的 Description section，
    導致 description=''。

    參見 SKILL.md 陷阱 20（inner_text 200K+ chars 深度提取）
    和陷阱 27（EP description=0 時的回退策略）。

    參數:
        page: Playwright page 物件（已加載專利頁面）

    返回:
        {'description': str, 'description_len': int, 'examples': list,
         'background': str, 'summary': str}
    """
    result = {
        'description': '',
        'description_len': 0,
        'examples': [],
        'background': '',
        'summary': '',
    }

    try:
        # ---- 策略 1: div.description 精確定位 ----
        desc = page.evaluate("""() => {
            const el = document.querySelector('div.description');
            if (el) return el.innerText;
            // 策略 2: publication-body 區塊遍歷
            const divs = document.querySelectorAll('div.publication-body > div');
            for (const d of divs) {
                if (d.className && d.className.toLowerCase().includes('description')) {
                    return d.innerText;
                }
            }
            return '';
        }""")

        if desc and len(desc) > 100:
            result['description'] = desc[:300000]
            result['description_len'] = len(desc)
        else:
            # ---- 策略 3: inner_text('body') + 正則分段 ----
            body = page.inner_text('body')
            if not body or len(body) < 200:
                return result

            desc_m = re.search(r'Description\n([\s\S]{200,}?)\nClaims', body)
            if desc_m:
                desc = desc_m.group(1).strip()
            else:
                # 找 [0001] 開始到 Claims 之前
                para_m = re.search(r'\[0001\]([\s\S]{200,}?)\n(?:Claims|Classifications)', body)
                if para_m:
                    desc = para_m.group(0).strip()
                else:
                    claims_idx = body.find('Claims')
                    if claims_idx > 1000:
                        desc_start = body.find('[0001]')
                        if desc_start < 0:
                            desc_start = body.find('Description\n')
                            if desc_start >= 0:
                                desc_start += len('Description\n')
                        if 0 <= desc_start < claims_idx:
                            desc = body[desc_start:claims_idx].strip()
                        else:
                            desc = ''
                    else:
                        desc = ''

            if desc:
                result['description'] = desc[:300000]
                result['description_len'] = len(desc)

        # ---- 從提取到的 description 中提取實施例 ----
        if result['description']:
            example_pattern = (
                r'(?:Example|EXAMPLE|Beispiel|Mixture\s+Example)\s*[A-Z]?\d+[.:]?\s*'
                r'[\s\S]{30,2000}?(?=(?:Example|EXAMPLE|Beispiel|Mixture\s+Example)\s*[A-Z]?\d+|$)'
            )
            examples = re.findall(example_pattern, result['description'], re.IGNORECASE)
            result['examples'] = [ex.strip()[:1500] for ex in examples[:5]]

        # ---- EP 格式分段：從 description 中提取 background 和 summary ----
        if result['description']:
            desc_text = result['description']

            # EP 專利分段標記（放寬匹配：不要求行首錨定）
            bg_start = -1
            sm_start = -1

            # 搜尋 background/prior art 標記
            for marker in [r'PRIOR\s+ART', r'Background\s+(?:of\s+)?(?:the\s+)?Invention',
                          r'Description\s+of\s+the\s+Related\s+Art', r'Stand\s+der\s+Technik']:
                m = re.search(marker, desc_text, re.IGNORECASE)
                if m and (bg_start < 0 or m.start() < bg_start):
                    bg_start = m.start()

            # 搜尋 summary/disclosure 標記或過渡段
            for marker in [r'Summary\s+of\s+(?:the\s+)?Invention', r'Disclosure\s+of\s+(?:the\s+)?Invention',
                          r'object\s+of\s+(?:the\s+)?present\s+invention',
                          r'Surprisingly,?\s+it\s+has\s+now\s+been\s+found',
                          r'The\s+present\s+invention\s+provides']:
                m = re.search(marker, desc_text, re.IGNORECASE)
                if m and (sm_start < 0 or m.start() < sm_start):
                    sm_start = m.start()

            # 根據標記分段
            if bg_start >= 0 and sm_start > bg_start:
                result['background'] = desc_text[bg_start:sm_start].strip()[:5000]
                result['summary'] = desc_text[sm_start:sm_start+4000].strip()
            elif sm_start >= 0:
                # 只有過渡段，之前全部作為 background
                result['background'] = desc_text[:sm_start].strip()[:5000]
                result['summary'] = desc_text[sm_start:sm_start+4000].strip()
            elif bg_start >= 0:
                # 只有 PRIOR ART 標記
                result['background'] = desc_text[bg_start:bg_start+5000].strip()
                # summary 取 background 之後 4000 chars
                after_bg = bg_start + len(result['background'])
                if after_bg < len(desc_text):
                    result['summary'] = desc_text[after_bg:after_bg+4000].strip()
            else:
                # 無任何標記 — 取前 5000 chars 作為 background
                result['background'] = desc_text[:5000].strip()
                result['summary'] = desc_text[5000:9000].strip()

    except Exception as e:
        print(f"  EP Description inner_text 回退失敗: {e}")

    return result



def determine_dielectric_type(sections: Dict) -> Dict:
    """
    從 sections 判定正/負介電各向異性。

    優先從 description 計數 neg/pos 關鍵字；
    description 為空時回退至 abstract + background + summary。

    參見 SKILL.md 陷阱 13（neg/pos 關鍵字計數法）和陷阱 27（EP 回退）。

    參數:
        sections: extract_patent_sections() 的返回值

    返回:
        {
            'neg_count': int,
            'pos_count': int,
            'neg_delta_count': int,
            'is_negative_da': bool|None,
            'search_source': str,
        }
    """
    desc = sections.get('description', '')
    search_source = 'description'

    if desc.strip():
        search_text = desc
    else:
        search_text = ' '.join(filter(None, [
            sections.get('abstract', ''),
            sections.get('background', ''),
            sections.get('summary', ''),
        ]))
        search_source = 'abstract+background+summary'

    neg_count = 0
    pos_count = 0
    neg_delta_count = 0

    if search_text.strip():
        neg_count = len(re.findall(
            r'negative\s+dielectric\s+anisotrop', search_text, re.IGNORECASE
        ))
        pos_count = len(re.findall(
            r'positive\s+dielectric\s+anisotrop', search_text, re.IGNORECASE
        ))
        neg_delta_count = len(re.findall(
            r'\u0394\u03b5[^\w]*-[0-9]|delta\s*epsilon[^\w]*-[0-9]',
            search_text, re.IGNORECASE
        ))

    is_negative_da = None
    if neg_count > 0 and (neg_count >= pos_count or neg_delta_count > 0):
        is_negative_da = True
    elif pos_count > 0 and neg_count == 0:
        is_negative_da = False
    elif neg_count > 0 and pos_count > neg_count:
        is_negative_da = True

    return {
        'neg_count': neg_count,
        'pos_count': pos_count,
        'neg_delta_count': neg_delta_count,
        'is_negative_da': is_negative_da,
        'search_source': search_source,
    }




def extract_patent_sections(url: str, page=None) -> Dict:
    """
    從 Google Patents 頁面提取結構化段落。

    返回:
        {
            'abstract': str,
            'background': str,
            'summary': str,
            'claim_1': str,
            'claim_2': str,
            'claim_3': str,
            'examples': List[str],
            'title': str,
            'patent_number': str,
            'description_len': int,
        }
    """
    from playwright.sync_api import sync_playwright

    result = {
        'abstract': '',
        'background': '',
        'summary': '',
        'claim_1': '',
        'claim_2': '',
        'claim_3': '',
        'examples': [],
        'title': '',
        'patent_number': '',
        'description_len': 0,
    }

    own_browser = False
    browser = None

    try:
        if page is None:
            p = sync_playwright().start()
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                ]
            )
            page = browser.new_page()
            page.set_extra_http_headers({
                'User-Agent': USER_AGENT,
                'Accept-Language': 'en-US,en;q=0.9',
            })
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            own_browser = True

            # 等待網路閒置（容忍超時）
            try:
                page.wait_for_load_state('networkidle', timeout=15000)
            except Exception:
                pass

            # 滾動加載（Google Patents 延遲渲染）
            for pos in range(0, 25000, 1500):
                page.evaluate(f'window.scrollTo(0, {pos})')
                page.wait_for_timeout(400)
            page.wait_for_timeout(3000)

        # ---- JS 提取 Description + Claims + Abstract ----
        js_result = page.evaluate("""() => {
            const output = {
                abstract: '',
                description: '',
                claims: '',
                title: '',
                patentNumber: ''
            };

            const sections = document.querySelectorAll('section');
            for (const s of sections) {
                const text = s.innerText || '';

                // Description: 內含段落號 [NNNN] 或含 "BACKGROUND"
                if ((text.includes('[0001]') || text.includes('[0002]') ||
                     text.includes('BACKGROUND OF THE INVENTION') ||
                     text.includes('Background of the Invention') ||
                     text.includes('DETAILED DESCRIPTION')) &&
                    text.length > output.description.length &&
                    text.length < 500000) {
                    output.description = text;
                }

                // Claims
                if (text.match(/^1\\./m) && text.length > 500 && text.length < 100000 &&
                    (text.includes('claim') || text.includes('according to') ||
                     text.includes('comprising'))) {
                    if (output.claims.length === 0 || text.length < output.claims.length * 1.5) {
                        output.claims = text;
                    }
                }

                // Abstract
                if (text.length > 50 && text.length < 3000 &&
                    !text.includes('[000') && !text.includes('Claims') &&
                    (text.toLowerCase().includes('liquid-crystal') ||
                     text.toLowerCase().includes('liquid crystal') ||
                     text.toLowerCase().includes('dielectric') ||
                     text.toLowerCase().includes('compound') ||
                     text.toLowerCase().includes('method'))) {
                    if (output.abstract.length === 0) {
                        output.abstract = text.replace(/^Abstract\\s*/i, '').trim();
                    }
                }
            }

            const urlMatch = window.location.href.match(/patent\\/([A-Z]{2}\\d+[A-Z]?\\d?)/i);
            if (urlMatch) output.patentNumber = urlMatch[1].toUpperCase();

            const titleEl = document.querySelector('h1, [itemprop="title"], .title');
            if (titleEl) output.title = titleEl.textContent.trim().substring(0, 200);

            output.description = output.description.substring(0, 500000);
            output.claims = output.claims.substring(0, 80000);
            output.abstract = output.abstract.substring(0, 2000);

            return output;
        }""")

        desc = js_result.get('description', '')
        claims = js_result.get('claims', '')
        abstract = js_result.get('abstract', '')
        result['title'] = js_result.get('title', '')
        result['patent_number'] = js_result.get('patentNumber', '')
        result['description_len'] = len(desc)

        # ---- EP description 回退（陷阱 27）：JS evaluate description 為空時，
        #     使用 inner_text('body') 全文提取，再用正則分段 Description ----
        ep_desc_fallback = None
        if not desc.strip():
            print('  [陷阱27] JS description 為空，啟動 EP inner_text 回退提取...')
            ep_desc_fallback = _extract_ep_description_fallback(page)
            if ep_desc_fallback['description']:
                desc = ep_desc_fallback['description']
                result['description_len'] = ep_desc_fallback['description_len']
                print(f'  [陷阱27] EP 回退成功：description_len={result["description_len"]}')
            else:
                print('  [陷阱27] EP 回退未能提取到 description')

        # ---- 按標題行分割 Description ----
        desc_sections = split_description_sections(desc)
        result['background'] = desc_sections['background']
        result['summary'] = desc_sections['summary']

        # ---- 提取 Claims 1-3: 先嘗試正則 ----
        for n in [1, 2, 3]:
            pat = rf'(?:^|\n)\s*{n}\.\s+([\s\S]{{20,5000}}?)(?=\n\s*{n+1}\.\s|$)'
            m = re.search(pat, claims)
            if m:
                c = re.sub(r'\s+', ' ', m.group(1)).strip()
                result[f'claim_{n}'] = c[:2000]

        # ---- EP 專利 DOM 回退: 正則對 <ol class="claims"> 結構無效 ----
        if not result.get('claim_1'):
            ep_claims = _extract_ep_claims_dom(page)
            for n in [1, 2, 3]:
                key = f'claim_{n}'
                if not result.get(key) and ep_claims.get(key):
                    result[key] = ep_claims[key]

        # ---- 提取實施例 ----
        example_pattern = (
            r'(?:Example|EXAMPLE|Beispiel|Mixture\s+Example)\s*[A-Z]?\d+[.:]?\s*'
            r'[\s\S]{30,2000}?(?=(?:Example|EXAMPLE|Beispiel|Mixture\s+Example)\s*[A-Z]?\d+|$)'
            )
        examples = re.findall(example_pattern, desc, re.IGNORECASE)
        result['examples'] = [ex.strip()[:1500] for ex in examples[:5]]

        # EP 回退實施例合併（當 JS description 為空且 inner_text 回退有實施例時）
        if not result['examples'] and ep_desc_fallback and ep_desc_fallback.get('examples'):
            result['examples'] = ep_desc_fallback['examples']
            print(f'  [陷阱27] EP 回退實施例：{len(result["examples"])} 個')

        # EP 回退 background/summary 合併（當 JS description 為空且分段結果為空時）
        if ep_desc_fallback and not result.get('background') and ep_desc_fallback.get('background'):
            result['background'] = ep_desc_fallback['background']
            print(f'  [陷阱27] EP 回退 background：{len(result["background"])} chars')
        if ep_desc_fallback and not result.get('summary') and ep_desc_fallback.get('summary'):
            result['summary'] = ep_desc_fallback['summary']
            print(f'  [陷阱27] EP 回退 summary：{len(result["summary"])} chars')
        result['abstract'] = abstract

        # ---- 正/負介電判定（陷阱 13 + 27 回退） ----
        da_info = determine_dielectric_type({
            'description': desc,
            'abstract': abstract,
            'background': result['background'],
            'summary': result['summary'],
        })
        result['dielectric_type'] = da_info
        if da_info['is_negative_da'] is not None:
            label = '負介電' if da_info['is_negative_da'] else '正介電'
            print(f'  介電判定：{label} (neg={da_info["neg_count"]}, pos={da_info["pos_count"]}, source={da_info["search_source"]})')
        else:
            print(f'  介電判定：無法判定 (neg={da_info["neg_count"]}, pos={da_info["pos_count"]}, source={da_info["search_source"]})')

    except Exception as e:
        print(f"  ❌ 段落提取異常: {e}")
    finally:
        if own_browser and browser:
            try:
                browser.close()
            except Exception:
                pass

    return result


def build_tech_feature_prompt(sections: Dict) -> str:
    """
    根據提取的段落組合 LLM prompt。
    """
    abstract = sections.get('abstract', '') or '[未提取到 Abstract]'
    background = sections.get('background', '') or '[未提取到 Background of the Invention]'
    summary = sections.get('summary', '') or '[未提取到 Summary of the Invention]'
    claim_1 = sections.get('claim_1', '') or '[未提取到 Claim 1]'
    claim_2 = sections.get('claim_2', '') or '[未提取到 Claim 2]'

    examples_list = sections.get('examples', [])
    if examples_list:
        examples_text = '\n---\n'.join(examples_list[:3])
    else:
        examples_text = '[未提取到實施例]'

    prompt = TECH_FEATURE_PROMPT_TEMPLATE.format(
        abstract=abstract[:800],
        background=background[:4000],
        summary=summary[:3000],
        claim_1=claim_1[:1500],
        claim_2=claim_2[:1200],
        examples=examples_text[:3000],
    )

    return prompt


def generate_tech_features_openai(
    sections: Dict,
    api_key: str = None,
    model: str = "gpt-4o-mini"
) -> str:
    """使用 OpenAI API 生成技術特點摘要。"""
    try:
        import openai
    except ImportError:
        print("  ❌ openai 套件未安裝，請執行: pip install openai")
        return ""

    client = openai.OpenAI(
        api_key=api_key or os.environ.get('OPENAI_API_KEY')
    )
    prompt = build_tech_feature_prompt(sections)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是一個專利技術特點摘要生成器，擅長從專利文件中"
                    "提取關鍵技術資訊並撰寫結構化摘要。請使用繁體中文。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=1024,
    )

    return response.choices[0].message.content


def generate_tech_features_anthropic(
    sections: Dict,
    api_key: str = None,
    model: str = "claude-sonnet-4-20250514"
) -> str:
    """使用 Anthropic API 生成技術特點摘要。"""
    try:
        import anthropic
    except ImportError:
        print("  ❌ anthropic 套件未安裝，請執行: pip install anthropic")
        return ""

    client = anthropic.Anthropic(
        api_key=api_key or os.environ.get('ANTHROPIC_API_KEY')
    )
    prompt = build_tech_feature_prompt(sections)

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text


def enrich_patent_with_tech_features(
    patent_data: Dict,
    sections: Dict = None,
    llm_backend: str = 'prompt_only',
    api_key: str = None,
    model: str = None,
) -> Dict:
    """
    將技術特點摘要添加到專利數據中。

    流程：
    1. 如果已經有 sections，直接使用
    2. 根據 llm_backend 選擇生成方式
    3. 將結果寫入 patent_data['tech_features']
    """
    if sections:
        patent_data['tech_feature_sections'] = {
            'background_len': len(sections.get('background', '')),
            'summary_len': len(sections.get('summary', '')),
            'claim_1_len': len(sections.get('claim_1', '')),
            'claim_2_len': len(sections.get('claim_2', '')),
            'examples_count': len(sections.get('examples', [])),
        }

    if llm_backend == 'openai':
        tech_features = generate_tech_features_openai(
            sections, api_key, model or 'gpt-4o-mini'
        )
    elif llm_backend == 'anthropic':
        tech_features = generate_tech_features_anthropic(
            sections, api_key, model or 'claude-sonnet-4-20250514'
        )
    elif llm_backend == 'prompt_only':
        prompt = build_tech_feature_prompt(sections)
        patent_data['tech_feature_prompt'] = prompt
        tech_features = ''
    else:
        prompt = build_tech_feature_prompt(sections)
        patent_data['tech_feature_prompt'] = prompt
        tech_features = '[pending_subagent_call]'

    if tech_features:
        patent_data['tech_features'] = tech_features

    return patent_data


def format_tech_features_for_report(patent: Dict) -> str:
    """將技術特點摘要格式化為報告中的 Markdown 段落。"""
    lines = []

    tech_features = patent.get('tech_features', '')
    if tech_features and tech_features != '[pending_subagent_call]':
        lines.append("#### 技術特點摘要（LLM 生成）")
        lines.append("")
        lines.append(tech_features)
        lines.append("")

    sections_info = patent.get('tech_feature_sections', {})
    if sections_info:
        lines.append("*段落提取統計:*")
        parts = []
        if sections_info.get('background_len', 0) > 0:
            parts.append(f"Background {sections_info['background_len']}字")
        if sections_info.get('summary_len', 0) > 0:
            parts.append(f"Summary {sections_info['summary_len']}字")
        if sections_info.get('claim_1_len', 0) > 0:
            parts.append(f"Claim1 {sections_info['claim_1_len']}字")
        if sections_info.get('claim_2_len', 0) > 0:
            parts.append(f"Claim2 {sections_info['claim_2_len']}字")
        if sections_info.get('examples_count', 0) > 0:
            parts.append(f"實施例 {sections_info['examples_count']}個")
        lines.append("  " + " | ".join(parts))
        lines.append("")

    return '\n'.join(lines)


# ========== 主程式 ==========

def main():
    parser = argparse.ArgumentParser(
        description='技術特點 LLM 摘要生成器'
    )
    parser.add_argument('--url', help='Google Patents URL')
    parser.add_argument('--json', help='已提取的 JSON 檔案路徑')
    parser.add_argument(
        '--backend', default='prompt_only',
        choices=['subagent', 'openai', 'anthropic', 'prompt_only'],
        help='LLM 後端 (預設: prompt_only)'
    )
    parser.add_argument('--model', help='LLM 模型名稱')
    parser.add_argument(
        '--test', action='store_true', help='執行端到端測試'
    )
    parser.add_argument(
        '--output', default='/tmp/tech_features_output.json',
        help='輸出檔案路徑'
    )

    args = parser.parse_args()

    if args.test:
        test_url = "https://patents.google.com/patent/US20250284151A1/en"
        print("=" * 70)
        print("技術特點 LLM 摘要生成器 — 端到端測試")
        print("=" * 70)

        print(f"\n📋 步驟 1：提取段落 — {test_url}")
        sections = extract_patent_sections(test_url)

        print(f"\n📊 提取結果：")
        for k, v in sections.items():
            if isinstance(v, str):
                print(f"  {k}: {len(v)} chars")
            elif isinstance(v, list):
                print(f"  {k}: {len(v)} items")

        print(f"\n📋 步驟 2：組合 LLM Prompt")
        prompt = build_tech_feature_prompt(sections)
        print(f"  Prompt 長度: {len(prompt)} chars (~{len(prompt)//4} tokens)")

        prompt_path = '/tmp/tech_feature_test_prompt.txt'
        with open(prompt_path, 'w') as f:
            f.write(prompt)
        print(f"  Prompt 已儲存: {prompt_path}")

        output = {
            'patent_number': sections.get('patent_number', ''),
            'sections': {
                'abstract_len': len(sections.get('abstract', '')),
                'background_len': len(sections.get('background', '')),
                'summary_len': len(sections.get('summary', '')),
                'claim_1_len': len(sections.get('claim_1', '')),
                'claim_2_len': len(sections.get('claim_2', '')),
                'examples_count': len(sections.get('examples', [])),
            },
        }

        with open(args.output, 'w') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 測試完成！結果儲存: {args.output}")

        print(f"\n=== Background 預覽 ===")
        print(sections.get('background', '')[:500])
        print(f"\n=== Summary 預覽 ===")
        print(sections.get('summary', '')[:300])
        print(f"\n=== Claim 1 預覽 ===")
        print(sections.get('claim_1', '')[:300])
        print(f"\n=== Claim 2 預覽 ===")
        print(sections.get('claim_2', '')[:300])

        return

    if args.url:
        print(f"📋 提取段落: {args.url}")
        sections = extract_patent_sections(args.url)

        print(f"\n📊 提取結果：")
        for k, v in sections.items():
            if isinstance(v, str):
                print(f"  {k}: {len(v)} chars")
            elif isinstance(v, list):
                print(f"  {k}: {len(v)} items")

        prompt = build_tech_feature_prompt(sections)

        with open(args.output, 'w') as f:
            json.dump({
                'sections': {k: len(v) if isinstance(v, (str, list)) else v
                             for k, v in sections.items()},
                'prompt': prompt,
            }, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 結果儲存: {args.output}")

    if args.json:
        print(f"📋 從 JSON 載入: {args.json}")
        with open(args.json, 'r') as f:
            patents = json.load(f)

        results = []
        for i, p in enumerate(patents[:5]):
            url = p.get('url', '')
            if not url:
                continue

            print(f"\n  [{i+1}] {p.get('patent_number', 'N/A')}")
            sections = extract_patent_sections(url)
            prompt = build_tech_feature_prompt(sections)

            p['tech_feature_prompt'] = prompt
            p['tech_feature_sections'] = {
                'background_len': len(sections.get('background', '')),
                'summary_len': len(sections.get('summary', '')),
                'claim_1_len': len(sections.get('claim_1', '')),
                'claim_2_len': len(sections.get('claim_2', '')),
                'examples_count': len(sections.get('examples', [])),
            }
            results.append(p)

        with open(args.output, 'w') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 批量結果儲存: {args.output}")


if __name__ == '__main__':
    main()
