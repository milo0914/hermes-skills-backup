#!/usr/bin/env python3
"""Heal /data/.hermes/scripts/ after HF Space rebuild.

Copy all cron wrapper scripts from persistent skills/ to ephemeral scripts/.
Run this whenever cron jobs report 'Script not found' errors after a rebuild.

Usage:
  python3 heal-scripts-dir.py          # Copy missing/updated wrappers
  python3 heal-scripts-dir.py --check  # Verify only, don't copy
  python3 heal-scripts-dir.py --force  # Overwrite even if wrappers exist
"""
import argparse
import os
import shutil

SKILLS_DIR = "/data/.hermes/skills"
SCRIPTS_DIR = "/data/.hermes/scripts"

# (skills/ relative source, scripts/ target filename)
ALL_CRON_SCRIPTS = [
    ("devops/github-skills-backup/scripts/cron-skills-backup.sh", "cron-skills-backup.sh"),
    ("devops/github-skills-backup/scripts/github-skills-backup.sh", "github-skills-backup.sh"),
    ("devops/hermes-cli-to-webui-sync/scripts/cron-sync-sessions.py", "cron-sync-sessions.py"),
    ("devops/hermes-cli-to-webui-sync/scripts/sync-sessions-to-webui.py", "sync-sessions-to-webui.py"),
    ("devops/robust-db-persistence/scripts/cron-backup-sessions.py", "backup-sessions.py"),
    ("devops/robust-db-persistence/scripts/cron-restore-from-hf.py", "restore-from-hf.py"),
    ("research/twstock-alpha-gpt/scripts/kaggle-gpu-quota-monitor.py", "kaggle-gpu-quota-monitor.py"),
]

def main():
    parser = argparse.ArgumentParser(description="Heal scripts/ after HF Space rebuild")
    parser.add_argument("--check", action="store_true", help="Verify only, don't copy")
    parser.add_argument("--force", action="store_true", help="Overwrite even if wrappers exist")
    args = parser.parse_args()

    os.makedirs(SCRIPTS_DIR, exist_ok=True)

    missing = []
    ok = []
    no_source = []

    for rel_src, target in ALL_CRON_SCRIPTS:
        src = os.path.join(SKILLS_DIR, rel_src)
        dst = os.path.join(SCRIPTS_DIR, target)

        if not os.path.exists(src):
            no_source.append(rel_src)
            continue

        if os.path.exists(dst) and not args.force:
            ok.append(f"{target} (exists)")
            continue

        if args.check:
            missing.append(f"{target} (source: {rel_src})")
        else:
            shutil.copy2(src, dst)
            os.chmod(dst, 0o755)
            size = os.path.getsize(dst)
            ok.append(f"COPIED: {target} ({size} bytes)")

    print(f"scripts/ directory: {SCRIPTS_DIR}")
    print(f"Total wrappers defined: {len(ALL_CRON_SCRIPTS)}")

    if no_source:
        print(f"\nMISSING source files ({len(no_source)}):")
        for s in no_source:
            print(f"  - {s}")

    if args.check and missing:
        print(f"\nWrappers needing copy ({len(missing)}):")
        for m in missing:
            print(f"  - {m}")

    if ok:
        print(f"\nOK/Copied ({len(ok)}):")
        for o in ok:
            print(f"  {o}")

    # Return code: 0 if all present, 1 if any missing
    if args.check and missing:
        return 1
    return 0

if __name__ == "__main__":
    exit(main())
