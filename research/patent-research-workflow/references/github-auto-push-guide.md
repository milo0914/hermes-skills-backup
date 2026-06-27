# GitHub 自動推送配置指南

**最後更新**: 2026-05-20  
**適用技能**: `patent-research-workflow`  
**相關腳本**: `scripts/push-patent-report-to-github-v3.sh`, `scripts/generate_patent_report_with_auto_push.py`

---

## 📋 概述

本指南說明如何配置和使用專利調研報告的自動推送功能，將生成的報告自動上傳到 GitHub 倉庫。

---

## 🎯 推送策略

### 時間戳資料夾策略
- ✅ 每次推送創建帶時間戳的資料夾（`YYYYMMDD_HHMMSS`）
- ✅ 保留所有歷史記錄，不會覆蓋舊資料
- ✅ 同時生成壓縮檔（`.tar.gz`）
- ✅ 自動維護 `REPORT_INDEX.md` 索引文件

### Token 處理策略
- ✅ 推送腳本已移除 Token 預檢
- ✅ 直接使用環境變量中的 `GITHUB_TOKEN`
- ✅ 如果 Token 不存在或無效，GitHub API 會返回 401 錯誤
- ✅ 避免冗長的前置檢查，讓 API 直接處理認證

**設計原理**:
- 預檢會產生冗長的錯誤提示，但實際推送時仍會被 GitHub API 拒絕
- 直接讓 API 處理認證更簡潔，錯誤信息更明確
- Python 腳本直接執行推送腳本，不進行額外檢查

---

## 🔧 環境配置

### HuggingFace Spaces 設置

1. 前往 Space Settings
2. 找到 **Variables and Secrets** 區塊
3. 點擊 **Add Secret**
4. 新增以下 Secrets：

```
FIRECRAWL_API_KEY = fc-xxxxxxxxxxxxxxxxxxxx
GITHUB_TOKEN = ghp_xxxxxxxxxxxxxxxxxxxx
```

5. 重啟 Space 使設置生效

### 驗證設置

在 Space 的 Terminal 中執行：
```bash
echo $FIRECRAWL_API_KEY
echo $GITHUB_TOKEN
```

如果顯示值（或前綴），表示設置成功。

---

## 🚀 使用方式

### 方法 1: 執行完整流程（推薦）

```bash
python3 /data/.hermes/skills/research/patent-research-workflow/scripts/generate_patent_report_with_auto_push.py
```

**執行流程**:
1. 🔍 搜索專利（使用 Firecrawl）
2. 📥 提取專利詳情（scrape 模式）
3. 📝 生成 Markdown 報告
4. 📦 **自動推送到 GitHub** ← 自動執行

### 方法 2: 手動推送

```bash
bash /data/.hermes/skills/research/patent-research-workflow/scripts/push-patent-report-to-github-v3.sh
```

**前提條件**:
- 報告文件已生成：`/tmp/merck_negative_dielectric_patents_final_report.md`
- 提取結果已保存：`/tmp/extracted_patents_v2.json`
- 搜索結果已保存：`/tmp/patent_search_results.json`

---

## 📦 推送後的 GitHub 倉庫結構

```
hermes-patent-research/
├── REPORT_INDEX.md                 # 索引所有報告
├── 20260520_074032/                # 時間戳資料夾
│   ├── README.md                   # 本次報告說明
│   ├── merck_negative_dielectric_patents_final_report.md
│   ├── extracted_patents_v2.json
│   └── patent_search_results.json
├── 20260520_074032.tar.gz          # 壓縮備份
└── ...                             # 更多歷史記錄
```

---

## ⚠️ 常見問題

### 1. Token 無效或過期

**現象**: GitHub API 返回 401 錯誤

**解決方案**:
1. 檢查 Token 是否過期
2. 重新生成 Personal Access Token
3. 確保 Token 有 `repo` 權限
4. 在 HuggingFace Spaces 後台重新設置 Secret

### 2. 倉庫已存在

**現象**: GitHub API 返回 "Repository already exists"

**解決方案**:
- 這是正常現象，腳本會繼續推送
- 如需重新開始，刪除 GitHub 上的倉庫後重試

### 3. 推送失敗

**可能原因**:
- GITHUB_TOKEN 未設置或無效
- 倉庫不存在且無法創建
- 網絡問題導致 GitHub API 不可用

**排查步驟**:
```bash
# 1. 檢查 Token
echo $GITHUB_TOKEN

# 2. 手動測試 API
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user

# 3. 檢查推送腳本輸出
bash -x /data/.hermes/skills/research/patent-research-workflow/scripts/push-patent-report-to-github-v3.sh
```

---

## 📝 設計決策記錄

### 為什麼移除 Token 預檢？

**修改前**:
```bash
if [ -z "$GITHUB_TOKEN" ]; then
  echo "❌ 錯誤：GITHUB_TOKEN 環境變數未設置"
  echo "請在 HuggingFace Spaces Secrets 中添加 GITHUB_TOKEN"
  exit 1
fi
```

**修改後**:
```bash
# 直接執行，不預檢
# GitHub API 會返回 401 錯誤（如果 Token 無效）
```

**原因**:
1. 預檢會產生冗長的錯誤提示，但實際推送時仍會被 GitHub API 拒絕
2. 直接讓 API 處理認證更簡潔，錯誤信息更明確
3. 避免在主觀檢查中產生不必要的錯誤提示
4. Python 腳本直接執行推送腳本，不進行額外檢查

### 為什麼使用時間戳資料夾？

**優點**:
- ✅ 保留所有歷史記錄
- ✅ 不會覆蓋舊資料
- ✅ 易於追蹤和審計
- ✅ 支持回滾和比較

**實現**:
```bash
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
TIMESTAMP_DIR="${OUTPUT_DIR}/patent-report-${TIMESTAMP}"
```

---

## 🔗 相關資源

- [GitHub Personal Access Token 文件](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- [HuggingFace Spaces Secrets 文件](https://huggingface.co/docs/hub/spaces-secrets)
- [patent-research-workflow 技能文檔](../SKILL.md)
