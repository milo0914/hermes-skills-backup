# GRPO 規劃實戰報告 - Google Patents + Crawl4AI 改進

**報告生成時間**: 2026-05-20 14:30
**任務等級**: L3（高風險、開放式創新、需權衡取捨）
**GRPO 版本**: 1.1.0

---

## 📊 GRPO 執行摘要

### 任務分級
- **等級**: L3（複雜多步驟、需權衡取捨）
- **理由**: 需要改進搜索策略、提取邏輯、日期控制，涉及多個子任務和工具選擇

### 群體採樣結果
生成 5 個改進方案，評分範圍 1.30-1.75/2.0：

| 排名 | 方案 | 總分 | 關鍵優勢 | 關鍵劣勢 |
|------|------|------|----------|----------|
| 1 | 方案 E（USPTO API） | 1.75 | 官方權威、精確控制 | 需申請 API Key |
| 2 | 方案 D（browser-use） | 1.70 | 真實瀏覽器、最可靠 | 配置複雜、慢 |
| 3 | **方案 C（混合方案）** | **1.65** | 平衡方案、立即可用 | 需兩次工具調用 |
| 4 | 方案 A（改進搜索） | 1.40 | 簡單直接 | 依賴 Firecrawl |
| 5 | 方案 B（改進解析） | 1.30 | 技術可控 | 反爬難解 |

### 執行選擇
**選擇方案 C（混合方案）**，理由：
- ✅ 立即可用，無需額外設置
- ✅ 成功率高（70-80%）
- ✅ 結合 Firecrawl 和 Crawl4AI 優勢
- ✅ 可在 1-2 小時內完成

---

## 🧪 實測結果

### 執行統計
| 指標 | 目標 | 實際 | 達成率 |
|------|------|------|--------|
| 總提取數量 | 10+ | 9 | 90% |
| Claim 1 提取 | >80% | 0/9 (0%) | ❌ 失敗 |
| 實施例提取 | >50% | 3/9 (33%) | ⚠️ 部分成功 |
| 日期範圍符合 | 100% | 0/9 (0%) | ❌ 失敗 |
| 技術特點提取 | 3-5 項 | 2-3 項 | ⚠️ 部分成功 |

### 關鍵發現

#### ✅ 成功點
1. **Crawl4AI 爬取成功**: 9 個專利全部成功爬取，無 403 錯誤
2. **實施例提取改進**: 3/9 專利成功提取實施例（之前為 0）
3. **技術特點提取**: 每個專利提取 2-3 項技術特點
4. **手動解析可行**: 證明手動解析 markdown 是可行的

#### ❌ 失敗點
1. **Claim 1 提取全失敗**: 正則表達式不匹配 Google Patents markdown 格式
2. **日期範圍全超出**: 舊搜索結果都是 2020 年以前的專利
3. **專利號未提取**: 需要改進專利號提取邏輯

---

## 🔍 根本原因分析

### 問題 1: Claim 1 提取失敗（0%）

**現象**: 所有專利的 Claim 1 長度為 0 字元

**原因**:
1. Google Patents markdown 格式中 Claims 部分格式多變
2. 正則表達式 `r'Claims\s*\n+(.*?)'` 過於嚴格
3. 實際 markdown 中 Claims 可能跨越多行，且格式不固定

**改進方案**:
```python
# 更寬鬆的正則表達式
claim_patterns = [
    r'(?i)CLAIMS?\s*[:\.\n]\s*1\.\s+(.*?)(?=\n\s*2\.|\Z)',  # 寬鬆版
    r'(?i)What is claimed is:\s*\n+\s*1\.\s+(.*?)(?=\n\s*2\.|\Z)',  # 常見開頭
    r'(?i)1\.\s+A\s+\w+\s+\w+\s+comprising\s+(.*?)(?=\n\s*2\.|\Z)',  # 以 comprising 開頭
]

for pattern in claim_patterns:
    match = re.search(pattern, markdown, re.DOTALL)
    if match:
        return "1. " + match.group(1).strip()
```

### 問題 2: 日期範圍不符合（0%）

**現象**: 所有專利都是 2020 年以前

**原因**:
1. 舊搜索結果來自 v4 腳本，未控制日期範圍
2. Firecrawl 搜索不支持日期範圍語法
3. 提取後過濾無法解決根本問題

**改進方案**:
1. **短期**: 在搜索階段使用更精確的關鍵字（包含年份）
2. **中期**: 使用 USPTO API（需申請 Key）
3. **長期**: 使用 Google Patents BigQuery

