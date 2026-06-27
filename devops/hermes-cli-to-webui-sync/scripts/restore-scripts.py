#!/usr/bin/env python3
"""
Restore wrapper scripts from skills/ to scripts/ after container rebuild.

This script lives in the skills/ directory (persistent storage) and is
called directly by a cron job to repopulate scripts/ after HF Spaces
container rebuilds wipe the ephemeral scripts/ directory.

Usage: python3 /data/.hermes/skills/devops/hermes-cli-to-webui-sync/scripts/restore-scripts.py [--quiet]
"""
import os
import sys

SKILLS_DIR = "/data/.hermes/skills"
SCRIPTS_DIR = "/data/.hermes/scripts"

# Mapping: script_name -> source_in_skills
SCRIPT_SOURCES = {
 "sync-sessions-to-webui.py": "devops/hermes-cli-to-webui-sync/scripts/sync-sessions-to-webui.py",
 "github-skills-backup.sh": "devops/github-skills-backup/scripts/github-skills-backup.sh",
 "backup-sessions.py": "devops/robust-db-persistence/scripts/backup_sessions.py",
 "restore-from-hf.py": "devops/robust-db-persistence/scripts/restore-from-hf.py",
}

# Wrapper template for Python scripts
PYTHON_WRAPPER = '''#!/usr/bin/env python3
"""Wrapper: delegates to the real script in skills/ (persistent storage)."""
import subprocess, sys, os
REAL = '{real_path}'
if not os.path.exists(REAL):
    print(f'ERROR: Real script not found at {{REAL}}')
    sys.exit(1)
sys.exit(subprocess.call([sys.executable, REAL] + sys.argv[1:]))
'''

# Wrapper template for shell scripts
BASH_WRAPPER = '''#!/bin/bash
# Wrapper: delegates to the real script in skills/ (persistent storage)
REAL='{real_path}'
if [ ! -f "$REAL" ]; then
    echo "ERROR: Real script not found at $REAL"
    exit 1
fi
exec bash "$REAL" "$@"
'''


def restore_scripts(quiet=False):
    os.makedirs(SCRIPTS_DIR, exist_ok=True)
    restored = []
    already_ok = []

    for script_name, skill_path in SCRIPT_SOURCES.items():
        real_path = os.path.join(SKILLS_DIR, skill_path)
        dst = os.path.join(SCRIPTS_DIR, script_name)

        if not os.path.exists(real_path):
            if not quiet:
                print(f"WARN: Source not found: {real_path}")
            continue

        if os.path.exists(dst):
            with open(dst, 'r') as f:
                content = f.read()
            if real_path in content:
                already_ok.append(script_name)
                continue

        is_python = script_name.endswith('.py')
        template = PYTHON_WRAPPER if is_python else BASH_WRAPPER
        wrapper_content = template.format(real_path=real_path)

        with open(dst, 'w') as f:
            f.write(wrapper_content)
        os.chmod(dst, 0o755)
        restored.append(script_name)

    if not quiet:
        if restored:
            print(f"Restored {len(restored)} scripts: {', '.join(restored)}")
        if already_ok:
            print(f"Already OK: {', '.join(already_ok)}")
        if not restored and not already_ok:
            print("No scripts to restore.")

    return len(restored) > 0


if __name__ == "__main__":
    quiet = "--quiet" in sys.argv
    had_changes = restore_scripts(quiet=quiet)
    if not had_changes:
        sys.exit(0)
