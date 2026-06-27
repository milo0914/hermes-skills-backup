# patent-research-workflow 歷史心得（已停用）

> **停用日期**: 2026-05-21
> **停用原因**: Firecrawl 免費額度已用盡，此技能以 Firecrawl 為主體的流程無法繼續使用
> **替代技能**: `patent-playwright-scraper`（純開源 Playwright 方案，v12 雙引擎）
> **經驗整併**: Git/GitHub 操作、BigQuery 策略、GRPO 規劃、搜索策略已遷移至 patent-playwright-scraper

---

## 此技能的歷史貢獻

1. **建立了完整的專利調研工作流框架**：搜索→提取→報告→推送
2. **系統性測試了 7 種方法**，確認 Firecrawl LLM Extraction 是唯一批量提取成功方案
3. **記錄了大量失敗經驗**，避免後人重蹈覆轍
4. **發現 Google Patents 批量請求第 3 次開始觸發 IP 級別限制**
5. **建立了 GitHub 推送機制**（時間戳資料夾、壓縮檔、索引文件）

## Firecrawl 相關經驗（已過時，僅供參考）

### Firecrawl API 變遷
- `search()` 參數從 `num_results` 改為 `limit`，返回 `SearchData` 需訪問 `.web`
- `extract()` 已棄用，改用 `scrape(formats=["markdown"])`
- `extract()` 參數用 `urls`（複數）而非 `url`，返回需訪問 `.data`
- `scrape()` 用 `formats=["markdown"]` 提取內容

### Firecrawl 搜索限制
- `search()` 不支援複雜布林語法（如 `cpc:C09K19/30 AND filing_date:>=2020-01-01`）
- 只能用簡單關鍵字搜索，日期範圍需提取後過濾
- 免費額度有限，批量提取會快速耗盡

### 批量提取反爬經驗
- Google Patents 前 2 次請求成功，第 3 次開始返回 46 字元錯誤頁面
- IP 級別限制，重試機制無效
- Firecrawl LLM Extraction 能繞過（AI 驅動），但免費額度有限

## 仍可取的經驗（已遷移至 patent-playwright-scraper）

| 經驗 | 遷移目標 |
|------|---------|
| Git /tmp 初始化失敗解法 | patent-playwright-scraper → Git/GitHub 操作經驗 |
| Git Push 衝突解法 | 同上 |
| Tar 壓縮檔注意事項 | 同上 |
| BigQuery 搜索策略 | patent-playwright-scraper → 搜索策略與大規模調研 |
| GRPO 規劃方法論 | 同上 |
| 日期範圍控制策略 | 同上 |
| 搜索→提取→報告流程 | 同上 |

## 原始 SKILL.md 位置

完整原始文檔已不再作為技能加載，僅此歸檔文件保留歷史記錄。

---

**⚠️ 警告**: 此技能已停用。新專利調研任務請使用 `patent-playwright-scraper`。
