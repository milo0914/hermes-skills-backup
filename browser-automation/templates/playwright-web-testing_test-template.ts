/**
 * Playwright 網頁測試模板
 * 用於快速創建新的瀏覽器測試
 */

import { describe, test, expect, beforeAll, afterAll, beforeEach } from 'bun:test';
import { BrowserManager } from '../src/browser-manager';

// 測試配置
const TEST_CONFIG = {
  baseUrl: process.env.TEST_BASE_URL || 'http://localhost:3000',
  timeout: 30000,
  viewport: {
    width: 1280,
    height: 720,
  },
};

describe('測試套件名稱', () => {
  let bm: BrowserManager;
  
  // 啟動瀏覽器
  beforeAll(async () => {
    bm = new BrowserManager();
    await bm.launch();
  });
  
  // 關閉瀏覽器
  afterAll(async () => {
    if (bm) {
      await bm.close();
    }
  });
  
  // 每個測試前重置狀態
  beforeEach(async () => {
    // 清理 cookies、localStorage 等
    // await bm.clearCookies();
  });
  
  // ─── 導航測試 ──────────────────────────────────
  
  describe('導航測試', () => {
    test('應該成功導航到頁面', async () => {
      const result = await bm.goto(TEST_CONFIG.baseUrl);
      expect(result).toContain('Navigated to');
      expect(result).toContain('200');
    });
    
    test('應該正確返回當前 URL', async () => {
      await bm.goto(TEST_CONFIG.baseUrl);
      const url = await bm.url();
      expect(url).toContain(TEST_CONFIG.baseUrl);
    });
  });
  
  // ─── 內容提取測試 ──────────────────────────────
  
  describe('內容提取測試', () => {
    beforeAll(async () => {
      await bm.goto(TEST_CONFIG.baseUrl);
    });
    
    test('應該提取頁面文本', async () => {
      const text = await bm.text();
      expect(text).toBeTruthy();
      expect(typeof text).toBe('string');
    });
    
    test('應該提取 HTML 內容', async () => {
      const html = await bm.html();
      expect(html).toContain('<!DOCTYPE html>');
    });
    
    test('應該使用選擇器提取內容', async () => {
      const html = await bm.html('body');
      expect(html).toBeTruthy();
    });
    
    test('應該提取所有連結', async () => {
      const links = await bm.links();
      expect(Array.isArray(links)).toBe(true);
    });
    
    test('應該發現表單', async () => {
      const forms = await bm.forms();
      expect(Array.isArray(forms)).toBe(true);
    });
  });
  
  // ─── 交互測試 ──────────────────────────────────
  
  describe('交互測試', () => {
    test('應該點擊元素', async () => {
      await bm.goto(TEST_CONFIG.baseUrl);
      
      // 查找可點擊元素
      const clickable = await bm.js(`
        () => {
          const el = document.querySelector('a, button');
          return el ? el.id || el.className || 'clickable' : null;
        }
      `);
      
      if (clickable) {
        // 執行點擊測試
        // await bm.click('selector');
      }
    });
    
    test('應該填充表單字段', async () => {
      await bm.goto(TEST_CONFIG.baseUrl + '/form');
      
      // 填充輸入框
      // await bm.fill('input[name="email"]', 'test@example.com');
      // await bm.fill('input[name="password"]', 'password');
      
      // 提交表單
      // await bm.click('button[type="submit"]');
    });
  });
  
  // ─── JavaScript 執行測試 ───────────────────────
  
  describe('JavaScript 執行測試', () => {
    test('應該執行簡單的 JS 表達式', async () => {
      await bm.goto(TEST_CONFIG.baseUrl);
      
      const title = await bm.js('document.title');
      expect(typeof title).toBe('string');
      
      const url = await bm.js('window.location.href');
      expect(typeof url).toBe('string');
    });
    
    test('應該返回對象為 JSON', async () => {
      await bm.goto(TEST_CONFIG.baseUrl);
      
      const obj = await bm.js('({ a: 1, b: 2 })');
      expect(obj.a).toBe(1);
      expect(obj.b).toBe(2);
    });
  });
  
  // ─── 等待與同步測試 ────────────────────────────
  
  describe('等待與同步測試', () => {
    test('應該等待元素出現', async () => {
      await bm.goto(TEST_CONFIG.baseUrl);
      
      // 等待元素
      // await bm.wait-for('#main-content');
      
      const exists = await bm.js('document.body !== null');
      expect(exists).toBe(true);
    });
    
    test('應該等待網絡請求', async () => {
      await bm.goto(TEST_CONFIG.baseUrl);
      
      // 等待 API 請求
      // const [response] = await Promise.all([
      //   bm.wait-for-response('**/api/**'),
      //   bm.click('[data-testid="load"]'),
      // ]);
      // expect(response.status()).toBe(200);
    });
  });
  
  // ─── 截圖測試 ──────────────────────────────────
  
  describe('截圖測試', () => {
    test('應該截取頁面截圖', async () => {
      await bm.goto(TEST_CONFIG.baseUrl);
      
      const screenshotPath = '/tmp/test-screenshot.png';
      // await bm.screenshot(screenshotPath);
      
      // expect(fs.existsSync(screenshotPath)).toBe(true);
    });
  });
  
  // ─── 錯誤處理測試 ──────────────────────────────
  
  describe('錯誤處理測試', () => {
    test('應該處理導航錯誤', async () => {
      try {
        await bm.goto('https://invalid-url-that-does-not-exist.com');
      } catch (error) {
        expect(error).toBeDefined();
      }
    });
    
    test('應該處理元素未找到', async () => {
      await bm.goto(TEST_CONFIG.baseUrl);
      
      try {
        // await bm.click('#non-existent-element');
      } catch (error) {
        expect(error).toBeDefined();
      }
    });
  });
});

/**
 * 測試工具函數
 */

/**
 * 創建測試數據
 */
function createTestData() {
  return {
    user: {
      email: 'test@example.com',
      password: 'password123',
    },
  };
}

/**
 * 等待條件滿足
 */
async function waitForCondition(
  bm: BrowserManager,
  condition: () => Promise<boolean>,
  timeout: number = 5000
) {
  const start = Date.now();
  
  while (Date.now() - start < timeout) {
    if (await condition()) {
      return true;
    }
    await bm.wait(100);
  }
  
  throw new Error(`Timeout waiting for condition after ${timeout}ms`);
}
