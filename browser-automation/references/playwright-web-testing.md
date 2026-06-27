---
name: playwright-web-testing
description: Playwright 網頁測試驗證功能組件 - 使用 Playwright 進行網頁測試、瀏覽器自動化、網頁抓取和驗證的完整技能
version: "1.0.0"
license: MIT
compatibility: Works with all Hermes backends. Requires Node.js 18+ and Playwright installed.
metadata:
  author: hermeshub
  hermes:
    tags:
      - playwright
      - testing
      - browser-automation
      - web-testing
      - e2e
      - playwright-testing
    category: devops
    fallback_for_toolsets: [terminal, file]
required_environment_variables:
  - name: PLAYWRIGHT_BROWSERS_PATH
    prompt: Optional custom path for Playwright browsers
    help: Set custom browser installation path
    required_for: custom browser paths
---

# Playwright Web Testing - 網頁測試驗證功能

基於 gstack 的瀏覽器測試架構，提供完整的 Playwright 網頁測試、瀏覽器自動化和網頁驗證功能。

## 核心功能組件

### 1. 瀏覽器管理器 (Browser Manager)
- 無頭 Chromium 瀏覽器啟動與管理
- 瀏覽器會話狀態維護
- 多工作區隔離（每個項目獨立瀏覽器實例）
- 自動空閒關閉（30 分鐘無操作）

### 2. 命令系統 (Command System)
支援 ~70+ 個瀏覽器操作命令：

#### 導航命令
- `goto <url>` - 導航到指定 URL
- `back` - 後退
- `forward` - 前進
- `reload` - 重新加載頁面
- `url` - 獲取當前 URL

#### 讀取命令
- `text` - 獲取頁面純文本
- `html [selector]` - 獲取 HTML 內容
- `links` - 提取所有連結
- `forms` - 發現表單字段
- `accessibility` - 獲取 ARIA 樹
- `snapshot [-i]` - 獲取交互式快照（帶元素引用）
- `screenshot <path>` - 截圖

#### 寫入命令
- `click <selector>` - 點擊元素
- `fill <selector> <value>` - 填充輸入框
- `type <selector> <text>` - 打字（逐字）
- `press <key>` - 按鍵
- `select <selector> <value>` - 選擇選項
- `check <selector>` - 勾選複選框
- `uncheck <selector>` - 取消勾選

#### JavaScript 執行
- `js <expression>` - 執行 JS 表達式
- `eval <code>` - 執行 JS 代碼

#### 元命令
- `wait <ms>` - 等待指定毫秒
- `wait-for <selector>` - 等待元素出現
- `console` - 獲取控制台日誌
- `network` - 獲取網絡請求
- `dialog` - 處理對話框

### 3. 元素選擇系統
- CSS 選擇器：`#id`, `.class`, `div > p`
- 引用選擇器：`@e30` (來自 snapshot)
- XPath 選擇器：`//div[@id='foo']`
- 文本選擇器：`text=Submit`

### 4. 測試架構組件

#### 測試服務器
```typescript
import { startTestServer } from './test-server';
const testServer = startTestServer(0);
const baseUrl = testServer.url;
```

#### 測試結構
```typescript
import { describe, test, expect, beforeAll, afterAll } from 'bun:test';
import { BrowserManager } from './browser-manager';

let bm: BrowserManager;
let baseUrl: string;

beforeAll(async () => {
  testServer = startTestServer(0);
  baseUrl = testServer.url;
  bm = new BrowserManager();
  await bm.launch();
});

afterAll(async () => {
  await bm.close();
  testServer.server.stop();
});

describe('Navigation', () => {
  test('goto navigates to URL', async () => {
    const result = await bm.goto(baseUrl + '/basic.html');
    expect(result).toContain('Navigated to');
  });
});
```

### 5. 測試用例分類

#### 導航測試
- URL 導航
- 歷史導航（back/forward）
- 頁面加載狀態
- 重定向處理

#### 內容提取測試
- 純文本提取
- HTML 內容提取
- 元素選擇器查詢
- 連結和表單發現
- 可訪問性樹提取

#### 交互測試
- 點擊操作
- 表單填充
- 鍵盤輸入
- 文件上傳
- 拖放操作

#### JavaScript 執行測試
- 表達式求值
- 異步代碼執行
- 對象序列化
- 錯誤處理

#### 等待與同步測試
- 元素可見性等待
- 網絡空閒等待
- 自定義條件等待
- 超時處理

#### 截圖與視覺測試
- 頁面截圖
- 元素截圖
- 全頁截圖
- PDF 導出

### 6. 瀏覽器技能系統 (Browser Skills)

#### 技能結構
```
<skill-name>/
├── SKILL.md          # 技能描述和 frontmatter
├── script.ts         # Playwright 腳本
├── script.test.ts    # 測試文件
├── fixtures/         # 測試數據
└── _lib/            # 依賴庫
```

