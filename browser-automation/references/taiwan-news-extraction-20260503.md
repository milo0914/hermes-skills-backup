# Browser Automation 環境限制與解決方案

## 2026-05-03 會話記錄

### 任務目標
使用 browser-use MCP server 連接到 Google News Taiwan，搜尋當天台灣最熱門的 3 則新聞標題。

### 使用的配置
- **LLM Provider**: OpenRouter
- **Model**: nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free
- **API Key**: OpenRouter API Key
- **Browser**: Playwright Chromium (headless)

### 遇到的問題

#### 1. 瀏覽器路徑問題
**錯誤訊息：**
```
Error: Error calling tool 'run_browser_agent': Browser automation failed: 
Error getting browser path: No local browser path found after: uvx playwright install chrome
```

**原因：**
- `playwright install chrome` 需要 root 權限，無法在當前環境執行
- 已安裝的 Chromium 位於 `~/.cache/ms-playwright/chromium-1200/`
- browser-use 預設尋找 Chrome 而非 Chromium

**解決方案：**
```bash
# 1. 確認 Chromium 已安裝
ls -la ~/.cache/ms-playwright/

# 2. 設置為 headless 模式
mcp-server-browser-use config set -k browser.headless -v true

# 3. 重啟 server
uv run mcp-server-browser-use stop
uv run mcp-server-browser-use server
```

#### 2. DNS 解析失敗
**錯誤訊息：**
```
socket.gaierror: [Errno -2] Name or service not known
urllib3.exceptions.MaxRetryError: HTTPSConnectionPool(host='rss.udn.com', port=443)
```

**影響網站：**
- `rss.udn.com`
- `news.google.com` (部分環境)
- 其他外部新聞網站

**解決方案：**
- 在有完整 DNS 解析的環境中執行
- 使用 Firecrawl API 間接抓取（若有 API key）
- 通過 CDP 連接到有網路訪問的瀏覽器會話

#### 3. Google News 400 錯誤
**錯誤訊息：**
```html
<title>Error 400 (要求無效)!!1</title>
<meta name=viewport content="initial-scale=1, minimum-scale=1, width=device-width">
```

**原因：**
- Google News 需要有效的會話和請求頭
- 直接訪問可能被視為無效請求

**解決方案：**
- 使用 browser-use 的瀏覽器自動化功能（需要正確配置的瀏覽器）
- 使用 Firecrawl API 的 search 工具
- 避免直接抓取 Google News，改用其他新聞來源

#### 4. PTT 年齡驗證
**問題：**
PTT 需要年滿 18 歲確認才能訪問八卦版。

**解決方案：**
- 使用 persistent user data directory
- 通過 CDP 連接到已登入的瀏覽器

#### 5. ETtoday HTTP2 協議錯誤
**錯誤訊息：**
```
playwright._impl._errors.Error: Page.goto: net::ERR_HTTP2_PROTOCOL_ERROR
```

**原因：**
- 網站的 HTTP2 實現與 Playwright 兼容性問題

**解決方案：**
- 改用其他新聞來源
- 或調整瀏覽器配置

### 成功的測試

#### 1. Yahoo 奇摩新聞
成功抓取到標題，但主要是廣告：
```
1. Yahoo 新聞 - 最新新聞
2. Temu Clearance Sale
3. The Adult Industry's Dirty Secret For All-Night Staying Power
```

#### 2. PTT 連接成功
成功連接到 PTT，但遇到年齡驗證頁面。

### 建議的替代方案

#### 方案 1: 使用 Firecrawl API
```bash
export FIRECRAWL_API_KEY=fc-your-key
npx -y firecrawl-mcp scrape "https://tw.news.yahoo.com/"
```

#### 方案 2: 使用 CDP 連接現有瀏覽器
```bash
# 1. 啟動 Chrome 帶遠端調試
google-chrome --remote-debugging-port=9222

# 2. 設置 CDP URL
mcp-server-browser-use config set -k browser.cdp_url -v "http://localhost:9222"
mcp-server-browser-use config set -k browser.use_own_browser -v true

# 3. 重啟 server
uv run mcp-server-browser-use stop
uv run mcp-server-browser-use server
```

#### 方案 3: 使用 RSS 餵送
對於支持 RSS 的新聞網站，直接抓取 RSS 而非 HTML：
```python
import requests
response = requests.get('https://rss.udn.com/rss/rss0001.xml')
# 解析 XML 獲取新聞
```

### 環境檢查清單

在開始新聞抓取任務前，先執行以下檢查：

```bash
# 1. 檢查 server 狀態
uv run mcp-server-browser-use status

# 2. 檢查瀏覽器安裝
ls -la ~/.cache/ms-playwright/

# 3. 檢查 API Key
echo $OPENROUTER_API_KEY

# 4. 測試 DNS 解析
python3 -c "import socket; print(socket.gethostbyname('tw.news.yahoo.com'))"

# 5. 測試基本連接
curl -I https://tw.news.yahoo.com/
```

### 最佳實踐

1. **優先使用 Firecrawl API** - 如果有 API key，Firecrawl 處理反爬蟲機制更好
2. **使用 CDP 模式** - 連接到真實瀏覽器可避免許多問題
3. **準備多個新聞來源** - 不要只依賴單一網站
4. **設置適當的超時** - 新聞網站加載可能需要更長時間
5. **使用 headless 模式** - 在伺服器環境中更穩定

### 相關資源

- [browser-use GitHub](https://github.com/Saik0s/mcp-browser-use)
- [Firecrawl Documentation](https://docs.firecrawl.dev)
- [Playwright Browser Setup](https://playwright.dev/docs/browsers)