### 問題 3: Crawl4AI BrowserConfig 參數錯誤

**現象**: `BrowserConfig.__init__() got an unexpected keyword argument 'args'`

**原因**: Crawl4AI 的 `BrowserConfig` 不支持 `args` 參數，與 Playwright 不同

**解決方案**:
```python
# ❌ 錯誤做法（不支持 args）
browser_config = BrowserConfig(
    headless=True,
    args=['--no-sandbox', '--disable-dev-shm-usage']  # 會報錯
)

# ✅ 正確做法（使用支持的參數）
browser_config = BrowserConfig(
    headless=True,
    verbose=False
)
crawler_config = CrawlerRunConfig(
    word_count_threshold=1,
    page_timeout=30000
)
```

---

## 🎯 GRPO 反思與策略更新

### 反思 1: 方案選擇的權衡

**原計劃**: 方案 C（混合方案）評分 1.65/2.0
**實際表現**: 部分成功（實施例 33%，Claim 1 0%）

**反思**:
- 方案 C 確實立即可用，但 Claim 1 提取邏輯準備不足
- 過度依賴手動解析，低估了 Google Patents markdown 格式的多樣性
- 應該在執行前先分析 markdown 樣本，再設計正則表達式

**策略更新**:
```
下次遇到類似任務:
1. 先爬取 3-5 個樣本
2. 分析 markdown 格式特徵
3. 設計針對性正則表達式
4. 驗證後再批量處理
```

### 反思 2: 日期範圍控制策略

**原計劃**: 提取後過濾
**實際表現**: 舊搜索結果全是 2020 年以前

**反思**:
- 提取後過濾是被動策略，無法解決根本問題
- 應該在搜索階段就控制日期範圍
- Firecrawl 搜索不支持日期語法是主要瓶頸

**策略更新**:
```
優先級:
1. 首選: USPTO API（支持日期範圍）
2. 次選: Google Patents BigQuery（SQL 控制）
3. 備選: Firecrawl 搜索 + 關鍵字包含年份
4. 最後: 提取後過濾（被動）
```

### 反思 3: 工具選擇的平衡

**Firecrawl vs Crawl4AI**:
- Firecrawl: 搜索強，提取弱（已棄用 extract）
- Crawl4AI: 提取強，搜索弱（無法處理動態內容）

**最佳組合**:
```
搜索：Firecrawl（搜索結果質量好）
  ↓
提取：Crawl4AI（無額度限制）
  ↓
解析：手動正則 + LLM 輔助
```

---

## 📝 改進行動計劃

### 立即執行（今天）
1. ✅ 改進 Claim 1 正則表達式（多模式匹配）
2. ✅ 添加專利號提取邏輯
3. ✅ 改進實施例識別（多模式）
4. ✅ 添加技術特點提取優化

### 短期改進（1-2 天內）
1. ⏳ 申請 USPTO API Key
2. ⏳ 測試 USPTO API 搜索
3. ⏳ 比較 USPTO vs Firecrawl 搜索結果

### 中期優化（1 週內）
1. ⏳ 設置 Google Patents BigQuery
2. ⏳ 建立專利數據庫本地緩存
3. ⏳ 開發自動化驗證流程

---

## 📊 成功指標更新

| 指標 | 原目標 | 修正後目標 | 備註 |
|------|--------|-----------|------|
| Claim 1 提取 | >80% | >60% | 需要多模式正則 |
| 實施例提取 | >50% | >40% | 部分網站格式特殊 |
| 日期範圍符合 | 100% | >80% | 需改進搜索策略 |
| 專利數量 | 10+ | 10+ | 可達成 |

---

## 🔧 實戰腳本

### 搜索腳本 v6（混合方案）
位置：`/data/.hermes/skills/research/patent-research-workflow/scripts/patent_search_v6_hybrid.py`

### 提取腳本 v6（混合方案）
位置：`/data/.hermes/skills/research/patent-research-workflow/scripts/patent_extract_v6_hybrid.py`

### 執行方式
```bash
# 1. 搜索
python3 patent_search_v6_hybrid.py

# 2. 提取
python3 patent_extract_v6_hybrid.py
```

---

## 📚 相關資源

- GRPO 規劃技能：`grpo-planning`
- 專利調研技能：`patent-research-workflow`
- Crawl4AI 文檔：https://github.com/unclecode/crawl4ai
- Firecrawl 文檔：https://docs.firecrawl.dev/

---

**報告生成者**: GRPO Planning Agent
**報告版本**: v6.1
**下次更新**: 完成 USPTO API 測試後
