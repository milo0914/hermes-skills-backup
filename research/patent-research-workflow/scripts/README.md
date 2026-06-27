# 專利調研自動推送配置指南

## 📋 概述

本指南說明如何配置和使用專利調研報告的自動推送功能。

**重要**: 所有推送腳本已移至技能目錄，確保穩定性：
- 推送腳本：`/data/.hermes/skills/research/patent-research-workflow/scripts/push-patent-report-to-github-v3.sh`
- 完整流程：`/data/.hermes/skills/research/patent-research-workflow/scripts/generate_patent_report_with_auto_push.py`

---

## 🔧 HuggingFace Spaces 環境變量設置

在 HuggingFace Spaces 中運行時，環境變量需在 Space 後台設置：

### 步驟 1: 進入 Settings
1. 前往您的 Space 頁面
2. 點擊 **Settings** 標籤頁
3. 找到 **Variables and Secrets** 區塊

### 步驟 2: 添加 Secrets
點擊 **Add Secret**，新增以下兩個 Secrets：

| Name | Value | 說明 |
|------|-------|------|
| `FIRECRAWL_API_KEY` | `fc-xxxxxxxxxxxxxxxxxxxx` | Firecrawl API 密鑰 |
| `GITHUB_TOKEN` | `ghp_xxxxxxxxxxxxxxxxxxxx` | GitHub Personal Access Token |

### 步驟 3: 重啟 Space
添加完成後，點擊 **Restart Space** 使設置生效

### 驗證設置
在 Space 的 Terminal 中執行：
```bash
echo $FIRECRAWL_API_KEY
echo $GITHUB_TOKEN
```

如果顯示對應的值（或前綴），表示設置成功。

---

## 🚀 使用方式

### 方法 1: 執行完整流程（推薦）

```bash
# 在 Space 的 Terminal 中執行
python3 /data/.hermes/skills/research/patent-research-workflow/scripts/generate_patent_report_with_auto_push.py
```

**執行流程**:
1. 🔍 搜索專利（使用 Firecrawl）
2. 📥 提取專利詳情（Scrape + Markdown 解析）
3. 📝 生成 Markdown 報告
4. 📦 **自動推送到 GitHub**（如果 GITHUB_TOKEN 已設置）

### 方法 2: 手動推送

如果您已經有報告文件，可以單獨執行推送：

```bash
# 確保報告文件存在
ls -la /tmp/merck_negative_dielectric_patents_final_report.md

# 執行推送腳本
bash /data/.hermes/skills/research/patent-research-workflow/scripts/push-patent-report-to-github-v3.sh
```

---

## 📊 推送結果

推送成功後，GitHub 倉庫結構如下：

```
https://github.com/milo0914/hermes-patent-research/
├── REPORT_INDEX.md              # 所有報告的索引
├── 20260520_074032/             # 時間戳資料夾
│   ├── README.md                # 本次報告說明
│   ├── merck_negative_dielectric_patents_final_report.md
│   ├── extracted_patents_v2.json
│   └── patent_search_results.json
├── 20260520_074032.tar.gz       # 壓縮備份
└── ...                          # 更多歷史記錄
```

### 推送特點
- ✅ 每次推送創建帶時間戳的資料夾（格式：`YYYYMMDD_HHMMSS`）
- ✅ 同時生成壓縮檔（`.tar.gz`）
- ✅ 自動維護索引文件（`REPORT_INDEX.md`）
- ✅ 不會覆蓋舊資料，保留完整歷史記錄

---

## 🔍 故障排查

### 問題 1: 環境變量未設置
**現象**: 腳本報錯 "GITHUB_TOKEN 環境變數未設置"

**解決方案**:
1. 確認已在 HuggingFace Spaces 後台添加 Secrets
2. 確認已重啟 Space
3. 在 Terminal 中執行 `echo $GITHUB_TOKEN` 驗證

### 問題 2: 推送腳本找不到
**現象**: `bash: /data/.hermes/skills/research/patent-research-workflow/scripts/push-patent-report-to-github-v3.sh: No such file or directory`

**解決方案**:
1. 確認腳本路徑正確
2. 檢查技能目錄：`ls -la /data/.hermes/skills/research/patent-research-workflow/scripts/`
3. 如果腳本不存在，需重新安裝技能

### 問題 3: GitHub API 限制
**現象**: 推送失敗，提示 "API rate limit exceeded"

**解決方案**:
1. GitHub API 限制為每小時 5000 次（認證用戶）
2. 等待 1 小時後重試
3. 或考慮升級到 GitHub Pro

---

## 📝 GitHub Token 獲取

如果還沒有的 GitHub Token，請按照以下步驟獲取：

### 步驟 1: 進入 Settings
前往 https://github.com/settings/tokens

### 步驟 2: 生成新 Token
1. 點擊 **Generate new token (classic)**
2. 填寫備註（例如：Hermes Patent Research）
3. 勾選權限：
   - ✅ `repo` (完整控制私人倉庫)
   - ✅ `workflow` (如果需要操作 GitHub Actions)
4. 點擊 **Generate token**

### 步驟 3: 複製 Token
**重要**: Token 只會顯示一次！請立即複製並保存到安全的地方。

格式：`ghp_xxxxxxxxxxxxxxxxxxxx`（36 字元，以 `ghp_` 開頭）

---

## 📞 相關文件

| 文件 | 說明 |
|------|------|
| `/data/.hermes/skills/research/patent-research-workflow/scripts/push-patent-report-to-github-v3.sh` | GitHub 推送腳本 |
| `/data/.hermes/skills/research/patent-research-workflow/scripts/generate_patent_report_with_auto_push.py` | 完整流程腳本 |
| `/data/.hermes/skills/research/patent-research-workflow/SKILL.md` | 完整技能文檔 |
| `/tmp/merck_negative_dielectric_patents_final_report.md` | 生成的報告（執行後） |

---

## 💡 最佳實踐

1. **定期備份**: 每次執行專利調研後自動推送，保留完整歷史記錄
2. **環境變量管理**: 使用 HuggingFace Secrets 管理敏感信息
3. **版本控制**: 每次推送保留時間戳，方便追溯
4. **數據完整性**: 報告中所有專利均可在 Google Patents 驗證

---

**更新日期**: 2026-05-20  
**版本**: 1.0
