# 專利調研程序手冊 v2.0

**版本**: 2.0.0  
**更新日期**: 2026-06-04  
**適用範圍**: Merck KGaA 負介電液晶專利調研（及其他大規模專利調研任務）  
**前置技能**: `patent-playwright-scraper` (v1.2.15+)、`patent-research-workflow` (v5.2+)

---

## 目錄

1. [技能架構與版本演進](#1-技能架構與版本演進)
2. [從零開始的調研 SOP](#2-從零開始的調研-sop)
3. [搜索策略](#3-搜索策略)
4. [批量提取](#4-批量提取)
5. [EP 專利特殊處理](#5-ep-專利特殊處理)
6. [Δε 分類器 v13](#6-δε-分類器-v13)
7. [雙軌實施例提取](#7-雙軌實施例提取)
8. [技術要點生成](#8-技術要點生成)
9. [報告生成與驗證](#9-報告生成與驗證)
10. [進步性評判](#10-進步性評判)
11. [GitHub 推送](#11-github-推送)
12. [腳本 API 參考](#12-腳本-api-參考)
13. [介電常數同義詞清單](#13-介電常數同義詞清單)
14. [陷阱速查表](#14-陷阱速查表)
15. [USPTO OCR 變體處理](#15-uspto-ocr-變體處理)
16. [數據合併策略](#16-數據合併策略)
17. [品質驗證清單](#17-品質驗證清單)
18. [版本更新日誌](#18-版本更新日誌)

附錄 A: [申請人別名搜索矩陣](#附錄-a-申請人別名搜索矩陣)  
附錄 B: [CPC 分類代碼](#附錄-b-cpc-分類代碼)  
附錄 C: [報告模板結構](#附錄-c-報告模板結構)  
附錄 D: [Claim1 品質驗證規則](#附錄-d-claim1-品質驗證規則)  
附錄 E: [介電常數同義詞完整清單](#附錄-e-介電常數同義詞完整清單)

---

## 1. 技能架構與版本演進

### 1.1 技能層級

```
patent-playwright-scraper (class-level umbrella, v1.2.15)
├── SKILL.md — 核心指引（37 個陷阱、完整流程、腳本列表）
├── scripts/ — 所有提取、報告、推送腳本
├── templates/ — PROTECTION_RULES.md、報告模板
└── references/ — 手冊 v2.0（本文件）、同義詞清單、除錯記錄

patent-research-workflow (supplementary, v5.2)
├── SKILL.md — v13 分類器架構、陷阱 22-26
└── scripts/ — v13 主腳本 patent_extract_v13_refined.py
```

### 1.2 版本演進摘要

| 版本 | Claim1 | 實施例 | 日期 | Δε 分類 | 關鍵改進 |
|------|--------|-------|------|---------|---------|
| v8 | 55.6% | 44% | 0% | N/A | Playwright 直接訪問 |
| v9 | 66.7% | 33.3% | 22.2% | neg/pos 計數 | 6 種正則 |
| v11 | 88.9% | 33.3% | 100% | neg/pos 計數 | JS evaluate 日期 |
| v11.1 | 100% | 90%+ | 100% | neg/pos 計數 | 生產驗證 24/24 |
| v13 | 100% | 雙軌 | 100% | 四層分類器 | 3 篇誤判修正、instead_of 修復 |

📖 詳細版本歷史見 `patent-playwright-scraper/SKILL.md`「版本歷史」段落

---

## 2. 從零開始的調研 SOP

### 階段 0: 載入技能（必須先執行）

```python
# 在開始任何搜索或提取之前
skill_view(name='patent-playwright-scraper')
# 若涉及 Δε 分類，也載入
skill_view(name='patent-research-workflow')
```

### 階段 1: 搜索

1. 用 `assignee:` 語法 + 技術目標詞構造搜索 URL
2. 滾動加載（5+ 次）觸發動態渲染
3. 多輪搜索：覆蓋所有 assignee 別名
4. 日期範圍：`after=priority:YYYYMMDD`（仍需提取後驗證）

📖 陷阱 8, 9, 10, 10a — 搜索相關

### 階段 2: 批量提取

1. 每批 ≤9 篇（避免超時）
2. 獨立進程提取每篇專利（避免 asyncio 污染）
3. 增量保存 JSON（每篇提取後立即寫入）

📖 陷阱 12, 16

### 階段 3: EP 專利 DOM 提取（如有 EP 專利）

1. 識別 EP 專利：專利號以 EP 開頭 或 claim1=0 chars
2. `page.evaluate()` 從 `<ol class="claims"><li class="claim">` DOM 提取
3. Description 三層回退：`div.description` → `div.publication-body` → `inner_text + 正則`

📖 陷阱 24, 27

### 階段 4: Δε 分類（v13 四層分類器）

1. 呼叫 `classify_delta_epsilon_v13(patent_data)` — 輸入為單一 Dict
2. 四層優先序：Abstract(0.95) > Claim(0.90) > Examples(0.85) > Desc tail(0.60)
3. AMBIGUOUS 輸出需檢查原因（截斷 vs 合理 AMBIGUOUS）

📖 陷阱 13, 23, 37

### 階段 5: 實施例提取（雙軌）

1. Track 1：全文 inner_text 提取（200K+ chars）→ 正則定位 Example 區段
2. Track 2：段落號定位（[0150]+ 區域）→ 關鍵字匹配
3. 品質評判：example_count=0 標記為 failure

📖 陷阱 11, 20, 22

### 階段 6: 技術要點生成

1. `extract_patent_sections()` 提取 Background/Summary/Claims/Examples
2. `build_tech_feature_prompt()` 組裝 5 維度 prompt
3. delegate_task 分批（每批 3 子代理）
4. 驗證：每篇 ≥150 字、每維度 ≥30 字、含分子洞見

📖 陷阱 15, 22, 25

### 階段 7: 報告生成 + 回填

1. `generate_report_v4.py` 生成 Markdown
2. JSON→MD 回填：tech_features 從 JSON 寫回 .md（替換舊式流水線條列）
3. 驗證三項修正：分子洞見 + Claim1 + Abstract

📖 陷阱 26, 30

### 階段 8: 進步性評判（如需要）

1. 7 欄位結構化評判框架
2. 反向行號插入避免偏移
3. 30 項完整性驗證

📖 陷阱 31, 32, 33

### 階段 9: 推送 + 驗證

1. `.env` 讀取 token + `GIT_ASKPASS` 推送
2. clone GitHub repo 確認推送內容
3. 文件大小對照

📖 陷阱 14, 19, 21

---

## 3. 搜索策略

### 3.1 Google Patents URL 構造

```python
# ✅ 正確：assignee 語法 + 技術目標詞
url = 'https://patents.google.com/?assignee="Merck Patent GmbH"&q="contrast"+"liquid crystal"&after=priority:20230101'

# ❌ 錯誤：Merck 當作通用關鍵字
url = 'https://patents.google.com/?q=Merck+negative+dielectric+liquid+crystal'
```

### 3.2 多輪搜索矩陣

至少 6-8 組搜索（2-3 個核心 assignee × 2-3 組關鍵字），合併去重。

📖 附錄 A: 申請人別名搜索矩陣

### 3.3 日期控制

- `after=priority:YYYYMMDD` 比 `filing_date=` 更有效，但仍非嚴格過濾
- 提取後程序化嚴格驗證（預期 30-60% 不在範圍內）

📖 陷阱 10

---

## 4. 批量提取

### 4.1 每批上限

```python
BATCH_SIZE = 9  # 每批 ≤9 篇，避免 execute_code 超時
```

### 4.2 進程隔離

```python
# ✅ 每篇獨立進程
for url in urls:
    result = subprocess.run(
        ['python3', '/tmp/extract_single.py', url],
        capture_output=True, text=True, timeout=60
    )
```

📖 陷阱 16 — asyncio event loop 污染

### 4.3 增量保存

```python
# 每篇提取後立即寫入 JSON
for i, patent in enumerate(patents):
    result = extract_single(patent['url'])
    all_results.append(result)
    with open(f'/tmp/batch_{batch_id}_results.json', 'w') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
```

---

## 5. EP 專利特殊處理

### 5.1 Claims DOM 提取

EP 專利使用 `<ol class="claims"><li class="claim">` HTML 結構，正則提取成功率 0%。

```python
js_result = page.evaluate("""() => {
    const claims = [];
    const claimList = document.querySelector('ol.claims, .claims');
    if (claimList) {
        const items = claimList.querySelectorAll('li.claim, li');
        items.forEach((li, idx) => {
            const text = li.innerText.trim();
            if (text) claims.push({num: idx + 1, text: text});
        });
    }
    return {claims: claims};
}""")
```

📖 陷阱 24

### 5.2 Description 三層回退

1. `div.description` DOM 精確定位
2. `div.publication-body > div` 區塊遍歷
3. `page.inner_text('body')` + 正則分段

📖 陷阱 27

---

## 6. Δε 分類器 v13

### 6.1 四層分類架構

| 層級 | 來源 | 置信度 | 判定邏輯 |
|------|------|--------|---------|
| Layer 1 | Abstract | 0.95 | 直接匹配 "negative/positive dielectric anisotropy" |
| Layer 1b | Abstract 顯示模式 | 0.55-0.65 | VA→likely_neg, FFS/IPS→likely_pos（輔助，不單獨判定） |
| Layer 2 | Claim 1 | 0.90 | 法律界定中的 DA 描述 |
| Layer 3 | Examples Δε 值 | 0.85 | Δε = -3.8 → neg, Δε = +5.2 → pos |
| Layer 4a | Description tail | 0.60 | 後 20% 文本的 neg/pos 計數 |
| Layer 4b | Description "instead of" | 0.70 | "negative DA instead of ... positive" 語義模式 |

### 6.2 API

```python
from patent_extract_v13_refined import classify_delta_epsilon_v13

# 輸入：單一 Dict（不可用 abstract keyword argument）
patent_data = {
    'abstract': '...LC medium having negative dielectric anisotropy...',
    'claim1': '...',
    'description': '...',
    'title': '...'
}
result = classify_delta_epsilon_v13(patent_data)

# 輸出
# result = {
#     'is_negative_da': True,
#     'classification': 'confirmed_neg',  # confirmed_neg/pos, likely_neg/pos, AMBIGUOUS
#     'confidence': 0.95,
#     'layer': 'abstract',
#     'evidence': [{'source': 'judgment', 'detail': '...'}],
#     'warnings': ['...']
# }
```

### 6.3 "instead of" 正則

```python
# 容納最多 40 字元間隙文字
instead_neg = re.findall(
    r'negative\s+dielectric\s+anisotropy\s+instead\s+of\s+.{0,40}?positive',
    description, re.IGNORECASE
)
```

📖 陷阱 25

### 6.4 AMBIGUOUS 處理原則

- 截斷導致 → 標記「需全文提取後重新分析」
- 專利本身不含 DA 正負 → 標記「合理 AMBIGUOUS」
- **不要為了降低 AMBIGUOUS 率而降低閾值**

📖 陷阱 26

### 6.5 v13 離線測試結果（18 篇專利）

| 指標 | 數值 |
|------|------|
| 確認判定 | 13/18 (72%) |
| 原誤判修正 | 3/3 (US12612551B2, US20250207032A1, US20250361444A1) |
| AMBIGUOUS（截斷） | 3 |
| AMBIGUOUS（合理） | 2 (EP4553132A1 微波, US20250085595A1 光散射) |
| 誤判率 | 0% (從 16.7% 降至 0%) |

📖 `patent-research-workflow/references/v13-offline-test-results.md`

---

## 7. 雙軌實施例提取

### 7.1 Track 1: 全文提取

```python
body = page.inner_text('body')  # 200K-350K chars
# 定位 Example 區段
example_pattern = r'(?:Example|EXAMPLE)\s*(?:Mixture\s+)?\d+[:\.\s]'
```

### 7.2 Track 2: 段落號定位

```python
# 高段落號區域（[0150]+）中的 Example 關鍵字
for para_num, para_text in paragraphs:
    if para_num >= 150 and re.search(r'(?:Example|Synthesis)\s+\d+', para_text):
        # 這是實施例段落
```

### 7.3 品質評判

```python
# example_count=0 標記為 failure（每篇專利必有實施例）
if result['example_count'] == 0:
    result['quality'] = 'failure'
```

📖 陷阱 11, 20, 22

---

## 8. 技術要點生成

### 8.1 段落提取

`extract_patent_sections()` 三層分段回退：
1. 標題行匹配（`BACKGROUND OF THE INVENTION` 等）
2. 啟發式分段（過渡段特徵詞）
3. 段落號回退（`[NNNN]` 逐段掃描）

📖 陷阱 15

### 8.2 5 維度摘要

1. 解決的問題
2. 核心發明
3. 關鍵技術特徵
4. 實施方式
5. 與先前技術差異

每維度 ≥30 字連貫論述，總長 ≥150 字，繁體中文，專利分析師語氣。

📖 陷阱 22 — 必須是融會理解的判斷性洞見

### 8.3 分子洞見驗證

```python
MOLECULAR_KEYWORDS = ["分子", "構造", "骨架", "化合物", "偶極", "極化", "環", "鍵", "端基", "連接基", "取代基"]
has_molecular_insight = any(kw in tech_point for kw in MOLECULAR_KEYWORDS)
```

📖 陷阱 30

---

## 9. 報告生成與驗證

### 9.1 v4 報告結構

六大章節：總覽表 → 各專利詳細分析 → 跨專利趨勢分析 → 參數數據總表 → 方法論 → 免責聲明

### 9.2 JSON→MD 回填（必須執行）

generate_report_v2.py 必定產生舊式「技術特點（重點工作）」，推送前必須從 JSON 回寫新式「技術要點」。

📖 陷阱 26

### 9.3 驗證腳本

```bash
python scripts/verify_report_structure.py <report.md>
```

使用寬鬆匹配，避免格式假陽性。

📖 陷阱 34, 35

---

## 10. 進步性評判

### 10.1 七欄位框架

1. 技術問題識別
2. 先前技術阻礙
3. 非常規方案
4. 實施例驗證
5. 協同效應
6. 進步性強度（⭐至⭐⭐⭐⭐）
7. 核心洞見

### 10.2 反向插入

從報告末尾往前逐篇插入，避免行號偏移。

📖 陷阱 32

---

## 11. GitHub 推送

### 11.1 推薦組合：.env + GIT_ASKPASS

```python
# Step 1: 從 .env 讀取 token
with open('/data/.hermes/.env', 'r') as f:
    for line in f:
        if line.startswith('GITHUB_TOKEN='):
            token = line.strip().split('=', 1)[1]
            break

# Step 2: ASKPASS 腳本隔離 token
with open('/tmp/git_askpass_helper.sh', 'w') as f:
    f.write('#!/bin/bash\necho "' + token + '"')
os.chmod('/tmp/git_askpass_helper.sh', 0o755)

# Step 3: 推送
env = os.environ.copy()
env['GIT_ASKPASS'] = '/tmp/git_askpass_helper.sh'
env['GIT_TERMINAL_PROMPT'] = '0'
subprocess.run(['git', 'push', 'origin', 'main'], cwd=work_dir, env=env, timeout=60)
```

📖 陷阱 14, 19, 21

### 11.2 推送前檢查

- ✅ 使用壓縮檔 + 時間戳命名
- ✅ 先 `git pull --rebase` 再 push
- ❌ 禁止 `git add -A` 散檔推送（會覆蓋舊報告）

📖 陷阱 19

---

## 12. 腳本 API 參考

### 12.1 v13 主腳本

**路徑**: `patent-research-workflow/scripts/patent_extract_v13_refined.py`

| 函數 | 用途 | 輸入 | 輸出 |
|------|------|------|------|
| `classify_delta_epsilon_v13(patent_data)` | Δε 四層分類 | `Dict` | `Dict[str, Any]` |
| `extract_examples_dual_track(text)` | 雙軌實施例提取 | `str` | `List[Dict]` |
| `extract_claim1_v13(text)` | Claim1 提取 | `str` | `str` |
| `detect_truncation(text)` | 截斷檢測 | `str` | `Dict` |
| `batch_extract_v13(urls)` | 批量提取 | `List[str]` | `List[Dict]` |
| `extract_patent_full_v13(url)` | 完整提取 | `str` | `Dict` |
| `fetch_full_patent_text(url)` | 全文提取 | `str` | `str` |
| `reanalyze_existing_data_v13(data)` | 重新分析 | `Dict` | `Dict` |

### 12.2 v11.1 生產腳本

**路徑**: `patent-playwright-scraper/scripts/patent_extract_v11_1_improved.py`

生產首選，24/24 專利 100% 成功率。

### 12.3 E2E 腳本

**路徑**: `patent-playwright-scraper/scripts/merck_lc_e2e_2024_2026.py`

7 階段流程：搜索→提取→日期過濾→相關性過濾→LLM 技術要點→報告→推送。

### 12.4 報告腳本

| 腳本 | 用途 |
|------|------|
| `generate_report_v4.py` | v4 報告（含 Abstract/Claim1/分子洞見） |
| `verify_report_structure.py` | 寬鬆匹配版報告驗證 |
| `tech_feature_generator.py` | LLM 技術特點摘要生成 |

📖 完整腳本列表見 `patent-playwright-scraper/SKILL.md`「腳本文件」段落

---

## 13. 介電常數同義詞清單

### 核心概念（6 條）

1. dielectric anisotropy
2. dielectric anisotropy value
3. dielectric constant anisotropy
4. permittivity anisotropy
5. electrical anisotropy
6. dielectric anisotropic property

### Δε 書寫變體（8 條）

7. Δε
8. Δε value
9. delta epsilon
10. delta-epsilon
11. dielectric anisotropy Δε
12. dielectric anisotropy (Δε)
13. dielectric anisotropy (delta epsilon)
14. Δε of the liquid crystal

### 方向性表述（10 條）

15. negative dielectric anisotropy
16. positive dielectric anisotropy
17. dielectric anisotropy is negative
18. dielectric anisotropy is positive
19. having negative dielectric anisotropy
20. having positive dielectric anisotropy
21. dielectric anisotropy less than zero
22. dielectric anisotropy greater than zero
23. Δε < 0
24. Δε > 0

### 數值表示（8 條）

25. Δε = -3.0
26. Δε = +5.2
27. Δε of -3.8
28. Δε of about -3
29. dielectric anisotropy of -3
30. dielectric anisotropy value of approximately -3
31. Δεr (relative dielectric anisotropy)
32. Δn (birefringence, related but distinct)

### USPTO OCR 變體（4 條）

33. `.DELTA..epsilon.`
34. `&Delta;&epsilon;`
35. `&#916;&#949;`
36. `&Dgr;`

📖 詳細 OCR 正規化見第 15 章

---

## 14. 陷阱速查表

| # | 陷阱名稱 | 觸發條件 | 解決方案 |
|---|---------|---------|---------|
| 1 | Crawl4AI 版本兼容 | Crawl4AI 0.4.x 參數變化 | 用 Playwright 直接訪問 |
| 2 | Claim1 正則 | 單一正則失配 | 5-7 種模式多輪匹配 |
| 3 | 日期範圍控制 | filing_date URL 參數不嚴格 | 提取後程序化驗證 |
| 5 | Google Patents 日期 | meta 標籤不可靠 | JS timeline 語義提取 |
| 6 | Justia 反爬 | Cloudflare 挑戰 | UA + 輪詢等待 16s |
| 7a | 頁面內容提取 | querySelector 只返回標題 | inner_text + 正則 |
| 7 | 專利號 URL 格式 | Justia URL 無 patent/ 前綴 | 多域名正則 + 標題備用 |
| 8 | Merck 搜索無關專利 | "Merck" 當作關鍵字 | assignee: 語法 |
| 9 | 搜索動態加載 | 初始頁面只有 3-5 條 | 5+ 次滾動 |
| 10 | filing_date 不嚴格 | 58% 被過濾 | after=priority: + 後驗證 |
| 10a | 缺技術目標詞 | q="liquid crystal" 太寬 | 加 "contrast" 等目標詞 |
| 11a | 禁止 patch 改 Python | 縮排崩壞 | write_file 整檔重寫 |
| 11 | 裝置類無 Example N | 結構性限制 | 段落式提取或 embodiment |
| 12 | 批量超時 | 18+ 篇超 300s | 每批 ≤9 |
| 13 | neg/pos 計數誤判 | prior art 也提及 | v13 四層分類器 |
| 14 | GitHub Push 認證 | GITHUB_TOKEN 不在 env | GIT_ASKPASS |
| 15 | 技術特點需 LLM | 正則無法綜合判讀 | tech_feature_generator |
| 16 | Playwright asyncio | sync API 重複調用 | 獨立進程 |
| 17 | 報告質量清理 | false positive + 亂碼 | 三步清理流程 |
| 18 | 模組化 vs E2E | 單體難調試 | 迭代時用模組化 |
| 19 | 推送覆蓋舊報告 | 一般 git 流程 | 壓縮檔 + 時間戳 |
| 20 | 深度提取 | inner_text 200K+ chars | 正則批量提取 |
| 21 | .env token | env 中不可見 | dotenv 或逐行解析 |
| 22 | 技術要點流水線化 | LLM 列舉式摘要 | 融會理解 + ≥150 字 |
| 23 | 未載入 skill 就開始 | Agent 跳過 skill_view | 強制先載入 |
| 24 | EP Claims DOM | 正則 0% 成功率 | page.evaluate DOM |
| 25 | 批量技術要點 | delegate_task 限制 | 分批 3 子代理 |
| 26 | JSON→MD 未回填 | 報告推舊格式 | 推送前回填 tech_features |
| 27 | EP description 空 | JS evaluate 返回空 | 三層 DOM 回退 |
| 28 | Claim1 品質 | NMR/實施例/UI 前綴 | 5 種品質驗證規則 |
| 29 | 多來源合併 | 欄位不一致 | longest-wins / max-wins |
| 30 | 報告 v4 三項修正 | 缺分子洞見/Claim1/Abstract | 自動驗證三項 |
| 31 | 進步性評判框架 | 格式不統一 | 7 欄位結構化 |
| 32 | 批量區塊插入 | 前向插入行號偏移 | 反向插入 |
| 33 | 子代理 timeout | 600s 不足 | fallback 自行處理 |
| 34 | ⭐ 正則拆解 | findall 拆連續 ⭐ | 逐行 search |
| 35 | 驗證格式耦合 | 全形/半形差異 | 寬鬆匹配 |
| 36 | USPTO OCR 變體 | Δε 被編碼 | normalize_uspto_ocr() |
| 37 | v13 取代舊計數法 | 陷阱 13 誤判 16.7% | 四層分類器 |

---

## 15. USPTO OCR 變體處理

### 15.1 正規化函數

```python
def normalize_uspto_ocr(text: str) -> str:
    """將 USPTO OCR 變體正規化為 Unicode Δε"""
    text = re.sub(r'\.DELTA\.\.epsilon\.', 'Δε', text)
    text = re.sub(r'&Delta;', 'Δ', text)
    text = re.sub(r'&epsilon;', 'ε', text)
    text = re.sub(r'&#916;', 'Δ', text)
    text = re.sub(r'&#949;', 'ε', text)
    text = re.sub(r'&Dgr;', 'Δ', text)
    return text
```

### 15.2 使用時機

- 直接抓取 USPTO 頁面時（非 Google Patents）
- Google Patents 已自動轉換，生產流程通常不需此步驟

📖 陷阱 36

---

## 16. 數據合併策略

### 16.1 欄位級擇優

| 欄位類型 | 策略 | 說明 |
|---------|------|------|
| 文本（claim1, abstract） | longest-wins | 取最長非空值 |
| 計數（neg_da_count） | max-wins | 取最大值 |
| 列表（elastic_hits） | merge-dedup | 合併去重 |
| 布林（is_negative_da） | certainty-wins | True/False 優先於 None |
| 結構（physical_params） | key-merge | 合併鍵值對 |

### 16.2 回退順序

final_10_merged → extracted_all → final_list → tech_point_context → 預設值

📖 陷阱 29

---

## 17. 品質驗證清單

### 提取後驗證

```bash
python scripts/validate_extraction_results.py <output.json> -v
```

| 指標 | 門檻 |
|------|------|
| Date Range | ≥80% |
| Claim 1 | ≥80% |
| Examples | ≥50% |
| Patent Numbers | ≥95% |

### Claim1 品質驗證

```python
def validate_claim1(claim1: str) -> tuple[bool, str]:
    c = claim1.strip()
    if not c or len(c) < 50:
        return False, "EMPTY_OR_TOO_SHORT"
    if c.startswith('[00') or c.startswith('[01'):
        return False, "PARAGRAPH_NUMBER_PREFIX"
    if '1H NMR' in c[:50]:
        return False, "NMR_DATA"
    if 'Mixture Example' in c[:30]:
        return False, "MIXTURE_EXAMPLE_DATA"
    if re.match(r'Claims\s*\(\d+\)', c[:20]):
        return False, "UI_HEADER_PREFIX"
    return True, "OK"
```

📖 陷阱 28

### 報告驗證

```bash
python scripts/verify_report_structure.py <report.md>
```

區分「結構性驗證」（必須通過）和「格式性驗證」（可容忍）。

📖 陷阱 35

---

## 18. 版本更新日誌

| 版本 | 日期 | 更新內容 |
|------|------|---------|
| v1.0.0 | 2026-05-24 | 初始版本，16 章結構 |
| v2.0.0 | 2026-06-04 | 新增 v13 四層分類器、雙軌實施例、36 條同義詞、OCR 變體處理、37 條陷阱速查表、腳本 API 參考、數據合併策略、品質驗證清單 |

---

## 附錄 A: 申請人別名搜索矩陣

| 別名 | 搜索語法 | 備註 |
|------|---------|------|
| Merck Patent GmbH | `assignee:"Merck Patent GmbH"` | 最常見 |
| Merck KGaA | `assignee:"Merck KGaA"` | 母公司 |
| Merck Performance Materials Germany GmbH | `assignee:"Merck Performance Materials Germany GmbH"` | 2022+ 轉移 |
| EMD Chemicals Inc | `assignee:"EMD Chemicals Inc"` | 美國子公司 |
| Merck Electronics KGaA | `assignee:"Merck Electronics KGaA"` | 電子材料部門 |
| EMD Performance Materials Corp | `assignee:"EMD Performance Materials Corp"` | 美國 EMD 品牌 |
| Merck Display Materials Shanghai | `assignee:"Merck Display Materials"` | 中國子公司 |

---

## 附錄 B: CPC 分類代碼

| CPC 代碼 | 說明 |
|---------|------|
| C09K19/30 | 負介電各向異性液晶化合物 |
| C09K19/04 | 液晶組成物 |
| C09K19/34 | 液晶顯示元件 |
| C09K19/14 | 液晶化合物結構 |
| G02F1/13 | 液晶顯示裝置 |

---

## 附錄 C: 報告模板結構

```
# [調研主題] 專利調研報告

## 總覽表
（專利號、標題、日期、Δε、實施例數）

## 各專利詳細分析
### [Patent ID]
#### Abstract
#### Claim 1
#### 技術要點（融會理解版，含分子洞見）
#### 物理參數
#### 進步性評判（7 欄位）

## 跨專利趨勢分析
## 參數數據總表
## 方法論
## 免責聲明
```

---

## 附錄 D: Claim1 品質驗證規則

5 種常見品質問題及修復策略：

| 問題類型 | 診斷方法 | 修復策略 |
|---------|---------|---------|
| NMR 數據 | `'1H NMR' in c[:50]` | 重新定位 Claims section |
| 混合實施例 | `'Mixture Example' in c[:30]` | Playwright 重新提取 |
| UI 前綴 | `re.match(r'Claims\s*\(\d+\)', c[:20])` | 正則剝除前綴 |
| 缺 "1." 前綴 | EP 專利無編號 | 手動加 "1. " 前綴 |
| 殘留段落號 | `c.startswith('[00')` | 跳過段落號區段 |

---

## 附錄 E: 介電常數同義詞完整清單

見第 13 章「介電常數同義詞清單」的 36 條清單，包含：
- 核心概念（6 條）
- Δε 書寫變體（8 條）
- 方向性表述（10 條）
- 數值表示（8 條）
- USPTO OCR 變體（4 條）
