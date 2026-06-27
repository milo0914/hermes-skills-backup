---
name: patent-playwright-scraper
description: 使用 Playwright 直接訪問提取 Google Patents 等專利數據，繞過反爬機制，適用於 Firecrawl 額度用完或需要高可靠性提取的場景
category: research
tags: [patent, playwright, web-scraping, google-patents, uspto, open-source]
version: 1.0.0
created: 2026-05-20
---

# Playwright 專利數據提取技能

## 🎯 使用時機

當你需要：
- 從 Google Patents、USPTO、Justia 等專利網站提取數據
- Firecrawl 額度已用完，需改用純開源方案
- 需要處理 JavaScript 動態加載的頁面
- 需要高可靠性（>90% 成功率）的專利提取
- 提取 Claim 1、實施例、技術領域等關鍵信息

## ⚠️ 關鍵陷阱與教訓

### 陷阱 1: Crawl4AI 版本兼容性
- **問題**: Crawl4AI 新版本 (`0.4.x`) 的 `CrawlerRunConfig` 參數大幅變化
- **錯誤寫法**:
  ```python
  # 舊版本語法，會報 'has no attribute' 錯誤
  config = CrawlerRunConfig(enable_stealth=True, args=['--no-sandbox'])
  ```
- **正確寫法**:
  ```python
  # 使用 Playwright 直接訪問，完全控制
  from playwright.sync_api import sync_playwright
  
  with sync_playwright() as p:
      browser = p.chromium.launch(headless=True)
      page = browser.new_page()
      page.goto(url, wait_until='domcontentloaded', timeout=60000)
  ```

### 陷阱 2: Claim 1 提取正則表達式
- **問題**: 單一正則表達式無法匹配所有專利格式
- **解決方案**: 使用 5 種模式多輪匹配
  ```python
  patterns = [
      r'WHAT IS CLAIMED IS:\s*(?:1\.\s*)([\s\S]*?(?:;\s*or\s*[\s\S]*?)+)',
      r'CLAIMS\s*(?:1\.\s*)([\s\S]*?(?:;\s*or\s*[\s\S]*?)+)',
      r'1\.\s+([\s\S]*?(?:;\s*or\s*[\s\S]*?)+)',
      r'WHAT IS CLAIMED IS:\s*1\.\s+([\s\S]*?(?=2\.|$))',
      r'1\.\s+([\s\S]*?(?=2\.|$))'
  ]
  ```

### 陷阱 3: 日期範圍控制
- **問題**: Google Patents 搜索結果無法通過 URL 參數嚴格控制日期
- **解決方案**: 
  1. 搜索階段廣泛抓取
  2. 提取階段嚴格過濾 (2020-2026)
  3. 使用 USPTO API 或 BigQuery 進行精確搜索

### 陷阱 4: 反爬機制
- **問題**: The Lens、USPTO 等返回 403 Forbidden
- **解決方案**:
  - 使用真實瀏覽器環境 (Playwright)
  - 添加合理的延遲 (1-2 秒)
  - 使用正常的 User-Agent
  - 避免高頻請求

## 🛠️ 環境準備

```bash
# 安裝 Playwright
pip install playwright

# 安裝瀏覽器
playwright install chromium

# 其他依賴
pip install beautifulsoup4 lxml
```

## 📝 標準提取流程

### 步驟 1: 初始化瀏覽器

```python
from playwright.sync_api import sync_playwright
import json

def extract_patent_info(url: str) -> dict:
    """使用 Playwright 提取專利信息"""
    
    with sync_playwright() as p:
        # 啟動瀏覽器
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu'
            ]
        )
        
        # 創建頁面
        page = browser.new_page(
            user_agent='Mozilla/5.0 (Windows NT 110.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        try:
            # 訪問頁面
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            # 等待關鍵元素加載
            page.wait_for_selector('h1', timeout=10000)
            
            # 獲取頁面內容
            content = page.content()
            text = page.inner_text('body')
            
            return {
                'success': True,
                'url': url,
                'html': content,
                'text': text,
                'title': page.title()
            }
            
        except Exception as e:
            return {
                'success': False,
                'url': url,
                'error': str(e)
            }
        finally:
            browser.close()
```

### 步驟 2: 提取 Claim 1

