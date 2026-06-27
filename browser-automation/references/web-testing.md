---
name: web-testing
description: Web testing automation using Playwright, browser-use, and Firecrawl for comprehensive testing workflows.
---

# Web Testing Skill

這個技能提供完整的 Web 測試自動化能力，結合 Playwright、browser-use MCP 和 Firecrawl。

## 適用場景

- **功能測試**：測試網站功能是否正常
- **回歸測試**：確保新代碼不影響現有功能
- **性能測試**：測試頁面加載速度
- **可訪問性測試**：檢查無障礙功能
- **跨瀏覽器測試**：在不同瀏覽器上測試
- **API 測試**：測試後端 API 端點

## 核心工具

### 1. Playwright
- 快速、可靠的瀏覽器自動化
- 支持 Chromium、Firefox、WebKit
- 自動等待元素就緒
- 內置截圖和視頻錄製

### 2. browser-use MCP
- AI 驅動的瀏覽器操作
- 自然語言描述測試場景
- 智能元素識別

### 3. Firecrawl
- 網頁內容提取
- 結構化數據驗證
- 批量測試多個頁面

## 安裝步驟

```bash
# 1. 安裝 Playwright
pip install playwright
playwright install chromium

# 2. 安裝 pytest-playwright
pip install pytest-playwright

# 3. 安裝 browser-use (如果需要 AI 驅動)
cd /tmp
git clone https://github.com/Saik0s/mcp-browser-use.git
cd mcp-browser-use
uv sync
uv run playwright install chromium
```

## 測試範例

### 基本功能測試
```python
from playwright.sync_api import sync_playwright

def test_login():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://example.com/login")
        page.fill("#username", "testuser")
        page.fill("#password", "testpass")
        page.click("#login-btn")
        assert page.url == "https://example.com/dashboard"
        browser.close()
```

### 視覺回歸測試
```python
def test_visual_regression():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("https://example.com")
        page.screenshot(path="screenshot.png")
        browser.close()
```

## 最佳實踐

1. **使用 headless 模式**進行快速測試
2. **設置超時時間**避免卡住
3. **使用重試機制**處理網絡波動
4. **保存測試證據**（截圖、視頻、日誌）
5. **分離測試數據**與測試邏輯
6. **使用 fixture**管理瀏覽器實例

## 常見測試場景

| 場景 | 工具 | 說明 |
|------|------|------|
| 表單提交 | Playwright | 填寫、提交、驗證結果 |
| 頁面導航 | Playwright | 檢查鏈接、路由 |
| 內容驗證 | Firecrawl | 提取並比對內容 |
| 性能測試 | Playwright | 測量加載時間 |
| 可訪問性 | Playwright | 檢查 ARIA 屬性 |
| API 測試 | requests + Playwright | �截請求/響應 |

## 環境變數

```bash
export PLAYWRIGHT_BROWSERS_PATH=/home/appuser/.cache/ms-playwright
export TEST_TIMEOUT=30000  # 30 秒超時
export TEST_RETRIES=3      # 重試次數
```

## 參考資源

- [Playwright 文檔](https://playwright.dev)
- [pytest-playwright](https://playwright.dev/python/docs/intro)
- [browser-use GitHub](https://github.com/Saik0s/mcp-browser-use)
- [Firecrawl 文檔](https://docs.firecrawl.dev)
