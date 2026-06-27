# Date Map + Batch Size 設計記錄

## 日期：2026-05-22
## 來源：merck_lc_e2e_2024_2026.py 開發經驗

## Date Map 機制

搜索頁面 DOM 提取的日期資料透過 `date_map` 在搜索和提取兩個階段間傳遞。

### 搜索階段
`search_google_patents()` 返回 `Tuple[List[str], Dict[str, Dict]]`：
- 第一項：專利號列表 `patent_ids`
- 第二項：日期映射 `date_map`，key 為專利號，value 包含 `filing_date`、`priority_date`、`publication_date`、`date_source: "search_page_dom"`

### 全局合併
每次搜索輪次返回的 `round_dm` 合併到 `all_date_map`：
```python
ids, round_dm = search_google_patents(...)
all_date_map.update(round_dm)
```

### 提取階段回寫
提取成功後，將搜索頁日期補充到提取結果中：
```python
if result.get('success'):
    result.update(all_date_map.get(pid, {}))
```

回寫的欄位（來自搜索頁 DOM）：
- `filing_date` — 申請日
- `priority_date` — 優先權日
- `publication_date` — 公開日
- `date_source` — 值為 `"search_page_dom"` 或 `"extract_page_primary"`（提取頁面也有日期時以此為準）

### 設計決策
- `date_map` 不回寫 `year`：模板已有 `PATENT_YEAR`，保持分離避免冗餘
- 搜索頁日期是補充來源：提取頁面的 timeline 日期更準確，但搜索頁日期可在提取前就篩選

## Batch Size 控制

### 參數
- `BATCH_SIZE = 9`（固定，實測上限）
- 批次間暫停 10 秒

### 邏輯
```python
for i, pid in enumerate(patent_ids, 1):
    # ... 提取邏輯 ...
    
    # 批次間暫停：每 BATCH_SIZE 篇後休息
    if i > 1 and (i - 1) % BATCH_SIZE == 0:
        log(f"--- 批次 {i // BATCH_SIZE} 完成，暫停 10 秒 ---")
        time.sleep(10)
```

### 超時經驗
- 單批 ≤9 篇：穩定完成（每篇 ~8-12 秒，單批 ~90-110 秒）
- 單批 >10 篇：execute_code 超時風險顯著增加
- v12 雙引擎在 >5 篇時 CLI daemon 不穩定
- **生產首選**：v11.1 單引擎 Python + BATCH_SIZE=9

## Patch 工具縮排破壞教訓

使用 `skill_manage(action='patch')` 修改 Python 檔案時，替換段的縮排會被剝除至第 0 列。
發生在 L1005-1039 和 L1054-1102 兩個區塊，導致 `'return' outside function` 錯誤。

修復方式：寫獨立 Python 腳本 `/tmp/fix_indent.py`，定位丟失縮排的行號範圍，
批量添加 4 格縮排後寫回，再用 `compile()` 驗證語法。

**結論**：對 Python 檔案的重大修改，`write_file` 整段重寫比 `patch` 局部替換更安全。
