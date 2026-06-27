#!/bin/bash
# Self-healing cron wrapper for skills-backup
# Problem: /data/.hermes/scripts/ is ephemeral (wiped on HF Space rebuild)
# Cron script field only accepts relative paths under scripts/
# Solution: This wrapper auto-heals before running the actual backup
#
# v5 FIX: heal_skills now uses SKILL-LEVEL granularity (not just category-level).
# Previously, if devops/ already existed locally, it would skip copying
# even if individual skills within it were missing.
# Also: heal_scripts_dir uses cp (not symlinks) since cron rejects symlink targets.
#
# Healing logic:
# 1. Check if the actual backup script exists in skills/
# 2. If not, clone from GitHub and restore (with skill-level granularity)
# 3. Ensure scripts/ copies are in place
# 4. Run the actual backup (passing through all arguments)

set -e

SKILLS_DIR="/data/.hermes/skills"
SCRIPTS_DIR="/data/.hermes/scripts"
BACKUP_SCRIPT="${SKILLS_DIR}/devops/github-skills-backup/scripts/github-skills-backup.sh"
GITHUB_USER="${GITHUB_USER:-milo0914}"
REPO_NAME="${REPO_NAME:-hermes-skills-backup}"

# --- GITHUB_TOKEN resolution ---
# HF Spaces Secrets are NOT in shell env; they live in /proc/1/environ
# NEVER say "GITHUB_TOKEN not set" — it exists as a secret variable.
if [ -z "$GITHUB_TOKEN" ]; then
 GITHUB_TOKEN=$(cat /proc/1/environ 2>/dev/null | tr '\0' '\n' | grep '^GITHUB_TOKEN=' | cut -d= -f2-)
fi
if [ -z "$GITHUB_TOKEN" ]; then
 echo "ERROR: GITHUB_TOKEN not found (checked shell env and /proc/1/environ)"
 exit 1
fi
export GITHUB_TOKEN

# --- Self-heal: restore skills from GitHub if missing ---
if [ ! -f "$BACKUP_SCRIPT" ]; then
 echo "SELF-HEAL: Backup script not found at $BACKUP_SCRIPT"
 echo "SELF-HEAL: Restoring skills from GitHub..."

 CLONE_TMP="/tmp/hermes-skills-restore-$$"
 git clone --depth 1 "https://${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${REPO_NAME}.git" "$CLONE_TMP" 2>/dev/null

 if [ -d "$CLONE_TMP" ]; then
 # v5: Skill-level granularity — iterate over categories, then skills
 RESTORED=0
 for category_dir in "$CLONE_TMP"/*/; do
 [ -d "$category_dir" ] || continue
 category=$(basename "$category_dir")
 [ "$category" = "README.md" ] && continue
 [ "$category" = ".git" ] && continue

 local_cat="${SKILLS_DIR}/${category}"
 if [ ! -d "$local_cat" ]; then
 # Entire category missing — copy the whole thing
 cp -rn "$category_dir" "${SKILLS_DIR}/"
 skill_count=$(find "$category_dir" -mindepth 1 -maxdepth 1 -type d | wc -l)
 RESTORED=$((RESTORED + skill_count))
 echo "SELF-HEAL: Restored category ${category}/"
 else
 # Category exists — check individual skills within it
 for skill_dir in "$category_dir"*/; do
 [ -d "$skill_dir" ] || continue
 skill_name=$(basename "$skill_dir")
 local_skill="${local_cat}/${skill_name}"
 if [ ! -d "$local_skill" ]; then
 cp -rn "$skill_dir" "$local_skill/"
 RESTORED=$((RESTORED + 1))
 echo "SELF-HEAL: Restored skill ${category}/${skill_name}"
 fi
 done
 fi
 done

 echo "SELF-HEAL: Restored ${RESTORED} skill(s) from GitHub"
 rm -rf "$CLONE_TMP"
 else
 echo "ERROR: SELF-HEAL failed - could not clone from GitHub"
 exit 1
 fi
fi

# --- Self-heal: ensure scripts/ copies are in place ---
# v5 FIX: Use cp (not symlinks) since cron rejects symlink path targets.
mkdir -p "$SCRIPTS_DIR"

# Define all cron script mappings (source in skills/ -> name in scripts/)
declare -A CRON_SCRIPT_MAP
CRON_SCRIPT_MAP["cron-skills-backup.sh"]="${SKILLS_DIR}/devops/github-skills-backup/scripts/cron-skills-backup.sh"
CRON_SCRIPT_MAP["github-skills-backup.sh"]="${SKILLS_DIR}/devops/github-skills-backup/scripts/github-skills-backup.sh"
CRON_SCRIPT_MAP["cron-sync-sessions.py"]="${SKILLS_DIR}/devops/hermes-cli-to-webui-sync/scripts/cron-sync-sessions.py"
CRON_SCRIPT_MAP["sync-sessions-to-webui.py"]="${SKILLS_DIR}/devops/hermes-cli-to-webui-sync/scripts/sync-sessions-to-webui.py"
CRON_SCRIPT_MAP["backup-sessions.py"]="${SKILLS_DIR}/devops/robust-db-persistence/scripts/cron-backup-sessions.py"
CRON_SCRIPT_MAP["restore-from-hf.py"]="${SKILLS_DIR}/devops/robust-db-persistence/scripts/cron-restore-from-hf.py"
CRON_SCRIPT_MAP["kaggle-gpu-quota-monitor.py"]="${SKILLS_DIR}/research/twstock-alpha-gpt/scripts/kaggle-gpu-quota-monitor.py"

for script_name in "${!CRON_SCRIPT_MAP[@]}"; do
 src="${CRON_SCRIPT_MAP[$script_name]}"
 dst="${SCRIPTS_DIR}/${script_name}"
 if [ -f "$src" ] && [ ! -f "$dst" ]; then
 cp "$src" "$dst"
 chmod 755 "$dst"
 echo "SELF-HEAL: Restored $dst from skills/"
 fi
done

# --- Run the actual backup (pass all arguments through) ---
bash "$BACKUP_SCRIPT" "$@"
