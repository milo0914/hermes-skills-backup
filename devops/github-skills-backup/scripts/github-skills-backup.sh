#!/bin/bash
set -e

GITHUB_USER="${GITHUB_USER:-"milo0914"}"
REPO_NAME="${REPO_NAME:-"hermes-skills-backup"}"
BACKUP_DIR="/tmp/hermes-skills-backup"
SKILLS_DIR="/data/.hermes/skills"

# GITHUB_TOKEN may be an HF Spaces secret — not in shell env but in /proc/1/environ
if [ -z "$GITHUB_TOKEN" ]; then
  GITHUB_TOKEN=$(cat /proc/1/environ 2>/dev/null | tr '\0' '\n' | grep '^GITHUB_TOKEN=' | cut -d= -f2-)
fi
if [ -z "$GITHUB_TOKEN" ]; then
 echo "Error: GITHUB_TOKEN env var not set (checked shell env and /proc/1/environ)"
 exit 1
fi

MODE="backup"
RESTORE_TARGET=""

while [[ $# -gt 0 ]]; do
 case $1 in
 --restore)
 MODE="restore"
 RESTORE_TARGET="$2"
 shift 2
 ;;
 --list)
 MODE="list"
 shift
 ;;
 --check)
 MODE="check"
 shift
 ;;
 -h|--help|help)
 echo "Usage:"
 echo "  bash $0           # Backup all skills"
 echo "  bash $0 --list    # List all restorable skills"
 echo "  bash $0 --check   # Check GitHub repo connectivity"
 echo "  bash $0 --restore <category/skill-name>"
 echo ""
 echo "Examples:"
 echo "  bash $0 --list"
 echo "  bash $0 --restore research/patent-playwright-scraper"
 echo "  bash $0 --restore superpowers-zh/grpo-planning"
 exit 0
 ;;
 *)
 echo "Error: Unknown argument $1"
 exit 1
 ;;
 esac
done

if [ "$MODE" = "list" ]; then
 echo "Listing restorable skills from GitHub backup..."
 CLONE_TMP="/tmp/hermes-skills-backup-$$"
 git clone --depth 1 "https://${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${REPO_NAME}.git" "$CLONE_TMP" 2>/dev/null || true
 if [ ! -d "$CLONE_TMP" ]; then
 echo "Error: Failed to clone backup repo"
 exit 1
 fi

 echo ""
 echo "Available skills:"
 echo "================="
 for category_dir in "$CLONE_TMP"/*/; do
 if [ -d "$category_dir" ]; then
 category=$(basename "$category_dir")
 [ "$category" = ".git" ] && continue
 echo ""
 echo "[$category]"
 for skill_dir in "$category_dir"*/; do
 if [ -d "$skill_dir" ]; then
 skill=$(basename "$skill_dir")
 existing=""
 if [ -d "$SKILLS_DIR/$category/$skill" ]; then
 existing=" (overwrites existing)"
 fi
 echo "  - $category/$skill$existing"
 fi
 done
 fi
 done

 echo ""
 echo "To restore: bash $0 --restore <category/skill-name>"
 rm -rf "$CLONE_TMP"
 exit 0
fi

if [ "$MODE" = "check" ]; then
 echo "Checking GitHub connectivity..."
 HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://api.github.com/repos/${GITHUB_USER}/${REPO_NAME}" \
 -H "Authorization: Bearer ${GITHUB_TOKEN}")

 if [ "$HTTP_STATUS" = "200" ]; then
 echo "OK: https://github.com/${GITHUB_USER}/${REPO_NAME}"
 else
 echo "Error: HTTP ${HTTP_STATUS}"
 fi
 exit 0
fi