```python
import re
from typing import Optional

def extract_claim1(text: str) -> Optional[str]:
    """多模式匹配 Claim 1"""
    
    patterns = [
        # 模式 1: 標準 Google Patents 格式
        r'WHAT IS CLAIMED IS:\s*(?:1\.\s*)([\s\S]*?(?:;\s*or\s*[\s\S]*?)+)',
        # 模式 2: CLAIMS 開頭
        r'CLAIMS\s*(?:1\.\s*)([\s\S]*?(?:;\s*or\s*[\s\S]*?)+)',
        # 模式 3: 簡單數字開頭
        r'1\.\s+([\s\S]*?(?:;\s*or\s*[\s\S]*?)+)',
        # 模式 4: 到下一項為止
        r'WHAT IS CLAIMED IS:\s*1\.\s+([\s\S]*?(?=2\.|$))',
        # 模式 5: 最簡格式
        r'1\.\s+([\s\S]*?(?=2\.|$))'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            claim1 = match.group(1).strip()
            # 清理多餘空白
            claim1 = re.sub(r'\s+', ' ', claim1)
            if len(claim1) > 50:  # 合理長度
                return claim1
    
    return None
```

### 步驟 3: 提取實施例

```python
def extract_examples(text: str) -> list:
    """提取實施例/實施方式"""
    
    examples = []
    
    # 模式 1: Example 1, Example 2...
    example_pattern = r'(?:Example|EXAMPLE)\s*\d+[:\.\s][\s\S]*?(?=(?:Example|EXAMPLE)\s*\d+|$)'
    matches = re.findall(example_pattern, text, re.IGNORECASE)
    if matches:
        examples.extend([m.strip() for m in matches])
    
    # 模式 2: Embodiment
    embodiment_pattern = r'(?:In an?|According to an?)(?:\s+)?(?:example|embodiment|implementation)[\s\S]*?(?=(?:In an?|According to an?)(?:\s+)?(?:example|embodiment|implementation)|$)'
    matches = re.findall(embodiment_pattern, text, re.IGNORECASE)
    if matches:
        examples.extend([m.strip() for m in matches])
    
    # 模式 3: 具體實施方式標題下
    section_pattern = r'(?:DETAILED DESCRIPTION|具體實施方式|實施例)[\s\S]*?(?=\b(?:WHAT IS CLAIMED|CLAIMS|摘要|ABSTRACT)\b|$)'
    match = re.search(section_pattern, text, re.IGNORECASE)
    if match:
        section_text = match.group(0)
        # 提取段落
        paragraphs = re.split(r'\n\s*\n', section_text)
        examples.extend([p.strip() for p in paragraphs if len(p.strip()) > 100])
    
    return examples[:10]  # 限制最多 10 個
```

### 步驟 4: 提取專利號

```python
def extract_patent_number(text: str, url: str) -> Optional[str]:
    """提取專利號"""
    
    # 從 URL 提取
    url_patterns = [
        r'patents\.google\.com/patent/([A-Z]{2}\d+[A-Z]?)',
        r'patents\.google\.com/patent/([A-Z]{2,4}\d+[A-Z]?)',
        r'uspto\.gov/patent/([A-Z]{2}\d+)',
    ]
    
    for pattern in url_patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    # 從文本提取
    text_patterns = [
        r'(?:Patent number|US Patent|專利號)[:\s]*([A-Z]{2,4}\d+[A-Z]?)',
        r'([A-Z]{2}\d+[A-Z]?)\s*(?:B2|B1|A|A1|A2)?\s*(?:issued|granted)',
    ]
    
    for pattern in text_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None
```

### 步驟 5: 完整提取流程

```python
def extract_patent_full(url: str) -> dict:
    """完整專利信息提取"""
    
    # 步驟 1: 獲取頁面
    page_data = extract_patent_info(url)
    
    if not page_data['success']:
        return {
            'success': False,
            'url': url,
            'error': page_data.get('error', 'Unknown error')
        }
    
    text = page_data['text']
    
    # 步驟 2: 提取各項信息
    patent_number = extract_patent_number(text, url)
    claim1 = extract_claim1(text)
    examples = extract_examples(text)
    
    # 步驟 3: 提取日期
    pub_date_match = re.search(r'(?:Publication date|公開日期)[:\s]*(\d{4}-\d{2}-\d{2})', text)
    pub_date = pub_date_match.group(1) if pub_date_match else None
    
    # 步驟 4: 提取技術領域
    tech_field_match = re.search(r'(?:TECHNICAL FIELD|技術領域)[\s\S]{0,500}?\n\n', text, re.IGNORECASE)
    tech_field = tech_field_match.group(0).strip() if tech_field_match else None
    
    return {
        'success': True,
        'url': url,
        'patent_number': patent_number,
        'publication_date': pub_date,
        'claim1': claim1,
        'claim1_length': len(claim1) if claim1 else 0,
        'examples': examples,
        'example_count': len(examples),
        'technical_field': tech_field,
        'title': page_data.get('title', ''),
        'raw_text_length': len(text)
    }
```

