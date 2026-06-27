# 專利 Claim 1 與實施例抓取實戰記錄 (2026-05-12)

## 任務概述
完善 Merck 負介電液體晶體專利數據，補充 Claim 1（請求項 1）和實施例（Examples）詳細信息。

## 目標專利
- US 12618007
- US 12618008
- US 12612551
- US 12606745
- US 12595414
- US 12595417
- US 12585160

## 使用的工具
- **Playwright**: 瀏覽器自動化
- **Justia Patents**: https://patents.justia.com/patent/{number}
- **Google Patents**: https://patents.google.com/patent/US{number}

## 抓取策略

### 策略 1: Justia 直接抓取
```python
from playwright.sync_api import sync_playwright

def scrape_justia(patent_number):
    url = f"https://patents.justia.com/patent/{patent_number}"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # 使用 'domcontentloaded' 而非 'networkidle' 避免超時
        page.goto(url, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(8000)  # 等待 JavaScript 渲染
        
        # 提取標題
        title_elem = page.query_selector('h1 a')
        title = title_elem.inner_text().strip() if title_elem else ""
        
        # 提取 Claim 1 - 使用正則匹配
        content = page.inner_text('body')
        claim1_match = re.search(r'1\.\s+(.*?)(?:\n\n|2\.|\Z)', content, re.DOTALL)
        claim1 = claim1_match.group(1).strip() if claim1_match else ""
        
        # 提取實施例
        example_pattern = r'(?:EXAMPLE|Example)\s+\d+[:\.\-].*?(?=(?:EXAMPLE|Example)\s+\d+[:\.\-]|\Z)'
        examples = re.findall(example_pattern, content, re.IGNORECASE | re.DOTALL)
        
        browser.close()
        return {'title': title, 'claim1': claim1, 'examples': examples}
```

### 策略 2: Google Patents 交叉驗證
```python
def scrape_google_patent(patent_number):
    url = f"https://patents.google.com/patent/US{patent_number}"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until='networkidle', timeout=60000)
        page.wait_for_timeout(5000)
        
        # 提取 Claim 1 - 嘗試多種選擇器
        claims = page.query_selector_all('div.claw-note p')
        if claims:
            claim1 = claims[0].inner_text().strip()
        else:
            claims_section = page.query_selector('section[data-section="claims"]')
            if claims_section:
                claims_text = claims_section.inner_text()
                claim1_match = re.search(r'1\.\s+(.*?)(?:\n\n|2\.|\Z)', claims_text, re.DOTALL)
                claim1 = claim1_match.group(1).strip() if claim1_match else ""
        
        browser.close()
        return {'claim1': claim1}
```

## 實際抓取結果

### 成功抓取的專利
| 專利號 | 標題 | Claim 1 長度 | 實施例數 | 來源 |
|--------|------|-------------|---------|------|
| 12618007 | Liquid-crystalline medium | 504 字符 | 0 | Justia |
| 12612551 | Liquid crystal medium | 336 字符 | 0 | Justia |
| 12606745 | Liquid crystal medium | 317 字符 | 0 | Justia |
| 12595414 | Ferroelectric nematic LC | 141 字符 | 3 | Justia |
| 12585160 | Liquid-crystalline medium | 269 字符 | 0 | Justia |

### 超時失敗的專利
- US 12618008: Justia 超時 60 秒，Google Patents 也無法抓取
- US 12595417: Justia 超時 60 秒，Google Patents 也無法抓取

**原因分析**: 這兩個專利可能是近期專利，Justia 頁面加載極慢或服務器響應問題。

### 重要發現：US 12595414 實施例