#### SKILL.md Frontmatter
```yaml
---
name: scrape-hn-frontpage
description: 抓取 Hacker News 首頁新聞
host: news.ycombinator.com
triggers:
  - scrape hn frontpage
  - get hacker news stories
args:
  - name: limit
    description: 最大故事數量
trusted: false
---
```

### 7. 安全機制

#### 令牌註冊表
- 作用域令牌（scoped tokens）
- 一次性令牌
- 權限分級（只讀/讀寫/管理）

#### 環境隔離
- 環境變量過濾
- 工作目錄鎖定
- 進程權限控制

#### 內容安全
- CSP 策略執行
- 腳本注入防護
- 跨域請求限制

### 8. 性能優化

#### 緩存策略
- 瀏覽器實例複用
- 會話狀態持久化
- 資源緩存（cookies、localStorage）

#### 並發控制
- 請求隊列
- 速率限制
- 資源鎖定

## 使用流程

### 快速開始
```bash
# 1. 安裝依賴
bun install
bun playwright install chromium

# 2. 構建瀏覽器等件
bun run build

# 3. 設置環境變量
export B=./browse/dist/browse

# 4. 運行測試
bun test
```

### 創建新的測試
```typescript
// test/my-test.test.ts
import { describe, test, expect } from 'bun:test';
import { BrowserManager } from '../src/browser-manager';

describe('My Test', () => {
  let bm: BrowserManager;
  
  beforeAll(async () => {
    bm = new BrowserManager();
    await bm.launch();
  });
  
  afterAll(async () => {
    await bm.close();
  });
  
  test('should work', async () => {
    await bm.goto('https://example.com');
    const text = await bm.text();
    expect(text).toContain('Example');
  });
});
```

### 運行特定測試
```bash
# 運行所有測試
bun test

# 運行特定文件
bun test test/my-test.test.ts

# 運行匹配模式的測試
bun test -t "should work"

# 帶頭模式運行（可見瀏覽器）
bun test --headed
```

## 測試最佳實踐

### 1. 測試隔離
- 每個測試使用獨立頁面
- 測試間清理 cookies 和 localStorage
- 避免測試間依賴

### 2. 選擇器穩定性
- 優先使用 data-testid
- 避免使用易變的選擇器（如動態 class）
- 使用語義化選擇器

### 3. 等待策略
- 避免硬編碼等待（sleep）
- 使用顯式等待（wait-for）
- 設置合理的超時時間

### 4. 錯誤處理
- 捕獲並記錄詳細錯誤
- 失敗時自動截圖
- 提供重試機制

### 5. 性能優化
- 複用瀏覽器實例
- 使用無頭模式
- 禁用不必要的資源加載

## 常見測試場景

### 表單提交測試
```typescript
test('form submission', async () => {
  await bm.goto(baseUrl + '/form.html');
  await bm.fill('#email', 'test@example.com');
  await bm.fill('#password', 'secret123');
  await bm.click('button[type="submit"]');
  await bm.wait-for('.success-message');
  const text = await bm.text();
  expect(text).toContain('Success');
});
```

### 認證流程測試
```typescript
test('authentication flow', async () => {
  // 導航到登錄頁
  await bm.goto(baseUrl + '/login');
  
  // 填寫表單
  await bm.fill('input[name="username"]', 'testuser');
  await bm.fill('input[name="password"]', 'password');
  
  // 提交並等待導航
  await bm.click('button[type="submit"]');
  await bm.wait-for-navigation();
  
  // 驗證成功登錄
  expect(await bm.url()).toContain('/dashboard');
});
```

### API 攔截測試
```typescript
test('API interception', async () => {
  const requests: string[] = [];
  
  await bm.route('**/api/**', async route => {
    requests.push(route.request().url());
    await route.continue();
  });
  
  await bm.goto(baseUrl + '/');
  await bm.click('[data-testid="load-data"]');
  
  expect(requests).toContain(expect.stringContaining('/api/data'));
});
```

## 故障排除

### 常見問題

1. **瀏覽器啟動失敗**
   - 檢查 Playwright 是否正確安裝：`playwright --version`
   - 檢查瀏覽器二進制：`ls ~/.cache/ms-playwright/`
   - 重新安裝瀏覽器：`playwright install chromium`

2. **超時錯誤**
   - 增加默認超時：`setDefaultTimeout(30000)`
   - 檢查網絡延遲
   - 使用 `wait-for` 代替硬等待

3. **元素未找到**
   - 驗證選擇器正確性
   - 檢查元素是否可視
   - 使用 `wait-for` 等待元素

4. **內存洩漏**
   - 確保關閉瀏覽器實例
   - 及時清理頁面和上下文
   - 監控進程內存使用

## 參考資源

- [Playwright 官方文檔](https://playwright.dev/)
- [gstack BROWSER.md](/tmp/gstack/BROWSER.md)
- [Playwright 測試示例](/tmp/gstack/browse/test/)
- [瀏覽器管理器源碼](/tmp/gstack/browse/src/browser-manager.ts)

## 維護說明

此技能基於 gstack 的瀏覽器測試架構，定期更新以保持與最新 Playwright 版本兼容。
