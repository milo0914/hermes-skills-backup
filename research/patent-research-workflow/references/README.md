# Patent Research Workflow Skill - README

**技能名稱**: patent-research-workflow  
**適用場景**: 大規模專利搜尋、提取與分析（10+ 篇專利）  
**難度等級**: L2  
**主要工具**: Firecrawl MCP + LLM Extraction  
**成功率**: 100%（10/10）

---

## 🚀 快速開始

### 1. 環境準備

```bash
# 安裝依賴
pip install firecrawl-py

# 設置 API Key（獲取：https://www.firecrawl.dev/）
export FIRECRAWL_API_KEY="fc-xxxxx"
```

### 2. 執行範例腳本

```bash
# 執行完整流程
cd /data/.hermes/skills/research/patent-research-workflow
python scripts/patent_research_example.py
```

### 3. 查看結果

```bash
# 查看生成的報告
cat /tmp/merck_negative_dielectric_patents_report.md

# 查看提取的原始數據
cat /tmp/extracted_patents.json
```

---

## 📁 文件結構

```
patent-research-workflow/
├── SKILL.md                          # 技能主文件
├── references/
│   ├── test-report-20260506.md       # 詳細測試報告（7 種方法比較）
│   └── README.md                     # 本文件
└── scripts/
    ├── patent_research_example.py    # 完整範例腳本
    └── README.md                     # 腳本說明
```

---

## 📖 使用說明

### 基本使用（推薦）

```python
from firecrawl import FirecrawlApp
import os

# 初始化
app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))

# 定義提取 schema
schema = {
    "type": "object",
    "properties": {
        "patent_number": {"type": "string"},
        "filing_date": {"type": "string"},
        "title": {"type": "string"},
        "technical_features": {"type": "array", "items": {"type": "string"}},
        "claim_1": {"type": "string"},
        "molecular_structure": {"type": "string"},
        "example_effects": {"type": "string"}
    }
}

# 搜尋
results = app.search(
    query="Merck KGaA negative dielectric liquid crystal patent",
    num_results=10,
    lang="en"
)

# 提取
for result in results.get("data", []):
    url = result.get("url", "")
    if "patent" in url:
        extracted = app.extract(
            url=url,
            schema=schema,
            prompt="Extract patent information"
        )
        print(extracted)
```

### 進階使用（完整腳本）

參考 `scripts/patent_research_example.py` 完整腳本，包含：
- 自動搜尋
- 批量提取
- 錯誤處理
- 報告生成

---

## 📊 性能比較

| 方法 | 成功率 | 時間（10 篇） | 推薦度 |
|------|--------|--------------|--------|
| Firecrawl LLM Extraction | 100% | 15-20 分鐘 | ⭐⭐⭐⭐⭐ |
| Playwright 批量爬取 | 20% | 10 分鐘 | ❌ 不推薦 |
| USPTO API | 100% | 30 分鐘 | ⭐⭐⭐⭐ |
| PatSnap | 100% | 10 分鐘 | ⭐⭐⭐⭐⭐（付費） |

---

## ⚠️ 常見問題

### Q1: 為什麼 Playwright 批量爬取會失敗？
**A**: Google Patents 對批量請求進行 IP 級別限制，前 2 次成功，第 3 次開始返回 46 字元錯誤頁面。詳見 `references/test-report-20260506.md`。

### Q2: Firecrawl API Key 如何獲取？
**A**: 至 https://www.firecrawl.dev/ 註冊免費帳號即可取得。

### Q3: 提取的字段不完整怎麼辦？
**A**: 調整 extraction schema 或 prompt，例如添加 field descriptions 或強調 "Focus on technical details"。

### Q4: 可以提取其他類型的專利嗎？
**A**: 可以，修改搜尋關鍵字即可，例如："Tesla battery technology patent"。

---

## 📚 參考資源

- **Firecrawl 文件**: https://docs.firecrawl.dev/
- **USPTO API**: https://www.uspto.gov/developers
- **Google Patents**: https://patents.google.com/
- **測試報告**: `references/test-report-20260506.md`

---

## 🎯 使用時機

### ✅ 適合使用
- 需要分析 10 篇以上專利
- 需要結構化提取技術細節
- 需要生成 Markdown 報告
- 遇到反爬機制阻擋

### ❌ 不適合使用
- 只需查詢 1-2 篇專利（直接手動查詢）
- 已有 PatSnap 等專業工具權限
- 需要即時結果（此流程需 30-35 分鐘）

---

## 📝 版本記錄

| 版本 | 日期 | 更新內容 |
|------|------|----------|
| 1.0.0 | 2026-05-19 | 初始版本，包含完整流程與測試報告 |

---

## 🔑 關鍵摘要

**一句話總結**: 大規模專利提取請用 Firecrawl LLM Extraction，避免使用 Playwright 直接批量爬取（20% 成功率）。

**核心流程**: 環境準備 → Firecrawl 搜尋 → LLM Extraction 提取 → Markdown 報告生成

**成功關鍵**: AI 驅動提取繞過反爬機制，100% 提取成功率

**失敗教訓**: Google Patents 批量請求必敗（IP 級別限制），重試無效，需換方法