#### 實施例 1: UUQU-4-N 合成
```
Step 1.1
13.8 g (35 mmol) 1 was dissolved in 150 ml 1,4-dioxane, 
1.0 g (1.4 mmol) palladium acetate, 10.4 g (0.1 mol) potassium acetate 
and 13.9 g (53 mmol) bis(pinacolato)boron were added. 
The mixture was heated under reflux overnight. 
After the usual workup 12.4 g (80%) of 2 was obtained as slightly yellow crystals.

Step 1.2
5.4 g (23 mmol) potassium phosphate was dissolved in 10 ml water. 
80 ml of toluene, 2.8 g (11.4 mmol) 1-bromo-2,6-difluoro-4-butyl benzene 3, 
6.3 g (14.2 mmol) 1, 42.2 mg (0.2 mmol) palladium acetate 
and 126.7 mg (0.3 mmol) S-Phos were added and the mixture was heated under reflux overnight. 
After the usual workup 3.42 g (62%) 3 (UUQU-4-N) was obtained as colorless crystals.

1H NMR (400 MHz, Chloroform-d) δ 7.16 (d, J=11.0 Hz, 2H), 7.07-6.99 (m, 2H), 
6.91-6.81 (m, 2H), 2.69-2.61 (m, 2H), 1.69-1.57 (m, 2H), 1.39 (h, J=7.4 Hz, 2H), 
0.96 (t, J=7.3 Hz, 3H).

Melting point: 44° C.
```

#### 實施例 2: UUZU-4-N 合成
```
Step 2.1
57.2 g (150 mmol) disodiumtetraborate-decahydrate, 2.8 g (4 mmol) palladium chloride, 
0.2 g (4 mmol) hydrazinium hydroxide, 39.4 g (0.2 mol) 1-bromo-3,5-difluorobenzene, 
42.8 g (0.2 mol) 5 and 200 ml of water were combined. 
The mixture was heated to reflux for 6 h. 
After the usual workup 50 g (88%) of 6 was obtained.

Step 2.2
50 g (175 mmol) 6 was dissolved in 300 ml tetrahydrofuran and cooled to −75° C. 
118 ml (193 mmol) of 15% n-butyllithium in hexane was added dropwise below −70° C. 
and the mixture was stirred at that temperature for 1.5 h. 
The mixture was poured onto 500 g of solid carbon dioxide and allowed to warm to room temperature. 
After the usual workup 46.8 g (82%) of 7 was obtained as colorless crystals.
```

#### 實施例 3: 電容測量
```
Example 1. A capacitance of 1.41 μF is determined using a 10 Hz alternating voltage. 
The resulting relative dielectric permittivity (εr) of the medium is 4.2·10^4.
```

## 關鍵教訓

### 1. Justia HTML 結構特殊
- `.claims .claim` 選擇器無效
- 必須使用文本正則匹配
- 優先匹配 "What is claimed is:" 後的內容

### 2. 超時問題
- `wait_until='networkidle'` 容易超時
- 改用 `domcontentloaded` + 手動等待
- 對超時專利切換數據源

### 3. 交叉驗證的必要性
- Justia 和 Google Patents 互補
- 單一數據源總有失靈時
- 建議同時抓取雙方並比對

### 4. Claim 1 的識別
**錯誤模式**: 抓到描述性段落而非正式請求項
- 開頭是 "However, these compositions..."
- 開頭是 "In addition to..."
- 開頭是 "These objects have been achieved..."

**正確模式**:
- 以 "What is claimed is:" 開頭
- 或直接以 "1." 開頭的段落
- 包含明確的技術特征描述

## 生成的文件
- `/tmp/patent_detailed_results.json`: 詳細抓取結果
- `/tmp/merck_patents_integrated.json`: 整合後數據
- `/tmp/merck_patents_detailed_report.md`: 完整 Markdown 報告

## 建議的改進工作流程
1. 先從 Justia 批量抓取基本字段
2. 對超時失敗的專利，改用 Google Patents 重試
3. 對 Claim 1，同時從 Justia 和 Google Patents 抓取，比對一致性
4. 對實施例，優先用 Justia（結構化較好）
5. 保存中間結果，避免重複抓取

## 相關技能
- browser-automation: 瀏覽器自動化基礎
- scrapling: 自適應網頁爬取
- web-researcher: 高級網絡研究
