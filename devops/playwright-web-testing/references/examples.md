# Playwright 網頁測試範例

## 基礎測試範例

### 1. 簡單導航測試
```typescript
import { describe, test, expect } from 'bun:test';
import { BrowserManager } from '../src/browser-manager';

describe('基礎導航測試', () => {
  let bm: BrowserManager;
  
  beforeAll(async () => {
    bm = new BrowserManager();
    await bm.launch();
  });
  
  afterAll(async () => {
    await bm.close();
  });
  
  test('頁面導航', async () => {
    await bm.goto('https://example.com');
    const url = await bm.url();
    expect(url).toContain('example.com');
  });
  
  test('頁面標題', async () => {
    await bm.goto('https://example.com');
    const title = await bm.js('document.title');
    expect(title).toBe('Example Domain');
  });
});
```

### 2. 表單交互測試
```typescript
import { describe, test, expect } from 'bun:test';
import { BrowserManager } from '../src/browser-manager';

describe('表單交互測試', () => {
  let bm: BrowserManager;
  let baseUrl: string;
  
  beforeAll(async () => {
    bm = new BrowserManager();
    await bm.launch();
    baseUrl = 'http://localhost:3000';
  });
  
  afterAll(async () => {
    await bm.close();
  });
  
  test('登錄表單提交', async () => {
    await bm.goto(baseUrl + '/login');
    
    // 填寫表單
    await bm.fill('input[name="username"]', 'testuser');
    await bm.fill('input[name="password"]', 'password123');
    
    // 提交表單
    await bm.click('button[type="submit"]');
    
    // 等待導航
    await bm.wait-for-navigation();
    
    // 驗證結果
    expect(await bm.url()).toContain('/dashboard');
  });
  
  test('表單驗證', async () => {
    await bm.goto(baseUrl + '/register');
    
    // 提交空表單
    await bm.click('button[type="submit"]');
    
    // 等待驗證錯誤
    await bm.wait-for('.error-message');
    
    const text = await bm.text();
    expect(text).toContain('Required');
  });
});
```

### 3. 內容提取測試
```typescript
import { describe, test, expect } from 'bun:test';
import { BrowserManager } from '../src/browser-manager';

describe('內容提取測試', () => {
  let bm: BrowserManager;
  
  beforeAll(async () => {
    bm = new BrowserManager();
    await bm.launch();
  });
  
  afterAll(async () => {
    await bm.close();
  });
  
  test('提取頁面文本', async () => {
    await bm.goto('https://news.ycombinator.com');
    
    const text = await bm.text();
    expect(text).toContain('Hacker News');
  });
  
  test('提取連結', async () => {
    await bm.goto('https://news.ycombinator.com');
    
    const links = await bm.links();
    expect(links.length).toBeGreaterThan(0);
    expect(links[0]).toContain('href');
  });
  
  test('提取特定元素', async () => {
    await bm.goto('https://news.ycombinator.com');
    
    const html = await bm.html('#hnmain');
    expect(html).toContain('Hacker News');
  });
});
```

### 4. 等待與同步測試
```typescript
import { describe, test, expect } from 'bun:test';
import { BrowserManager } from '../src/browser-manager';

describe('等待與同步測試', () => {
  let bm: BrowserManager;
  
  beforeAll(async () => {
    bm = new BrowserManager();
    await bm.launch();
  });
  
  afterAll(async () => {
    await bm.close();
  });
  
  test('等待元素出現', async () => {
    await bm.goto('https://example.com');
    
    // 等待元素
    await bm.wait-for('#main-content');
    
    const exists = await bm.js('document.querySelector("#main-content") !== null');
    expect(exists).toBe(true);
  });
  
  test('等待網絡請求', async () => {
    await bm.goto('https://example.com');
    
    // 等待特定 API 請求
    const [response] = await Promise.all([
      bm.wait-for-response('**/api/**'),
      bm.click('[data-testid="load-data"]'),
    ]);
    
    expect(response.status()).toBe(200);
  });
  
  test('自定義等待條件', async () => {
    await bm.goto('https://example.com');
    
    // 等待自定義條件
    await bm.wait-for-function(() => {
      return document.querySelectorAll('.item').length > 5;
    });
    
    const count = await bm.js('document.querySelectorAll(".item").length');
    expect(count).toBeGreaterThan(5);
  });
});
```