## 🚀 批量提取腳本範例

```python
#!/usr/bin/env python3
"""
Merck KGaA 負介電液晶專利批量提取腳本
使用 Playwright 直接訪問，繞過反爬機制
"""

import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

# 導入上述所有提取函數...

def batch_extract(search_file: str, output_file: str):
    """批量提取專利信息"""
    
    # 讀取搜索結果
    with open(search_file, 'r', encoding='utf-8') as f:
        patents = json.load(f)
    
    print(f"讀取到 {len(patents)} 個專利")
    
    extracted = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        for i, patent in enumerate(patents, 1):
            url = patent.get('url') or patent.get('link')
            if not url:
                continue
            
            print(f"\n[{i}/{len(patents)}] 提取：{url}")
            
            try:
                page = browser.new_page()
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
                page.wait_for_selector('h1', timeout=10000)
                
                text = page.inner_text('body')
                title = page.title()
                
                # 提取信息
                patent_number = extract_patent_number(text, url)
                claim1 = extract_claim1(text)
                examples = extract_examples(text)
                
                result = {
                    'url': url,
                    'patent_number': patent_number,
                    'title': title,
                    'claim1': claim1,
                    'claim1_length': len(claim1) if claim1 else 0,
                    'examples': examples,
                    'example_count': len(examples),
                    'success': True
                }
                
                print(f" ✓ 提取成功 - 專利號：{patent_number or 'N/A'}")
                print(f"   Claim 1 長度：{result['claim1_length']} 字元")
                print(f"   實施例：{result['example_count']} 個")
                
            except Exception as e:
                result = {
                    'url': url,
                    'success': False,
                    'error': str(e)
                }
                print(f" ✗ 提取失敗：{e}")
            
            finally:
                page.close()
            
            extracted.append(result)
            
            # 禮貌延遲
            time.sleep(1.5)
        
        browser.close()
    
    # 保存結果
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2)
    
    # 統計
    success_count = sum(1 for p in extracted if p['success'])
    claim1_count = sum(1 for p in extracted if p.get('claim1'))
    
    print("\n" + "="*80)
    print("提取統計")
    print("="*80)
    print(f" 總提取數量：{success_count}/{len(extracted)}")
    print(f" 有 Claim 1: {claim1_count}/{len(extracted)} ({claim1_count/len(extracted)*100:.1f}%)")
    print(f" 結果已保存：{output_file}")

if __name__ == '__main__':
    batch_extract('/tmp/patent_search_results.json', '/tmp/extracted_patents_v8.json')
```

## 📊 性能指標

### 最新版本 (v10) 性能

| 指標 | 目標 | v8 實測 | v9 實測 | v10-A 實測 | 備註 |
|------|------|--------|--------|-----------|------|
| 提取成功率 | >95% | 100% (9/9) | 100% (9/9) | 100% (9/9) | Playwright 直接訪問 ✅ |
| Claim 1 提取率 | >80% | 55.6% (5/9) | 66.7% (6/9) | 66.7% (6/9) | 6 種正則模式 ⚠️ |
| 實施例提取率 | >50% | 44% (4/9) | 33.3% (3/9) | 33.3% (3/9) | 需改進識別邏輯 ⚠️ |
| 日期提取率 | >80% | 0% (0/9) | 22.2% (2/9) | 0% (0/9) | Google meta 不可靠 ❌ |
| 專利號提取率 | >95% | 77.8% (7/9) | 77.8% (7/9) | 77.8% (7/9) | 需改進格式 ⚠️ |
| 平均提取時間 | <15 秒 | ~8 秒 | ~10 秒 | ~12 秒 | 含結構化解析 ✅ |
| 反爬繞過率 | 100% | 100% | 100% | 77.8% | Justia 需改進 ⚠️ |

**版本演進趨勢**：
- v8: 初始版本，Claim 1 55.6%
- v9: 6 種正則 + 置信度評分，Claim 1 66.7%
- v10-A: HTML 結構化解析，Claim 1 持平，日期提取失效
- v10-C（推薦）: 混合式 LLM 輔助，預期 Claim 1 >85%

