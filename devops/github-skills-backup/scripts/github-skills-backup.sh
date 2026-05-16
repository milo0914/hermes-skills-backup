#!/bin/bash
# GitHub Skills Backup - 自動備份腳本
# 使用方式：bash /tmp/github-skills-backup.sh

set -e

GITHUB_USER="${GITHUB_USER:-"milo0914"}"
REPO_NAME="${REPO_NAME:-"hermes-skills-backup"}"
BACKUP_DIR="/tmp/hermes-skills-backup"
SKILLS_DIR="/data/.hermes/skills"

echo "🚀 Hermes Skills Backup to GitHub"
echo "======================================"
echo "用戶：$GITHUB_USER"
echo "倉庫：$REPO_NAME"
echo ""

# 檢查 GITHUB_TOKEN
if [ -z "$GITHUB_TOKEN" ]; then
 echo "❌ 錯誤：GITHUB_TOKEN 環境變變數未設置"
 echo ""
 echo "請在 HuggingFace Spaces Secrets 中添加 GITHUB_TOKEN："
 echo "1. 前往 Space Settings"
 echo "2. Variables and Secrets"
 echo "3. Add Secret: GITHUB_TOKEN = ghp_xxxxxxxxxxxx"
 echo ""
 exit 1
fi

# 清理舊備份
rm -rf "$BACKUP_DIR"
mkdir -p "$BACKUP_DIR"

# 複製所有技能
echo "📦 準備備份..."
SKILL_COUNT=0
for skill_dir in $SKILLS_DIR/*/; do
 skill_name=$(basename "$skill_dir")
 # 排除特殊目錄
 if [[ ! "$skill_name" =~ ^\. ]] && [[ -d "$skill_dir" ]]; then
 cp -r "$skill_dir" "$BACKUP_DIR/"
 echo "  ✓ $skill_name"
 ((SKILL_COUNT++)) || true
 fi
done

echo "  總計：$SKILL_COUNT 個技能"
echo ""

# 創建 README
echo "📝 創建 README..."
cat > "$BACKUP_DIR/README.md" << EOF
# Hermes Skills Backup

自動備份的 Hermes Agent 技能集合。

## 包含技能 ($SKILL_COUNT 個)

$(ls -1 "$BACKUP_DIR" | grep -v README | sed 's/^/- /')

## 還原方式

\`\`\`bash
# 克隆備份
git clone https://github.com/$GITHUB_USER/$REPO_NAME.git
cd $REPO_NAME

# 複製到 Hermes Agent
cp -r * /data/.hermes/skills/
\`\`\`

## 備份時間

$(date -Iseconds)

## 備份說明

- 此備份包含所有已安裝的 Hermes Agent 技能
- 包括 superpowers-zh (20 個中文技能)
- 包括 skill-creator、browser-automation 等工具類技能
- 自動從 GitHub 克隆後可立即使用

EOF

# 初始化 git
echo "📦 初始化 Git..."
cd "$BACKUP_DIR"
git init
git config user.name "Hermes Agent"
git config user.email "hermes@nousresearch.com"
git add .
git commit -m "Backup: Hermes Skills ($SKILL_COUNT skills) $(date +%Y-%m-%d %H:%M)"

# 創建遠程倉庫
REMOTE_URL="https://${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${REPO_NAME}.git"

# 使用 API 創建倉庫
echo "📝 創建 GitHub 倉庫..."
CREATE_RESULT=$(curl -s -X POST "https://api.github.com/user/repos" \
 -H "Authorization: token ${GITHUB_TOKEN}" \
 -H "Accept: application/vnd.github.v3+json" \
 -d "{\"name\":\"${REPO_NAME}\",\"private\":false,\"auto_init\":false}")

if echo "$CREATE_RESULT" | grep -q "already exists"; then
 echo "  ✓ 倉庫已存在"
elif echo "$CREATE_RESULT" | grep -q "created_at"; then
 echo "  ✓ 倉庫已創建"
else
 echo "  ⚠️ 倉庫創建可能出錯"
 echo "  $CREATE_RESULT"
fi

# 推送
echo "📤 推送到 GitHub..."
git remote add origin "$REMOTE_URL" 2>/dev/null || git remote set-url origin "$REMOTE_URL"
git branch -M main
git push -u origin main --force 2>&1 | tail -5

echo ""
echo "======================================"
echo "✅ 備份完成！"
echo "📦 倉庫地址：https://github.com/${GITHUB_USER}/${REPO_NAME}"
echo "======================================"
echo ""
echo "💡 使用方式："
echo "  git clone https://github.com/${GITHUB_USER}/${REPO_NAME}.git"
echo "  cd ${REPO_NAME}"
echo "  cp -r * /data/.hermes/skills/"
echo ""
