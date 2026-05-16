# GitHub Skills Backup 使用指南

## 快速開始

### 首次使用（設置 GITHUB_TOKEN）

1. **獲取 GitHub Token**：
 - 前往 https://github.com/settings/tokens
 - 點擊 "Generate new token (classic)"
 - 勾選 `repo` 權限
 - 複製 Token（格式：`ghp_xxxxxxxxxxxx`）

2. **在 HuggingFace Spaces 添加 Secret**：
 - 前往您的 Space 頁面
 - 點擊 **Settings** → **Variables and Secrets**
 - 添加 Secret：
 - Name: `GITHUB_TOKEN`
 - Value: `ghp_xxxxxxxxxxxx`

3. **執行備份**：
```bash
bash /tmp/github-skills-backup.sh
```

### 日常備份

設置好 GITHUB_TOKEN 後，只需執行：

```bash
bash /tmp/github-skills-backup.sh
```

## 使用技能

加載技能後，可以：

```
使用 github-skills-backup 來備份所有技能到 GitHub
```

## 輸出示例

```
🚀 Hermes Skills Backup to GitHub
======================================
用戶：milo0914
倉庫：hermes-skills-backup

📦 準備備份...
  ✓ 1password
  ✓ arxiv
  ✓ superpowers-zh
  ...
  總計：26 個技能

📝 創建 README...
📦 初始化 Git...
📝 創建 GitHub 倉庫...
  ✓ 倉庫已存在
📤 推送到 GitHub...
  ...

======================================
✅ 備份完成！
📦 倉庫地址：https://github.com/milo0914/hermes-skills-backup
======================================
```

## 從備份還原

```bash
# 克隆備份
git clone https://github.com/milo0914/hermes-skills-backup.git
cd hermes-skills-backup

# 複製到 Hermes Agent
cp -r * /data/.hermes/skills/
```

## 故障排除

### GITHUB_TOKEN 未設置
```bash
# 檢查環境變數
echo $GITHUB_TOKEN

# 如果為空，需要在 HuggingFace Spaces Settings 中添加
```

### 推送失敗
```bash
# 檢查 Token 有效性
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user

# 刪除重試
curl -X DELETE "https://api.github.com/repos/$GITHUB_USER/$REPO_NAME" \
 -H "Authorization: token $GITHUB_TOKEN"
```

## 自動化（可選）

添加到 crontab 每週備份：
```bash
0 2 * * 1 bash /tmp/github-skills-backup.sh
```