**瓶頸分析**：
1. Justia 反爬（3/9 失敗）：需真實瀏覽器指紋或 USPTO API
2. 日期提取：Google Patents meta 標籤不可靠，需 USPTO API/BigQuery
3. Claim 1 置信度：需 LLM 驗證低置信度案例

### v9 性能（存檔）

| 指標 | 目標 | v8 實測 | v9 實測 | 改進幅度 |
|------|------|--------|--------|---------|
| 提取成功率 | >95% | 100% (9/9) | 100% (9/9) | 維持 ✅ |
| Claim 1 提取率 | >80% | 55.6% (5/9) | 66.7% (6/9) | +11.1% ✅ |
| 實施例提取率 | >50% | 44% (4/9) | 33.3% (3/9) | -11.1% ⚠️ |
| 日期提取率 | >80% | 0% (0/9) | 22.2% (2/9) | +22.2% ✅ |
| 平均提取時間 | <15 秒 | ~8 秒 | ~10 秒 | 可接受 ✅ |
| 反爬繞過率 | 100% | 100% | 100% | 維持 ✅ |

### 版本演進

| 版本 | Claim 1 | 實施例 | 日期 | 關鍵改進 |
|------|--------|-------|------|---------|
| v6 | 0% | 33% | 0% | 初始版 |
| v7 | 0% | 33% | 0% | Crawl4AI 適配 |
| v8 | 55.6% | 44% | 0% | Playwright 直接訪問 |
| v9 | 66.7% | 33.3% | 22.2% | 6 種正則 + 多策略 |

## 🔧 疑難排解

### 問題 1: 頁面加載超時

**現象**: `Page.wait_for_selector: Timeout 10000ms exceeded`

**解決方案**:
```python
# 使用更寬鬆的等待條件
page.goto(url, wait_until='domcontentloaded', timeout=60000)

try:
    page.wait_for_load_state('networkidle', timeout=10000)
except:
    pass  # 超時也繼續執行

# 避免使用 wait_for_selector('h1, title') 這種會匹配多個元素的選擇器
```

### 問題 2: Claim 1 提取率偏低

**現象**: Claim 1 提取率 < 60%

**解決方案**:
```python
# 使用 6 種正則模式 + 置信度評分
CLAIM1_PATTERNS = [
    (r'WHAT IS CLAIMED IS:...', "標準格式", 1.0),
    (r'CLAIMS...', "CLAIMS 開頭", 0.9),
    (r'1\.\s+...', "寬鬆數字", 0.8),
    (r'申請專利範圍...', "中文格式", 0.85),
    (r'(?:Claim 1|第 1 項)...', "WO 格式", 0.75),
    (r'1\.\s+...', "最簡保底", 0.7),
]

# 選擇置信度最高的結果
results.sort(key=lambda x: x[2], reverse=True)
```

### 問題 3: Justia 反爬機制

**現象**: 返回 "Just a moment..." 頁面

**解決方案**:
```python
# 方案 1: 使用更真實的 User-Agent
page.context.set_extra_http_headers({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)...'
})

# 方案 2: 添加隨機延遲
import random
time.sleep(random.uniform(1.0, 3.0))

# 方案 3: 使用 USPTO API 替代
# (需要事先申請 API Key)
```

### 問題 4: 日期提取失败

**現象**: 無法從 Google Patents 提取日期

**解決方案**:
```python
# 解析 HTML meta 標籤
date_match = page.query_selector('meta[name="citation_publication_date"]')
if date_match:
    pub_date = date_match.get_attribute('content')

# 或使用多格式正則
date_patterns = [
    r'(?:Publication date|公開日期)[:\s]*(\d{4}-\d{2}-\d{2})',
    r'(\d{4}年\d{1,2}月\d{1,2}日)',
]
```

### 問題 5: 非專利頁面干擾

**現象**: 列表頁、發明人頁無法提取有效信息

**解決方案**:
```python
# 前端 URL 預篩選
def is_patent_url(url: str) -> bool:
    patent_patterns = [
        r'patents\.google\.com/patent/[A-Z]{2,4}\d+',
        r'uspto\.gov/patent/[A-Z]{2}\d+',
    ]
    return any(re.match(p, url) for p in patent_patterns)

# 頁面類型識別
if "Inventor" in title or "Assignee" in title:
    return None  # 跳過非專利頁面
```

### 問題 6: Claim 1 過長

**現象**: Claim 1 長度超過 20000 字元

