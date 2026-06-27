# v11 測試報告

## 測試日期: 2026-05-20

## 測試結果

| 指標 | v9 | v10-A | v11 | 變化 |
|------|-----|-------|-----|------|
| Claim 1 | 66.7% (6/9) | 66.7% (6/9) | **88.9% (8/9)** | +22.2% |
| 實施例 | 33.3% (3/9) | 33.3% (3/9) | 33.3% (3/9) | 持平 |
| 公開日 | 22.2% (2/9) | 0% (0/9) | **66.7% (6/9)** | +66.7% |
| 申請日 | N/A | 0% (0/9) | **100% (9/9)** | +100% |
| 專利號 | 77.8% (7/9) | 77.8% (7/9) | 55.6% (5/9) | -22.2% |
| 反爬阻擋 | 0/9 | 2/9 | **0/9** | 解決 |

## 逐案分析

### Google Patents (5 個)
| 專利 | Claim 1 | 日期 | 備註 |
|------|---------|------|------|
| US8399073B2 | ✅ 20798字元 (GP claims, 1.0) | pub:2009-12-17, filing:2011-06-21 | pub_date 可能是優先權日 |
| CN101407719B | ✅ 1900字元 (寬鬆1., 0.95) | pub:2008-03-28, filing:2008-03-28 | pub=filing 需語義修正 |
| US5576867A | ✅ 661字元 (寬鬆1., 1.0) | pub:1995-06-06, filing:1995-06-06 | 同上 |
| WO2010022891A1 | ✅ 9847字元 (GP claims, 1.0) | pub:2009-08-20, filing:2009-08-20 | 同上 |
| US7369204B1 | ✅ 1220字元 (寬鬆1., 1.0) | pub:2006-07-21, filing:2006-07-21 | 同上 |

### Justia (3 個)
| 頁面 | Claim 1 | 日期 | 備註 |
|------|---------|------|------|
| inventor/kazuaki-tarumi | ✅ 4848字元 (GP claims, 1.0) | filing:December 12, 2016 | 列表頁，非單一專利 |
| assignee/merck-patent-gmbh | ❌ 無匹配 | filing:September 29, 2023 | 列表頁 |
| patents-by-us-classification/349/182 | ✅ 19856字元 (GP claims, 1.0) | filing:April 1, 2022 | 分類頁 |

### ipqwery (1 個)
| 頁面 | Claim 1 | 日期 | 備註 |
|------|---------|------|------|
| 315-merck-patent-gmbh | ✅ 253字元 (寬鬆1., 0.95) | pub:2026-05-15, filing:2025-11-04 | 非標準專利頁面 |

## 關鍵發現

### 1. Google Patents 日期結構
日期不在 meta 標籤或 JSON-LD 中，而是在 `.event.style-scope.application-timeline` 元素的事件列表中：
- "2009-12-17 Application filed by Merck Patent GmbH" → 申請日
- "2013-03-19 Publication of US8399073B2" → 公開/授權日
- "2013-03-19 Application granted" → 授權日

v11 使用 `re.findall(r'\d{4}-\d{2}-\d{2}', text)` 提取日期序列，但未做語義區分導致 pub_date 和 filing_date 可能重複。v11.1 需用 JavaScript 提取帶語義標籤的日期。

### 2. Justia 反爬已解決
User-Agent + Cloudflare 等待（最多 16 秒）+ 延遲重試，9/9 全部成功提取。

### 3. 專利號提取下降原因
v9/v10 的 77.8% 主要來自 Google Patents URL 中的 `patent/XX123456` 格式。Justia 和 ipqwery 的 URL 格式不同：
- justia.com/inventor/... → 無專利號
- justia.com/assignee/... → 無專利號
- ipqwery.com/ipowner/... → 無專利號

需從頁面標題或內容中提取專利號。

### 4. Claim 1 突破原因
v11 增加了 "claims 區段定位" 策略：先搜索 CLAIMS/WHAT IS CLAIMED IS 等標記，從該位置開始匹配，避免全文誤匹配。7 種模式（比 v9 多 1 種）+ 置信度評分。

## playwright-cli 評估

### 安裝
```bash
cd /tmp && npm init -y && npm install @playwright/cli@latest
npx playwright-cli install-browser chromium  # 下載 ~290MB
```

### 測試結果
- `npx playwright-cli open --browser=chromium <url>` → 成功導航
- `npx playwright-cli --raw eval "..."` → 成功提取頁面內容
- **限制**: 需指定 `--browser=chromium`（默認 chrome 通道不可用）
- **速度**: 比Python Playwright慢（daemon 進程啟停開銷）
- **結論**: 適合單頁交互式調試，不適合批量提取

### v11 整合
v11 腳本支持 `--cli` 參數啟用 playwright-cli 模式，但默認關閉（Python Playwright 更快更穩定）。

## 待改進

1. 日期語義提取：用 JS evaluate 提取 application-timeline 中的帶語義日期
2. 專利號多域名提取：增加 Justia/ipqwery URL 模式
3. 實施例提取率：需改進識別邏輯（目前 33.3%）
4. 搜索結果質量：3/9 是列表頁而非專利頁面，需前端 URL 篩選
