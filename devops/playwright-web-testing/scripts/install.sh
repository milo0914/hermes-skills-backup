#!/bin/bash

# Playwright 網頁測試環境安裝腳本
# 用於快速設置 Playwright 測試環境

set -e

echo "========================================="
echo "Playwright 測試環境安裝"
echo "========================================="

# 檢查 Node.js
if ! command -v node &> /dev/null; then
    echo "❌ 錯誤：未找到 Node.js"
    echo "請先安裝 Node.js: https://nodejs.org/"
    exit 1
fi

echo "✓ Node.js 版本：$(node --version)"

# 檢查 Bun (可選)
if command -v bun &> /dev/null; then
    echo "✓ Bun 版本：$(bun --version)"
    PACKAGE_MANAGER="bun"
else
    echo "⚠ 未找到 Bun，將使用 npm"
    PACKAGE_MANAGER="npm"
fi

# 創建項目目錄
PROJECT_NAME=${1:-"playwright-tests"}
echo ""
echo "創建項目：$PROJECT_NAME"

mkdir -p "$PROJECT_NAME"
cd "$PROJECT_NAME"

# 初始化項目
echo ""
echo "初始化項目..."
if [ "$PACKAGE_MANAGER" = "bun" ]; then
    bun init -y
    bun add -d @playwright/test playwright
else
    npm init -y
    npm install -D @playwright/test playwright
fi

# 創建目錄結構
echo ""
echo "創建目錄結構..."
mkdir -p tests
mkdir -p tests/fixtures
mkdir -p tests/pages
mkdir -p tests/utils
mkdir -p test-data
mkdir -p screenshots

# 創建配置文件
echo ""
echo "創建配置文件..."

cat > playwright.config.ts << 'EOF'
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
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  reporter: 'html',
  projects: [
    {
      name: 'chromium',
      use: { 
        browserName: 'chromium',
      },
    },
    {
      name: 'firefox',
      use: { 
        browserName: 'firefox',
      },
    },
    {
      name: 'webkit',
      use: { 
        browserName: 'webkit',
      },
    },
  ],
});
EOF

# 創建示例測試
echo ""
echo "創建示例測試..."

cat > tests/example.spec.ts << 'EOF'
import { test, expect } from '@playwright/test';

test.describe('示例測試套件', () => {
  test('應該加載頁面', async ({ page }) => {
    await page.goto('https://example.com');
    
    const title = await page.title();
    expect(title).toBe('Example Domain');
  });

  test('應該點擊連結', async ({ page }) => {
    await page.goto('https://example.com');
    
    const link = page.locator('a');
    await expect(link).toHaveAttribute('href', 'https://www.iana.org/domains/example');
  });

  test('應該截圖', async ({ page }) => {
    await page.goto('https://example.com');
    
    await page.screenshot({ path: 'screenshots/example.png' });
  });
});
EOF

# 創建頁面對象模型示例
cat > tests/pages/home.page.ts << 'EOF'
import { Page, Locator } from '@playwright/test';

export class HomePage {
  readonly page: Page;
  readonly heading: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
  }

  async goto() {
    await this.page.goto('/');
  }

  async getHeading(): Promise<string> {
    return await this.heading.textContent() || '';
  }
}
EOF

# 創建工具函數
cat > tests/utils/helpers.ts << 'EOF'
import { test } from '@playwright/test';

/**
 * 等待延遲
 */
export async function delay(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * 生成隨機字符串
 */
export function randomString(length: number): string {
  return Math.random().toString(36).substring(2, length + 2);
}

/**
 * 生成隨機郵箱
 */
export function randomEmail(): string {
  return `test_${randomString(10)}@example.com`;
}

/**
 * 捕獲錯誤並截圖
 */
export async function captureError(
  page: Page,
  name: string,
  fn: () => Promise<void>
): Promise<void> {
  try {
    await fn();
  } catch (error) {
    await page.screenshot({ path: `screenshots/error-${name}.png` });
    throw error;
  }
}
EOF

# 創建 package.json 腳本
echo ""
echo "更新 package.json..."

if [ "$PACKAGE_MANAGER" = "bun" ]; then
    bun add -d typescript @types/node
else
    npm install -D typescript @types/node
fi

# 添加腳本到 package.json
if [ "$PACKAGE_MANAGER" = "bun" ]; then
    bun run -e 'const pkg = require("./package.json"); pkg.scripts = { ...pkg.scripts, "test": "playwright test", "test:ui": "playwright test --ui", "test:headed": "playwright test --headed", "test:debug": "playwright test --debug", "test:report": "playwright show-report" }; fs.writeFileSync("package.json", JSON.stringify(pkg, null, 2));'
else
    npm pkg set scripts.test="playwright test"
    npm pkg set scripts.test:ui="playwright test --ui"
    npm pkg set scripts.test:headed="playwright test --headed"
    npm pkg set scripts.test:debug="playwright test --debug"
    npm pkg set scripts.test:report="playwright show-report"
fi

# 安裝 Playwright 瀏覽器
echo ""
echo "安裝 Playwright 瀏覽器..."
if [ "$PACKAGE_MANAGER" = "bun" ]; then
    bunx playwright install chromium
else
    npx playwright install chromium
fi

echo ""
echo "========================================="
echo "✓ 安裝完成！"
echo "========================================="
echo ""
echo "項目結構:"
echo "  $PROJECT_NAME/"
echo "  ├── tests/              # 測試文件"
echo "  │   ├── fixtures/       # 測試夹具"
echo "  │   ├── pages/          # 頁面對象"
echo "  │   └── utils/          # 工具函數"
echo "  ├── test-data/          # 測試數據"
echo "  ├── screenshots/        # 截圖"
echo "  ├── playwright.config.ts"
echo "  └── package.json"
echo ""
echo "可用命令:"
echo "  $PACKAGE_MANAGER test           # 運行所有測試"
echo "  $PACKAGE_MANAGER test:ui        # UI 模式"
echo "  $PACKAGE_MANAGER test:headed    # 帶頭模式"
echo "  $PACKAGE_MANAGER test:debug     # 調試模式"
echo "  $PACKAGE_MANAGER test:report    # 查看報告"
echo ""
echo "下一步:"
echo "  1. cd $PROJECT_NAME"
echo "  2. $PACKAGE_MANAGER test"
echo ""
