---
name: open-source-patent-tools
description: 開源專利調研工具集合 - 不依賴 Firecrawl/USPTO API 的純開源解決方案
author: Hermes Agent
version: 1.0.0
created: 2026-05-20
tags:
 - patent
 - open-source
 - crawl4ai
 - browser-use
 - scraping
category: research
---

# 開源專利調研工具集合

**目標**: 在不依賴 Firecrawl/USPTO API 的情況下，使用純開源工具進行專利調研

## 可用開源工具

### 1. Crawl4AI (已安裝)
- **狀態**: ✅ 已安裝並可用
- **位置**: `/tmp/mcp-browser-use/` (與 browser-use 共享環境)
- **特點**: 無額度限制，可爬取任意頁面
- **限制**: 無法處理 JavaScript 動態加載內容

### 2. browser-use (已安裝)
- **狀態**: ✅ 已安裝並可用
- **位置**: `/tmp/mcp-browser-use/`
- **特點**: 真實瀏覽器，可處理動態內容
- **限制**: 速度較慢，需配置 LLM API

### 3. Playwright (已安裝)
- **狀態**: ✅ 已安裝（通過 browser-use）
- **位置**: `~/.cache/ms-playwright/`
- **特點**: 真實瀏覽器，可處理動態內容
- **限制**: 需手寫腳本

### 4. BeautifulSoup4 + requests
- **狀態**: ⚠️ 需安裝
- **安裝**: `pip install beautifulsoup4 requests`
- **特點**: 輕量級，適合靜態頁面
- **限制**: 無法處理 JavaScript

## 推薦工作流程

### 流程 A: Crawl4AI + 手動解析（快速）
1. 使用 Crawl4AI 爬取專利頁面
2. 手動解析 markdown 提取 Claim 和實施例
3. 使用正則表達式過濾日期

### 流程 B: browser-use + 真實瀏覽器（可靠）
1. 使用 browser-use 訪問 Google Patents
2. 等待 JavaScript 加載完成
3. 提取專利 URL 列表
4. 批量提取專利詳情

### 流程 C: Playwright 直接腳本（可控）
1. 使用 Playwright 訪問 Google Patents
2. 執行搜索並等待結果加載
3. 提取專利 URL
4. 批量提取詳情

## 安裝檢查清單

```bash
# 1. 檢查 Crawl4AI
python3 -c "from crawl4ai import AsyncWebCrawler; print('Crawl4AI OK')"

# 2. 檢查 Playwright
python3 -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"

# 3. 檢查 BeautifulSoup
python3 -c "from bs4 import BeautifulSoup; print('BeautifulSoup OK')"

# 4. 安裝缺失組件
pip install beautifulsoup4 requests
```

## 已發現問題

### 問題 1: Crawl4AI BrowserConfig 參數
- **錯誤**: `BrowserConfig.__init__() got an unexpected keyword argument 'args'`
- **原因**: Crawl4AI 版本更新，參數變更
- **解決**: 移除 `args` 參數，使用標準配置

### 問題 2: Claim 1 提取失敗
- **錯誤**: 正則表達式過於嚴格
- **原因**: Google Patents markdown 格式變化
- **解決**: 使用多模式匹配（Claims、Claim 1、1. 等）

### 問題 3: 日期範圍控制
- **錯誤**: 舊搜索結果多為 2020 年以前
- **原因**: 無法在搜索階段控制日期
- **解決**: 
  1. 使用更精確的搜索詞（包含年份）
  2. 在提取後嚴格過濾
  3. 考慮使用 USPTO API 或 BigQuery

## 下一步行動

1. **立即**: 修復 Claim 1 提取邏輯
2. **短期**: 測試 browser-use 真實瀏覽器方案
3. **長期**: 申請 USPTO API Key 或設置 BigQuery
