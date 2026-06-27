# Git 在 /tmp 目錄的權限問題測試報告

**測試日期**: 2026-05-20  
**問題編號**: GIT-TMP-001  
**影響範圍**: 所有需要在 /tmp 目錄執行 git 操作的場景

---

## 問題描述

在 `/tmp` 目錄下執行 `git init` 時遇到以下錯誤：

```
fatal: detected dubious ownership in repository at '/tmp'
To add an exception for this directory, call:
	git config --global --add safe.directory /tmp
```

或

```
fatal: not in a git directory
```

**根本原因**: 
- `/tmp` 目錄通常由 root 用戶擁有（權限 `1777`）
- Git 出於安全考慮，不信任非當前用戶擁有的目錄
- 這是 Git 的安全機制，防止惡意用戶在共享目錄中注入 git 倉庫

---

## 測試過程

### 測試 1: 直接在 /tmp 初始化 git（失敗）

```bash
cd /tmp
git init
# 輸出：Initialized empty Git repository in /tmp/.git/
git config user.name "Test"
git config user.email "test@test.com"
git add .
# 輸出：fatal: detected dubious ownership in repository at '/tmp'
```

**結果**: ❌ 失敗 - Git 拒絕在 `/tmp` 目錄操作

### 測試 2: 添加 safe.directory（不推薦）

```bash
git config --global --add safe.directory /tmp
cd /tmp
git init
git add .
git commit -m "Test"
```

**結果**: ✅ 成功，但**降低安全性**，不推薦

### 測試 3: 在子目錄初始化（推薦）

```bash
mkdir -p /tmp/patent-report-20260520_123456
cd /tmp/patent-report-20260520_123456
git init
git config user.name "Test"
git config user.email "test@test.com"
git add .
git commit -m "Test"
```

**結果**: ✅ 成功 - 無權限錯誤，Git 正常運作

---

## 解決方案比較

| 方案 | 安全性 | 推薦度 | 說明 |
|------|--------|--------|------|
| 在子目錄初始化 | ⭐⭐⭐⭐⭐ | ✅ 强烈推荐 | 保持 Git 安全機制，無副作用 |
| 添加 safe.directory | ⭐⭐ | ❌ 不推薦 | 降低安全性，僅用於測試環境 |
| 修改 /tmp 權限 | ⭐ | ❌ 禁止 | 破壞系統安全，絕對不要做 |

---

## 實作範例

### 錯誤做法（會觸發權限錯誤）

```bash
#!/bin/bash
OUTPUT_DIR="/tmp"
cd "${OUTPUT_DIR}"
git init  # ❌ 錯誤：在 /tmp 直接初始化
git config user.name "Agent"
git add .
git commit -m "Report"
```

### 正確做法（在子目錄初始化）

```bash
#!/bin/bash
OUTPUT_DIR="/tmp"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
TIMESTAMP_DIR="${OUTPUT_DIR}/patent-report-${TIMESTAMP}"

# 創建時間戳資料夾
mkdir -p "${TIMESTAMP_DIR}"

# 在子目錄內初始化 git
cd "${TIMESTAMP_DIR}"  # ✅ 正確：在子目錄操作
git init
git config user.name "Hermes Agent"
git config user.email "hermes@nousresearch.com"
git add .
git commit -m "Patent Report"
git branch -M main
```

---

## 相關錯誤信息

### 錯誤 1: dubious ownership
```
fatal: detected dubious ownership in repository at '/tmp'
To add an exception for this directory, call:
	git config --global --add safe.directory /tmp
```

### 錯誤 2: not in a git directory
```
fatal: not in a git directory
```

### 錯誤 3: could not read username
```
fatal: could not read Password for 'https://github.com': No such device or address
```

---

## 最佳實踐

1. **永遠不要在 `/tmp`、`/var/tmp` 等共享目錄直接初始化 git**
2. **在子目錄操作**：創建專用子目錄後再執行 git 操作
3. **保持路徑清晰**：使用有意義的子目錄名稱（如時間戳）
4. **避免全局 safe.directory**：除非在隔離的測試環境

---

## 影響範圍

此問題影響以下場景：
- ✅ 在 `/tmp` 生成報告並推送到 GitHub
- ✅ 在共享目錄創建 git 倉庫
- ✅ Docker 容器內的 git 操作
- ✅ 多用戶環境的 git 初始化

---

## 參考資源

- [Git 官方文檔 - safe.directory](https://git-scm.com/docs/git-config#Documentation/git-config.txt-safedirectory)
- [GitHub Security Advisories](https://github.com/blog/security)
- [Linux 文件系統層次結構標準](https://refspecs.linuxfoundation.org/FHS_3.0/fhs/index.html)

---

**測試者**: Hermes Agent  
**測試版本**: v3（時間戳版本）  
**測試狀態**: ✅ 已解決（在子目錄內初始化 git）  
**建議措施**: 更新所有在 `/tmp` 操作 git 的腳本，改為在子目錄執行
