#!/usr/bin/env python3
"""
Self-healing cron wrapper for session backup.
Problem: /data/.hermes/scripts/ is ephemeral (wiped on HF Space rebuild).
 The real script lives in skills/ which also needs restoration after rebuild.
Solution: This wrapper auto-heals before running the actual backup.

v5 FIX: heal_skills_from_github() now uses SKILL-LEVEL granularity
 (not just category-level). Previously, if devops/ already existed locally,
 it would skip copying even if individual skills within it were missing.
 Now it copies missing skills even if the category directory exists.

Healing logic:
1. Check if the actual script exists in skills/
2. If not, clone from GitHub and restore skills (with skill-level granularity)
3. Then run the actual backup script
"""

import os
import sys
import subprocess
import tempfile
import shutil

SKILLS_DIR = "/data/.hermes/skills"
SCRIPTS_DIR = "/data/.hermes/scripts"
REAL_SCRIPT = os.path.join(SKILLS_DIR, "devops/robust-db-persistence/scripts/backup_sessions.py")
GITHUB_USER = os.environ.get("GITHUB_USER", "milo0914")
REPO_NAME = os.environ.get("REPO_NAME", "hermes-skills-backup")


def get_github_token():
    """Resolve GITHUB_TOKEN from env or /proc/1/environ (HF Spaces Secret).
 NEVER say GITHUB_TOKEN is not set - it's a secret variable."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        return token
    try:
        with open("/proc/1/environ", "rb") as f:
            for entry in f.read().split(b"\x00"):
                s = entry.decode("utf-8", errors="replace")
                if s.startswith("GITHUB_TOKEN="):
                    return s.split("=", 1)[1]
    except Exception:
        pass
    return ""


def heal_skills_from_github(token):
    """Clone skills from GitHub and restore missing ones.

    v5: Uses SKILL-LEVEL granularity — copies individual missing skills
    even if their parent category directory already exists locally.
    This fixes the bug where category-level 'if not os.path.exists(dst)'
    would skip restoring a missing skill because its category dir existed.
    """
    clone_dir = tempfile.mkdtemp(prefix="hermes-skills-restore-")
    url = f"https://{token}@github.com/{GITHUB_USER}/{REPO_NAME}.git"
    result = subprocess.run(
        ["git", "clone", "--depth", "1", url, clone_dir],
        capture_output=True, timeout=120
    )
    if result.returncode != 0:
        print(f"SELF-HEAL ERROR: clone failed: {result.stderr.decode()}")
        return False

    restored_count = 0
    # Iterate over category dirs in the clone (e.g. devops/, research/)
    for category in os.listdir(clone_dir):
        cat_src = os.path.join(clone_dir, category)
        cat_dst = os.path.join(SKILLS_DIR, category)
        if not os.path.isdir(cat_src) or category in (".git", "README.md"):
            continue

        if not os.path.exists(cat_dst):
            # Entire category missing — copy the whole thing
            shutil.copytree(cat_src, cat_dst)
            restored_count += len([d for d in os.listdir(cat_src) if os.path.isdir(os.path.join(cat_src, d))])
            print(f"SELF-HEAL: Restored category {category}/ ({restored_count} skills)")
        else:
            # Category exists — check individual skills within it
            for skill_name in os.listdir(cat_src):
                skill_src = os.path.join(cat_src, skill_name)
                skill_dst = os.path.join(cat_dst, skill_name)
                if os.path.isdir(skill_src) and not os.path.exists(skill_dst):
                    shutil.copytree(skill_src, skill_dst)
                    restored_count += 1
                    print(f"SELF-HEAL: Restored skill {category}/{skill_name}")

    # Also handle flat skills (no category subdirectory)
    for entry in os.listdir(clone_dir):
        src = os.path.join(clone_dir, entry)
        dst = os.path.join(SKILLS_DIR, entry)
        if not os.path.isdir(src) or entry in (".git", "README.md"):
            continue
        # Already handled above as categories
        pass

    subprocess.run(["rm", "-rf", clone_dir], capture_output=True)
    print(f"SELF-HEAL: Restored {restored_count} skill(s) from GitHub")
    return True


def heal_scripts_dir():
    """Restore scripts/ from skills/ by copying all cron wrappers.

    v5 FIX: The mapping now correctly uses cron wrapper scripts
    (cron-backup-sessions.py, cron-restore-from-hf.py) as the source
    for the scripts/ copies, NOT the real scripts. The cron scheduler
    expects scripts/backup-sessions.py to be a self-healing wrapper,
    not the raw backup_sessions.py.
    """
    os.makedirs(SCRIPTS_DIR, exist_ok=True)
    wrappers = [
        ("devops/github-skills-backup/scripts/cron-skills-backup.sh", "cron-skills-backup.sh"),
        ("devops/github-skills-backup/scripts/github-skills-backup.sh", "github-skills-backup.sh"),
        ("devops/hermes-cli-to-webui-sync/scripts/cron-sync-sessions.py", "cron-sync-sessions.py"),
        ("devops/hermes-cli-to-webui-sync/scripts/sync-sessions-to-webui.py", "sync-sessions-to-webui.py"),
        ("devops/robust-db-persistence/scripts/cron-backup-sessions.py", "backup-sessions.py"),
        ("devops/robust-db-persistence/scripts/cron-restore-from-hf.py", "restore-from-hf.py"),
        ("research/twstock-alpha-gpt/scripts/kaggle-gpu-quota-monitor.py", "kaggle-gpu-quota-monitor.py"),
    ]
    for skill_rel, script_name in wrappers:
        src = os.path.join(SKILLS_DIR, skill_rel)
        dst = os.path.join(SCRIPTS_DIR, script_name)
        if os.path.isfile(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
            os.chmod(dst, 0o755)
            print(f"SELF-HEAL: Restored {dst} from skills/")


def main():
    # --- Self-heal: restore skills from GitHub if script missing ---
    if not os.path.isfile(REAL_SCRIPT):
        print(f"SELF-HEAL: Script not found at {REAL_SCRIPT}")
        token = get_github_token()
        if token:
            print("SELF-HEAL: Restoring skills from GitHub...")
            if heal_skills_from_github(token):
                print("SELF-HEAL: Skills restored from GitHub")
                heal_scripts_dir()
            else:
                print("ERROR: SELF-HEAL failed")
                sys.exit(1)
        else:
            print("ERROR: Cannot self-heal - GITHUB_TOKEN not found")
            sys.exit(1)
    else:
        # Script exists, but also heal scripts/ dir if needed
        heal_scripts_dir()

    # --- Run the actual backup ---
    if os.path.isfile(REAL_SCRIPT):
        result = subprocess.run(
            [sys.executable, REAL_SCRIPT] + sys.argv[1:],
            timeout=300
        )
        sys.exit(result.returncode)
    else:
        print(f"ERROR: Script still not found at {REAL_SCRIPT} after self-heal")
        sys.exit(1)


if __name__ == "__main__":
    main()