### 5. API 攔截測試
```typescript
import { describe, test, expect } from 'bun:test';
import { BrowserManager } from '../src/browser-manager';

describe('API 攔截測試', () => {
  let bm: BrowserManager;
  
  beforeAll(async () => {
    bm = new BrowserManager();
    await bm.launch();
  });
  
  afterAll(async () => {
    await bm.close();
  });
  
  test('攔截 API 請求', async () => {
    const apiCalls: string[] = [];
    
    // 設置攔截器
    await bm.route('**/api/**', async route => {
      apiCalls.push(route.request().url());
      await route.continue();
    });
    
    await bm.goto('https://example.com');
    await bm.click('[data-testid="fetch-data"]');
    
    expect(apiCalls).toContainEqual(expect.stringContaining('/api/'));
  });
  
  test('修改 API 響應', async () => {
    await bm.route('**/api/data', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: 'mocked' }),
      });
    });
    
    await bm.goto('https://example.com');
    await bm.click('[data-testid="load"]');
    
    const text = await bm.text();
    expect(text).toContain('mocked');
  });
});
```

### 6. 截圖與視覺測試
```typescript
import { describe, test, expect } from 'bun:test';
import { BrowserManager } from '../src/browser-manager';
import * as fs from 'fs';
import * as path from 'path';

describe('截圖測試', () => {
  let bm: BrowserManager;
  const screenshotDir = '/tmp/screenshots';
  
  beforeAll(async () => {
    bm = new BrowserManager();
    await bm.launch();
    fs.mkdirSync(screenshotDir, { recursive: true });
  });
  
  afterAll(async () => {
    await bm.close();
  });
  
  test('頁面截圖', async () => {
    await bm.goto('https://example.com');
    
    const screenshotPath = path.join(screenshotDir, 'example.png');
    await bm.screenshot(screenshotPath);
    
    expect(fs.existsSync(screenshotPath)).toBe(true);
  });
  
  test('元素截圖', async () => {
    await bm.goto('https://example.com');
    
    const screenshotPath = path.join(screenshotDir, 'element.png');
    await bm.screenshot(screenshotPath, { selector: '#main' });
    
    expect(fs.existsSync(screenshotPath)).toBe(true);
  });
});
```

## 進階測試技巧

### 1. 測試重試機制
```typescript
test('帶重試的測試', async () => {
  let attempts = 0;
  
  while (attempts < 3) {
    try {
      await bm.goto('https://flaky-site.com');
      await bm.wait-for('#content');
      break;
    } catch (error) {
      attempts++;
      if (attempts === 3) throw error;
      await bm.wait(1000);
    }
  }
});
```

### 2. 測試超時控制
```typescript
test('自定義超時', async () => {
  bm.setDefaultTimeout(10000);
  
  await bm.goto('https://slow-site.com');
  await bm.wait-for('#content', { timeout: 15000 });
});
```

### 3. 測試並行執行
```typescript
test.describe.parallel('並行測試', () => {
  test('測試 1', async () => {
    const bm = new BrowserManager();
    await bm.launch();
    await bm.goto('https://example.com/1');
    await bm.close();
  });
  
  test('測試 2', async () => {
    const bm = new BrowserManager();
    await bm.launch();
    await bm.goto('https://example.com/2');
    await bm.close();
  });
});
```

## 測試配置

### playwright.config.ts
```typescript
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  expect: {
    timeout: 5000,
  },
  use: {
    headless: true,
    viewport: { width: 1280, height: 720 },
    actionTimeout: 10000,
  },
  reporter: 'html',
});
```

### 測試腳本
```json
{
  "scripts": {
    "test": "bun test",
    "test:headed": "bun test --headed",
    "test:debug": "bun test --debug",
    "test:report": "bun test --reporter=html"
  }
}
```
