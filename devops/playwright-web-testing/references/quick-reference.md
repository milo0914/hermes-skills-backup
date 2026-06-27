# Playwright 測試快速參考

## 命令速查表

### 導航命令
| 命令 | 語法 | 說明 |
|------|------|------|
| goto | `goto <url>` | 導航到 URL |
| back | `back` | 後退 |
| forward | `forward` | 前進 |
| reload | `reload` | 重新加載 |
| url | `url` | 獲取當前 URL |

### 讀取命令
| 命令 | 語法 | 說明 |
|------|------|------|
| text | `text` | 獲取頁面文本 |
| html | `html [selector]` | 獲取 HTML |
| links | `links` | 提取所有連結 |
| forms | `forms` | 發現表單 |
| accessibility | `accessibility` | 獲取 ARIA 樹 |
| snapshot | `snapshot [-i]` | 獲取快照 |
| screenshot | `screenshot <path>` | 截圖 |

### 寫入命令
| 命令 | 語法 | 說明 |
|------|------|------|
| click | `click <selector>` | 點擊 |
| fill | `fill <selector> <value>` | 填充 |
| type | `type <selector> <text>` | 打字 |
| press | `press <key>` | 按鍵 |
| select | `select <selector> <value>` | 選擇 |
| check | `check <selector>` | 勾選 |
| uncheck | `uncheck <selector>` | 取消勾選 |

### JavaScript 命令
| 命令 | 語法 | 說明 |
|------|------|------|
| js | `js <expression>` | 執行表達式 |
| eval | `eval <code>` | 執行代碼 |

### 等待命令
| 命令 | 語法 | 說明 |
|------|------|------|
| wait | `wait <ms>` | 等待毫秒 |
| wait-for | `wait-for <selector>` | 等待元素 |
| console | `console` | 獲取控制台 |
| network | `network` | 獲取網絡 |

## 選擇器速查

### CSS 選擇器
```
#id                    # ID 選擇器
.class                 # 類選擇器
div                    # 標籤選擇器
div > p               # 子選擇器
div p                 # 後代選擇器
input[type="text"]    # 屬性選擇器
a[href*="example"]    # 屬性包含
```

### 引用選擇器
```
@e30                   # 來自 snapshot 的元素引用
@c5                    # 來自快照的可點擊引用
```

### XPath 選擇器
```
//div[@id='foo']       # ID 匹配
//input[@type='text']  # 屬性匹配
//div[contains(@class, 'active')]
```

### 文本選擇器
```
text=Submit            # 精確匹配
text^=Submit           # 開始匹配
text$=mit              # 結束匹配
text*=Submit           # 包含匹配
```

## 常用測試模式

### 表單提交
```typescript
await bm.goto('/form');
await bm.fill('#email', 'test@example.com');
await bm.fill('#password', 'secret');
await bm.click('button[type="submit"]');
await bm.wait-for('.success');
```

### 認證流程
```typescript
await bm.goto('/login');
await bm.fill('input[name="user"]', 'admin');
await bm.fill('input[name="pass"]', 'password');
await bm.click('button[type="submit"]');
await bm.wait-for-navigation();
expect(await bm.url()).toContain('/dashboard');
```

### 數據提取
```typescript
await bm.goto('/products');
const text = await bm.text();
const links = await bm.links();
const html = await bm.html('.product-list');
```

### API 攔截
```typescript
await bm.route('**/api/**', async route => {
  console.log('API call:', route.request().url());
  await route.continue();
});
```

### 截圖
```typescript
await bm.goto('/page');
await bm.screenshot('/tmp/screenshot.png');
```

## 等待策略

### 隱式等待
```typescript
bm.setDefaultTimeout(10000);
```

### 顯式等待
```typescript
await bm.wait-for('#element');
await bm.wait-for-navigation();
await bm.wait-for-response('**/api/**');
```

### 自定義等待
```typescript
await bm.wait-for-function(() => {
  return document.querySelectorAll('.item').length > 5;
});
```

## 錯誤處理

### 捕獲錯誤
```typescript
try {
  await bm.click('#not-exists');
} catch (error) {
  console.error('Element not found:', error);
}
```

### 重試機制
```typescript
let attempts = 0;
while (attempts < 3) {
  try {
    await bm.goto(url);
    break;
  } catch (error) {
    attempts++;
    if (attempts === 3) throw error;
    await bm.wait(1000);
  }
}
```

## 性能優化

### 禁用資源
```typescript
await bm.route('**/*.{png,jpg,jpeg}', async route => {
  await route.abort();
});
```

### 設置視口
```typescript
await bm.setViewportSize({ width: 1280, height: 720 });
```

### 無頭模式
```typescript
const bm = new BrowserManager({ headless: true });
```

## 測試腳本

### 運行測試
```bash
# 所有測試
bun test

# 特定文件
bun test test/my-test.test.ts

# 匹配模式
bun test -t "should work"

# 帶頭模式
bun test --headed

# 調試模式
bun test --debug
```

### 配置腳本
```json
{
  "scripts": {
    "test": "bun test",
    "test:ui": "bun test --headed",
    "test:debug": "bun test --debug",
    "test:report": "bun test --reporter=html"
  }
}
```

## 最佳實踐

### ✅ 推薦
- 使用 data-testid 屬性
- 使用顯式等待
- 每個測試獨立
- 測試前清理狀態
- 使用語義化選擇器

### ❌ 不推薦
- 硬編碼等待（sleep）
- 測試間依賴
- 使用易變的選擇器
- 過長的測試用例
- 沒有斷言的測試

## 常見問題

### 元素未找到
```typescript
// 等待元素
await bm.wait-for('#element');

// 檢查是否在 iframe 中
await bm.selectFrame('iframe');

// 檢查是否可見
const visible = await bm.js(`
  document.querySelector('#element').offsetParent !== null
`);
```

### 超時錯誤
```typescript
// 增加超時
bm.setDefaultTimeout(30000);

// 使用自定義超時
await bm.wait-for('#element', { timeout: 10000 });
```

### 內存洩漏
```typescript
afterEach(async () => {
  await bm.clearCookies();
  await bm.evaluate(() => localStorage.clear());
});

afterAll(async () => {
  await bm.close();
});
```
