#!/usr/bin/env python3
"""Kaggle GPU quota monitor + auto-push kernel v6.0

Checks if GPU quota has reset. If yes, pushes the kernel.
Runs every 4 hours. Self-removes after successful push.
"""
import subprocess, sys, os, json

os.environ['KAGGLE_CONFIG_DIR'] = os.path.expanduser('~/.kaggle')

KERNEL_DIR = '/tmp/kaggle-kernel'
PUSHED_FLAG = '/tmp/kaggle-kernel/.v60_pushed'

# If already pushed, stay silent
if os.path.exists(PUSHED_FLAG):
    sys.exit(0)

# Try pushing the kernel
result = subprocess.run(
    [sys.executable, '-m', 'kaggle', 'kernels', 'push', '-p', KERNEL_DIR],
    capture_output=True, text=True, timeout=120
)

stdout = result.stdout.strip()
stderr = result.stderr.strip()

if result.returncode == 0 and 'error' not in stdout.lower():
    # Success — mark as pushed
    with open(PUSHED_FLAG, 'w') as f:
        f.write(f'Pushed at: {__import__("datetime").datetime.now().isoformat()}\n')
        f.write(f'stdout: {stdout}\n')
    print(f"GPU quota OK! Kernel v6.0 pushed successfully.")
    print(f"Output: {stdout[:300]}")
elif 'quota' in stdout.lower() or 'quota' in stderr.lower():
    # Quota still exhausted — stay silent (no output = no delivery)
    sys.exit(0)
else:
    # Other error — report it
    print(f"Kernel push failed (non-quota error):")
    print(f"  stdout: {stdout[:300]}")
    print(f"  stderr: {stderr[:300]}")
    sys.exit(1)
