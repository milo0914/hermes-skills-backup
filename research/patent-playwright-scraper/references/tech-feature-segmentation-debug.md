# 技術特點段落分段 — 除錯記錄

## 日期: 2026-05-22

## 背景

將「技術特點」摘要從單純正則提取升級為 LLM 綜合判讀，需先從 Google Patents 頁面結構化提取 Background、Summary、Claims 等段落。

## Google Patents DOM 結構

- `document.querySelectorAll('section')` 返回多個 section
- 無 `itemprop` 屬性可用於定位
- Description 在 `section[5]`，Claims 在 `section[8]`（以索引+內容長度識別）
- JS 提取的 description 文本包含 `[0001]`、`[0002]` 等段落號

## 發現的三種專利格式

### 1. 有標題行（A1 公開申請、B2 已授權）

```
BACKGROUND OF THE INVENTION
[0002] The present invention relates to...
...
SUMMARY OF THE INVENTION
[0023] Surprisingly, it has now been found...
```

標題行匹配可正常工作。

### 2. 無標題行（Merck 液晶專利常見格式）

```
[0001] The present invention relates to liquid-crystal (LC) media...
[0002] One of the liquid-crystal display (LCD) modes used at present...
...
[0021] The invention is based on the object of providing novel...
...
```

無 `BACKGROUND OF THE INVENTION` 標題。Background 和 Summary 都嵌在段落號中。

### 3. 極端情況

US20240067879A1: 339K chars Description，`[0489]` 處出現 "prior art" 一詞（內文引用），被 `PRIOR ART` 正則誤配為標題行。

## 修復過程

### Bug 1: PRIOR ART 誤配

- **症狀**: `_split_by_heuristics` 返回 background=0，PRIOR ART 在 [0489] 位置匹配
- **根因**: `re.finditer(r'PRIOR\s+ART', full_desc, re.IGNORECASE)` 在 339K chars 全文搜索
- **修復**: (1) 限前 50K chars: `search_text = text[:50000]`; (2) 行首錨定: `r'(?:^|\n)\s*PRIOR\s+ART'`

### Bug 2: asyncio loop 衝突

- **症狀**: Playwright sync API 在 Jupyter/notebook 環境報 `asyncio.run() cannot be called from a running event loop`
- **根因**: Jupyter 已有 running event loop，sync_playwright 內部調用 asyncio.run() 衝突
- **修復**: 用 subprocess 隔離執行（`tech_feature_generator.py` 的 `--url` CLI 模式）

### Bug 3: DETAILED DESCRIPTION 標題匹配到 Description 開頭

- **症狀**: Description 區段開頭有 "Description\n" 字樣被 `DETAILED DESCRIPTION` 模式部分匹配
- **修復**: 行首錨定 + 要求全字匹配

## 啟發式分段核心邏輯

```python
TRANSITION_PATTERNS = [
    r'invention\s+is\s+based\s+on\s+the\s+object',
    r'Surprisingly,\s+it\s+has\s+now\s+been\s+found',
    r'The\s+present\s+invention\s+provides',
    r'invention\s+relates\s+to\s+a\s+liquid\s+crystal\s+medium\s+comprising',
]

END_OF_SUMMARY_PATTERNS = [
    r'The\s+invention\s+furthermore\s+relates\s+to',
    r'Mode\s+for\s+Carrying\s+Out',
    r'Detailed\s+Description',
]

for idx, (num, ptext) in enumerate(paragraphs):
    for pat in TRANSITION_PATTERNS:
        if re.search(pat, ptext, re.IGNORECASE):
            transition_idx = idx
            break

background = join paragraphs[:transition_idx]  # 上限 5000 chars
summary = join paragraphs[transition_idx:until END_OF_SUMMARY or 20 paras]  # 上限 4000 chars
```

## 驗證結果

| 專利 | 格式 | 分段策略 | Background | Summary | Claim1 | Claim2 |
|------|------|----------|------------|---------|--------|--------|
| US20240067879A1 | 無標題行 | 啟發式 | 5000 | 2870 | 1837 | 475 |
| US20250207032A1 | 有標題行 | 標題行匹配 | 5000 | 4000 | 1641 | 81 |
| US12612551B2 | 已授權 | 標題行匹配 | 5000 | 4000 | 1727 | 81 |
| US20250284151A1 | 有標題行 | 標題行匹配 | 5000 | 3483 | 1048 | 1115 |

## LLM 摘要品質（US20250284151A1 測試）

5 維度摘要由 delegate_task 調用 LLM 生成，品質良好：
1. 解決的問題: VA 顯示器響應時間和能耗問題
2. 核心發明: 高 clearing point + 高 Kavg + 低 Δn + 低 γ1 的 LC 介質
3. 關鍵技術特徵: Formula I + IIA/IIB/II/IIE/IIF 化合物組合
4. 實施方式: 具體化合物配比（未提取到實施例段落）
5. 與先前技術差異: 維持高 clearing point 同時降低 γ1

Prompt 長度: ~2550 tokens，在 gpt-4o-mini 128K context 內綽綽有餘。