**解決方案**:
```python
# 添加長度檢查
if len(claim1) > 5000:
    # 可能是誤匹配，降低置信度
    confidence *= 0.5

# 或截斷保存
if len(claim1) > 10000:
    claim1 = claim1[:10000] + "..."
```

## 📚 相關技能

- `patent-research-workflow`: 完整專利調研流程
- `browser-automation`: 瀏覽器自動化基礎
- `open-source-patent-tools`: 開源專利工具集合
- `web-researcher`: 高級網頁研究技巧

## 📝 版本歷史

- **v1.0.0** (2026-05-20): 初始版本，基於 Merck KGaA 負介電液晶專利調研實戰經驗
  - 整合 Playwright 直接訪問方案
  - 多模式 Claim 1 提取（6 種正則模式）
  - 完整的實施例識別邏輯
  - 詳細的陷阱與解決方案文檔

- **v9** (2026-05-20): 改進版
  - 6 種 Claim 1 正則模式 + 置信度評分
  - 改進實施例提取邏輯
  - 寬鬆等待策略避免超時
  - Claim 1 提取率提升至 66.7%

- **v10-A** (2026-05-20): HTML 結構化解析版
  - 解析 JSON-LD、meta 標籤、微數據
  - 使用 BeautifulSoup 進行結構化解析
  - 發現：Google Patents meta 標籤不可靠
  - Claim 1 持平（66.7%），日期提取失效（0%）

- **v10-C** (推薦方案): 混合式 LLM 輔助
  - 正則提取（100% 案例）
  - 置信度評估
  - 低置信度（<0.7）調用 LLM 驗證
  - 預期 Claim 1 >85%，成本 100 個專利 ~$0.40-0.80

---

## 🔬 LLM 集成指南

### 何時使用 LLM

**推薦使用場景**：
1. Claim 1 置信度 <0.7 的案例
2. Justia 等反爬網站的頁面
3. 非標準格式的專利（WO、CN 等）
4. 需要語義理解的提取任務

**不推薦使用場景**：
1. 標準 Google Patents 頁面（正則已足夠）
2. 批量初步篩選（成本考量）
3. 實時性要求高的場景

### 方案 A: Browser-use MCP

**安裝**：
```bash
# 需要 API key（Claude/GPT/OpenAI）
export ANTHROPIC_API_KEY=your_key
# 或
export OPENAI_API_KEY=your_key
```

**使用時機**：
- 動態頁面（JavaScript 加載）
- 高價值專利（需要精確提取）
- 批量處理後的疑難案例

**成本**：~$0.01-0.05/頁

### 方案 B: LangChain Playwright

**安裝**：
```bash
pip install langchain playwright langchain-openai
```

**使用時機**：
- 需要自定義 extraction prompt
- 批量處理 + 錯誤重試
- 多步驟提取任務

**成本**：~$0.01-0.03/頁

### 方案 C: 混合式（推薦）

**流程**：
```
正則提取（100% 案例，免費）
    ↓
置信度評估（長度、關鍵詞、格式）
    ↓
高置信度 (>0.7) → 直接輸出
    ↓
低置信度 (<0.7) → LLM 驗證修正
    ↓
最終結果
```

**成本估算**：
- 80% 案例：正則處理（$0）
- 20% 案例：LLM 驗證（~$0.02/個）
- **100 個專利總成本：~$0.40-0.80**

**實現腳本**：見 `scripts/patent_extract_v10c_hybrid.py`（待創建）

### 腳本文件
- `scripts/patent_extract_v9_full.py` - v9 完整版
- `scripts/patent_extract_v10a_structured.py` - v10-A 結構化解析版
- `scripts/patent_extract_v10c_hybrid.py` - v10-C 混合式（LLM 開關）
### 腳本文件
- `scripts/patent_extract_v9_full.py` - v9 完整版
- `scripts/patent_extract_v10a_structured.py` - v10-A 結構化解析版
- `scripts/patent_extract_v10c_hybrid.py` - v10-C 混合式（LLM 開關，待創建）
- `scripts/test_claim1_patterns.py` - 正則模式測試
- `scripts/standard_patent_extractor.py` - 標準提取器
- `scripts/advanced_patent_extractor.py` - 進階版（並發 + 重試）

### 參考文檔
- `references/test_report.md` - 測試報告
- `references/v10_test_report.md` - v10 測試報告與 LLM 集成指南
- `references/v10_comparison.md` - v9 vs v10 對比分析
