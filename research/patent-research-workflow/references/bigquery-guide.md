# Google Patents BigQuery 使用指南

**更新日期**: 2026-05-20  
**適用場景**: 大規模專利搜索（10+ 篇），需要精確控制日期範圍、CPC 分類、申請人

---

## 為什麼選擇 BigQuery

### 優勢
1. **精確日期控制** - SQL 語法可嚴格控制 `filing_date BETWEEN '2020-01-01' AND '2026-12-31'`
2. **全球覆蓋** - 整合 USPTO、EPO、WIPO、JPO 等 100+ 國家數據
3. **CPC 分類支持** - 可精確搜索 `C09K19/30`（負介電各向異性）
4. **申請人搜索** - 支持 `LIKE '%Merck%'` 和 `LIKE '%EMD%'`
5. **批量導出** - 一鍵導出 JSON/CSV，支持自動化
6. **免費額度充足** - 每月 10GB 免費查詢量，一般調研用不完

### 與網頁爬取方案比較
| 特性 | BigQuery | Firecrawl/Crawl4AI |
|------|---------|-------------------|
| 日期範圍控制 | ✅ SQL 語法精確控制 | ❌ 無法控制 |
| 專利數量 | 10-50 個（精確） | 0-8 個（不穩定） |
| 數據來源 | Google Patents 數據庫 | Google Patents 網頁 |
| 自動化程度 | 高 | 中 |
| 成功率 | ~100% | 0-50% |

---

## 設置步驟

### 1. 註冊 Google Cloud 賬戶
- 網址：https://console.cloud.google.com/
- 免費註冊，需綁定信用卡（不會扣費，除非超過 10GB）

### 2. 創建新的 GCP 項目
- 點擊項目選擇器 → 新建項目
- 項目名稱：`patent-research`（或其他）

### 3. 啟用 BigQuery API
- 在項目中搜索 "BigQuery API"
- 點擊 "啟用"

### 4. 創建服務賬戶並下載 JSON 認證文件
- 前往：IAM 與管理 → 服務賬戶
- 創建服務賬戶
- 下載 JSON 密鑰文件
- **重要**：保存 JSON 文件到安全位置

### 5. 設置環境變量
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/credentials.json"
```

### 6. 安裝 Python 依賴
```bash
pip install google-cloud-bigquery pandas
```

---

## 使用示例

### 基本查詢
```python
from google.cloud import bigquery

client = bigquery.Client()

query = """
SELECT
  publication_number,
  title,
  abstract,
  filing_date,
  applicant
FROM
  `patents-public-data.patents.publications`
WHERE
  LOWER(applicant) LIKE '%merck%'
  AND filing_date BETWEEN DATE '2020-01-01' AND DATE '2026-12-31'
LIMIT 50
"""

query_job = client.query(query)
results = query_job.result()

for row in results:
    print(f"{row.publication_number}: {row.title}")
```

### 進階查詢（含 CPC 分類）
```sql
SELECT
  publication_number,
  title,
  abstract,
  filing_date,
  publication_date,
  applicant,
  ARRAY_AGG(cpc_codes.code) as cpc_codes
FROM
  `patents-public-data.patents.publications`,
  UNNEST(cpc) AS cpc_codes
WHERE
  (LOWER(applicant) LIKE '%merck%' OR LOWER(applicant) LIKE '%emd%')
  AND filing_date BETWEEN DATE '2020-01-01' AND DATE '2026-12-31'
  AND (
    cpc_codes.code LIKE 'C09K19/30%' OR  -- 負介電各向異性
    cpc_codes.code LIKE 'C09K19/34%' OR  -- 液晶組合物
    cpc_codes.code LIKE 'C09K19/52%'     -- 液晶材料
  )
GROUP BY
  publication_number, title, abstract, filing_date, publication_date, applicant
ORDER BY
  filing_date DESC
LIMIT 50
```

---

## 數據導出

### 導出為 JSON
```python
import json

patents = []
for row in results:
    patents.append({
        "publication_number": row.publication_number,
        "title": row.title,
        "abstract": row.abstract,
        "filing_date": str(row.filing_date),
        "applicant": row.applicant,
        "cpc_codes": list(row.cpc_codes)
    })

with open("/tmp/patent_search_bigquery.json", "w", encoding="utf-8") as f:
    json.dump({
        "query": query,
        "count": len(patents),
        "patents": patents
    }, f, ensure_ascii=False, indent=2)
```

### 導出為 CSV
```python
import pandas as pd

# 轉換為 DataFrame
df = results.to_dataframe()

# 保存為 CSV
df.to_csv("/tmp/patent_search_bigquery.csv", index=False)
```

---

## 常見問題

### Q1: 認證失敗
**錯誤**: `DefaultCredentialsError: Your default credentials were not found`  
**解決**: 確認已設置 `GOOGLE_APPLICATION_CREDENTIALS` 環境變量

### Q2: 超過免費額度
**錯誤**: `403 Quota exceeded`  
**解決**: 檢查 BigQuery 使用量，考慮優化查詢或升級付費方案

### Q3: SQL 語法錯誤
**錯誤**: `400 Syntax error`  
**解決**: 檢查 SQL 語法，確保使用標準 SQL 語法

---

## 參考資源

- BigQuery 文檔：https://cloud.google.com/bigquery/docs
- Google Patents 數據集：https://console.cloud.google.com/bigquery?p=patents-public-data
- SQL 語法參考：https://cloud.google.com/bigquery/docs/sql-reference
- Python 客戶端：https://googleapis.dev/python/bigquery/latest/

---

## 相關腳本

- 搜索腳本：`scripts/patent_search_v5_bigquery.py`
- 完整評估報告：`/tmp/patent_datasource_final_report.md`