if [ "$MODE" = "restore" ]; then
 if [ -z "$RESTORE_TARGET" ]; then
 echo "Error: Please specify skill path"
 echo "Usage: bash $0 --restore <category/skill-name>"
 exit 1
 fi

 RESTORE_CATEGORY=$(echo "$RESTORE_TARGET" | cut -d'/' -f1)
 RESTORE_SKILL=$(echo "$RESTORE_TARGET" | cut -d'/' -f2)

 if [ -z "$RESTORE_CATEGORY" ] || [ -z "$RESTORE_SKILL" ]; then
 echo "Error: Invalid format. Use <category/skill-name>"
 exit 1
 fi

 echo "Restoring single skill from GitHub backup..."
 echo "======================================"
 echo "Target: $RESTORE_TARGET"
 echo ""

 CLONE_TMP="/tmp/hermes-skills-backup-restore-$$"
 git clone --depth 1 "https://${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${REPO_NAME}.git" "$CLONE_TMP" 2>/dev/null || true

 if [ ! -d "$CLONE_TMP" ]; then
 echo "Error: Failed to clone backup repo"
 exit 1
 fi

 SOURCE_SKILL_DIR="$CLONE_TMP/$RESTORE_TARGET"
 if [ ! -d "$SOURCE_SKILL_DIR" ]; then
 echo "Error: Skill $RESTORE_TARGET not found in backup"
 rm -rf "$CLONE_TMP"
 exit 1
 fi

 DEST_DIR="$SKILLS_DIR/$RESTORE_TARGET"
 if [ -d "$DEST_DIR" ]; then
 echo "Backing up existing skill..."
 mv "$DEST_DIR" "${DEST_DIR}.bak.$(date +%s)"
 fi

 mkdir -p "$(dirname "$DEST_DIR")"
 cp -r "$SOURCE_SKILL_DIR" "$DEST_DIR"

 echo ""
 echo "Restored: $RESTORE_TARGET"
 echo "Location: $DEST_DIR"
 FILE_COUNT=$(find "$DEST_DIR" -type f | wc -l)
 echo "Files: $FILE_COUNT"

 rm -rf "$CLONE_TMP"
 exit 0
fi

echo "Backing up all skills to GitHub..."
echo "======================================"
echo "User: $GITHUB_USER"
echo "Repo: $REPO_NAME"
echo ""

rm -rf "$BACKUP_DIR"
mkdir -p "$BACKUP_DIR"

echo "Preparing backup..."
SKILL_COUNT=0
for skill_dir in $SKILLS_DIR/*/; do
 skill_name=$(basename "$skill_dir")
 if [[ ! "$skill_name" =~ ^\. ]] && [[ -d "$skill_dir" ]]; then
 cp -r "$skill_dir" "$BACKUP_DIR/"
 echo "  OK $skill_name"
 ((SKILL_COUNT++)) || true
 fi
done

echo "  Total: $SKILL_COUNT skills"
echo ""

echo "Creating README..."
cat > "$BACKUP_DIR/README.md" << EOF
# Hermes Skills Backup

Backup of Hermes Agent skills.

## Included skills ($SKILL_COUNT)

$(ls -1 "$BACKUP_DIR" | grep -v README | sed 's/^/- /')

## Restore

\`\`\`bash
git clone https://github.com/$GITHUB_USER/$REPO_NAME.git
cd $REPO_NAME
cp -r * /data/.hermes/skills/
\`\`\`

## Backup time

$(date -Iseconds)

EOF

echo "Initializing git..."
cd "$BACKUP_DIR"
git init
git config user.name "Hermes Agent"
git config user.email "hermes@nousresearch.com"
git add .
git commit -m "Backup: $SKILL_COUNT skills on $(date +%Y-%m-%d)"

REMOTE_URL="https://${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${REPO_NAME}.git"

echo "Creating GitHub repo..."
CREATE_RESULT=$(curl -s -X POST "https://api.github.com/user/repos" \
 -H "Authorization: token ${GITHUB_TOKEN}" \
 -H "Accept: application/vnd.github.v3+json" \
 -d "{\"name\":\"${REPO_NAME}\",\"private\":false,\"auto_init\":false}")

if echo "$CREATE_RESULT" | grep -q "already exists"; then
 echo "  Repo already exists"
elif echo "$CREATE_RESULT" | grep -q "created_at"; then
 echo "  Repo created"
else
 echo "  Warning: repo creation may have failed"
fi

echo "Pushing to GitHub..."
git remote add origin "$REMOTE_URL" 2>/dev/null || git remote set-url origin "$REMOTE_URL"
git branch -M main
git push -u origin main --force 2>&1 | tail -5

echo ""
echo "======================================"
echo "Backup complete!"
echo "Repo: https://github.com/${GITHUB_USER}/${REPO_NAME}"
echo "======================================"
echo ""
echo "Commands:"
echo "  $0 --list               # List skills"
echo "  $0 --restore <path>     # Restore single skill"
echo "  $0 --check              # Check connectivity"
