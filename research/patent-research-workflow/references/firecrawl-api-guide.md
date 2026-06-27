# Firecrawl API 使用指南

## API 版本與參數變更

Firecrawl Python SDK 在 2026 年版本更新後，API 簽名發生變化：

### Search 方法
```python
# 正確用法
results = app.search(
    query="your query",
    limit=10,  # 不是 num_results
)

# 返回類型：SearchData
# 訪問結果：results.web (列表)
for result in results.web:
    url = result.url
    title = result.title
    description = result.description
```

### Extract 方法（已棄用）
```python
# 已標記為 deprecated，但仍可使用
result = app.extract(
    urls=["https://example.com"],  # 複數形式，不是 url
    schema=extraction_schema,
    prompt="Extract information"
)

# 返回結果訪問
data = result.data  # 提取的結構化數據
```

### Scrape 方法（推薦）
```python
# 提取 markdown 內容
result = app.scrape(
    url="https://example.com",
    formats=["markdown"],
)

content = result.markdown

# 或提取 JSON 格式（可自定義 schema）
result = app.scrape(
    url="https://example.com",
    formats=["json"],
)
```

## 常見錯誤與解決方案

### 錯誤 1: "unexpected keyword argument 'num_results'"
**原因**: 使用了舊版參數名稱  
**解決**: 改為 `limit`

### 錯誤 2: "unexpected keyword argument 'url'"
**原因**: `extract()` 需要 `urls` (複數)  
**解決**: 改為 `urls=[url]`

### 錯誤 3: "'SearchData' object has no attribute 'get'"
**原因**: `SearchData` 不是字典，需訪問 `.web` 屬性  
**解決**: 使用 `results.web` 迭代結果

### 錯誤 4: "No API key provided"
**原因**: 環境變量未設置或 SDK 初始化時未讀取  
**解決**: 確保在導入前設置 `FIRECRAWL_API_KEY` 環境變量

## 批量提取最佳實踐

1. **單次提取優於批量**: 每次調用只處理 1 個 URL，避免批量請求觸發限制
2. **使用 Scrape 而非 Extract**: Extract 已棄用，Scrape 更穩定
3. **添加延遲**: 相鄰請求間隔 2-3 秒
4. **錯誤處理**: 記錄失敗項目，稍後重試

## 測試 API 簽名
```python
import inspect
from firecrawl import FirecrawlApp

app = FirecrawlApp(api_key="your-key")

# 檢查方法簽名
print(inspect.signature(app.search))
print(inspect.signature(app.extract))
print(inspect.signature(app.scrape))
```

## 參考文檔
- Firecrawl 官方文檔: https://docs.firecrawl.dev/
- Python SDK: https://github.com/firecrawl/firecrawl/tree/main/libs/python
