#!/usr/bin/env python3
"""
Hermes Agent Session Restore from Hugging Face Dataset

When HF Space restarts, the local SQLite DB is wiped. This script restores
sessions from the HF Dataset backup by:

Phase 1: Check if local DB needs restoration (compare session counts)
Phase 2: Download state.db from HF and merge into local DB
Phase 3: Download session JSON files for any sessions still missing
Phase 4: Verify restoration completeness

Uses /proc/1/environ to read HF_TOKEN and HF_DATASET_REPO (secret variables).

Usage:
    python3 restore-from-hf.py [--dry-run] [--force] [--verbose]
    python3 restore-from-hf.py --check   # Only check, don't restore

Options:
    --dry-run   Show what would happen without making changes
    --force     Restore even if local DB appears to have sessions
    --verbose   Show detailed progress
    --check     Only check if restoration is needed (exit 0=need restore, 1=no need)
"""

import os
import sys
import json
import sqlite3
import argparse
import time
from datetime import datetime
from pathlib import Path

# ============================================================
# Secret Variable Resolution (same as backup_sessions.py)
# ============================================================

def read_proc1_environ():
    """Read environment variables from PID 1's /proc/1/environ."""
    env_vars = {}
    try:
        with open("/proc/1/environ", "rb") as f:
            env_data = f.read()
        for entry in env_data.split(b"\x00"):
            entry_str = entry.decode("utf-8", errors="replace")
            if "=" in entry_str:
                key, val = entry_str.split("=", 1)
                env_vars[key] = val
    except (FileNotFoundError, PermissionError, OSError):
        pass
    return env_vars


def get_hf_secret(key, default=""):
    """Get a secret variable with multi-source fallback."""
    # Source 1: os.environ
    val = os.environ.get(key, "")
    if val:
        return val
    # Source 2: /proc/1/environ
    proc1_env = read_proc1_environ()
    val = proc1_env.get(key, "")
    if val:
        return val
    # Source 3: .env file
    env_path = Path("/data/.hermes/.env")
    if env_path.exists():
        try:
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        if k == key and v.strip():
                            return v.strip()
        except (IOError, OSError):
            pass
    return default


# Configuration
STATE_DB = Path("/data/.hermes/state.db")
SESSIONS_DIR = Path("/data/.hermes/sessions")
HF_REPO = None  # Will be resolved from secrets
HF_TOKEN = None  # Will be resolved from secrets


def get_hf_credentials():
    """Resolve HF credentials from secret variables."""
    global HF_REPO, HF_TOKEN
    HF_REPO = get_hf_secret("HF_DATASET_REPO")
    HF_TOKEN = get_hf_secret("HF_TOKEN") or get_hf_secret("HUGGING_FACE_HUB_TOKEN")
    return bool(HF_REPO and HF_TOKEN)


def get_local_session_count():
    """Count sessions in local SQLite DB."""
    if not STATE_DB.exists():
        return 0
    try:
        conn = sqlite3.connect(str(STATE_DB), timeout=10)
        count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()
        return count
    except sqlite3.Error:
        return 0


def get_local_session_ids():
    """Get set of session IDs in local DB."""
    if not STATE_DB.exists():
        return set()
    try:
        conn = sqlite3.connect(str(STATE_DB), timeout=10)
        ids = {row[0] for row in conn.execute("SELECT id FROM sessions").fetchall()}
        conn.close()
        return ids
    except sqlite3.Error:
        return set()


def _extract_session_id_from_filename(fname):
    """Extract session ID from HF filename.
    
    Two naming formats exist in HF Dataset:
    - sessions/session_<id>.json  (Phase 2 backup_sessions.py format)
    - sessions/<id>.json          (early data_sync.py UUID format)
    Both are valid; we normalize to the bare session ID.
    """
    name = fname.split("/")[-1].replace(".json", "")
    if name.startswith("session_"):
        return name[8:]  # strip session_ prefix
    return name


def get_hf_session_count(api, verbose=False):
    """Count unique session IDs in HF Dataset.
    
    Handles both naming formats:
    - sessions/session_<id>.json  (Phase 2 backup format)
    - sessions/<id>.json          (early UUID format)
    """
    from huggingface_hub import list_repo_files
    files = list(list_repo_files(repo_id=HF_REPO, repo_type="dataset", token=HF_TOKEN))
    session_files = [f for f in files if f.startswith("sessions/") and f.endswith(".json")]
    # Extract unique session IDs (dedup across both formats)
    session_ids = {_extract_session_id_from_filename(f) for f in session_files}
    if verbose:
        print(f"  HF session files: {len(session_files)}, unique IDs: {len(session_ids)}")
    return len(session_ids)


def get_hf_session_file_list(api, verbose=False):
    """Get dict of session_id → HF filepath from HF Dataset.
    
    Handles both naming formats and deduplicates by session ID.
    If both formats exist for same ID, prefers session_<id>.json (newer format).
    """
    from huggingface_hub import list_repo_files
    files = list(list_repo_files(repo_id=HF_REPO, repo_type="dataset", token=HF_TOKEN))
    session_files = [f for f in files if f.startswith("sessions/") and f.endswith(".json")]
    # Build dict, preferring session_<id>.json over <id>.json
    result = {}
    for f in session_files:
        sid = _extract_session_id_from_filename(f)
        # Prefer session_<id>.json format (contains export metadata)
        if sid not in result or f.split("/")[-1].startswith("session_"):
            result[sid] = f
    if verbose:
        print(f"  HF session files: {len(session_files)}, unique IDs: {len(result)}")
    return result


# ============================================================
# Phase 1: Check if restoration is needed
# ============================================================

def phase1_check(force=False, verbose=False):
    """Determine if restoration from HF is needed."""
    print("=" * 60)
    print("Phase 1: Check if restoration is needed")
    print("=" * 60)

    local_count = get_local_session_count()
    print(f"  Local DB sessions: {local_count}")

    if not get_hf_credentials():
        print("  ERROR: Cannot resolve HF_TOKEN or HF_DATASET_REPO")
        return False, "no_credentials"

    from huggingface_hub import HfApi
    api = HfApi(token=HF_TOKEN)
    hf_count = get_hf_session_count(api, verbose=verbose)
    print(f"  HF Dataset sessions: {hf_count}")

    if force:
        print("  Force mode: will attempt restoration regardless")
        return True, "force_mode"

    if local_count == 0 and hf_count > 0:
        print("  RESTORATION NEEDED: Local DB is empty but HF has data!")
        return True, "db_empty"

    if local_count < hf_count * 0.5:
        print(f"  RESTORATION NEEDED: Local has only {local_count} vs HF's {hf_count}")
        return True, "significant_gap"

    if local_count < hf_count:
        gap = hf_count - local_count
        print(f"  PARTIAL RESTORE: {gap} sessions missing from local DB")
        return True, f"partial_gap_{gap}"

    print("  No restoration needed. Local DB appears complete.")
    return False, "up_to_date"


# ============================================================
# Phase 2: Restore state.db from HF (bulk restore)
# ============================================================

def phase2_restore_state_db(dry_run=False, verbose=False):
    """Download and merge state.db from HF Dataset.
    
    Strategy: Download the remote state.db, then merge sessions that
    are missing from the local DB. We don't replace the local DB 
    entirely because it may have newer sessions created after restart.
    """
    print("\n" + "=" * 60)
    print("Phase 2: Restore state.db from HF Dataset")
    print("=" * 60)

    from huggingface_hub import hf_hub_download

    # Download remote state.db to temp location
    print("  Downloading remote state.db...")
    try:
        remote_db_path = hf_hub_download(
            repo_id=HF_REPO,
            filename="state/state.db",
            repo_type="dataset",
            token=HF_TOKEN
        )
        if verbose:
            remote_size = os.path.getsize(remote_db_path)
            print(f"  Downloaded: {remote_db_path} ({remote_size / 1024 / 1024:.1f} MB)")
    except Exception as e:
        print(f"  ERROR: Failed to download state.db: {e}")
        return {"restored": 0, "errors": 1, "reason": str(e)}

    # Check remote DB contents
    try:
        remote_conn = sqlite3.connect(remote_db_path, timeout=10)
        remote_count = remote_conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        remote_msg_count = remote_conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        print(f"  Remote DB: {remote_count} sessions, {remote_msg_count} messages")
    except Exception as e:
        print(f"  ERROR: Cannot read remote DB: {e}")
        remote_conn.close()
        return {"restored": 0, "errors": 1, "reason": str(e)}

    if dry_run:
        print("  [DRY RUN] Would merge remote sessions into local DB")
        remote_conn.close()
        return {"restored": remote_count, "errors": 0, "dry_run": True}

    # Get local session IDs
    local_ids = get_local_session_ids()
    print(f"  Local DB has {len(local_ids)} sessions")

    # Find missing sessions from remote
    remote_sessions = remote_conn.execute("""
        SELECT id, source, user_id, model, model_config, system_prompt,
               parent_session_id, started_at, ended_at, end_reason,
               message_count, tool_call_count,
               input_tokens, output_tokens,
               cache_read_tokens, cache_write_tokens, reasoning_tokens,
               billing_provider, estimated_cost_usd, actual_cost_usd, cost_status,
               title
        FROM sessions
    """).fetchall()

    remote_ids = {row[0] for row in remote_sessions}
    missing_ids = remote_ids - local_ids
    print(f"  Missing sessions (in remote but not local): {len(missing_ids)}")

    if not missing_ids:
        print("  No missing sessions to restore from state.db")
        remote_conn.close()
        return {"restored": 0, "errors": 0, "reason": "none_missing"}

    # Ensure local DB exists with proper schema
    STATE_DB.parent.mkdir(parents=True, exist_ok=True)
    local_conn = sqlite3.connect(str(STATE_DB), timeout=30)
    local_cur = local_conn.cursor()

    restored = 0
    errors = 0

    for row in remote_sessions:
        session_id = row[0]
        if session_id in local_ids:
            continue  # Already exists locally

        try:
            # Insert session
            local_cur.execute("""
                INSERT OR IGNORE INTO sessions
                (id, source, user_id, model, model_config, system_prompt,
                 parent_session_id, started_at, ended_at, end_reason,
                 message_count, tool_call_count,
                 input_tokens, output_tokens,
                 cache_read_tokens, cache_write_tokens, reasoning_tokens,
                 billing_provider, estimated_cost_usd, actual_cost_usd, cost_status,
                 title)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, row)

            # Also restore messages for this session
            remote_msgs = remote_conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp",
                (session_id,)
            ).fetchall()

            # Get column names for messages table
            msg_cols = [desc[0] for desc in remote_conn.execute(
                "SELECT * FROM messages WHERE session_id = ? LIMIT 0", (session_id,)
            ).description]

            for msg_row in remote_msgs:
                # Build INSERT with matching columns
                placeholders = ", ".join(["?"] * len(msg_row))
                col_names = ", ".join(msg_cols)
                try:
                    local_cur.execute(
                        f"INSERT OR IGNORE INTO messages ({col_names}) VALUES ({placeholders})",
                        msg_row
                    )
                except sqlite3.OperationalError as e:
                    # Column mismatch between remote and local schema
                    # Try inserting only common columns
                    if verbose:
                        print(f"    Column mismatch for message, skipping: {e}")
                    continue

            restored += 1
            if verbose and restored % 50 == 0:
                print(f"    Progress: {restored}/{len(missing_ids)}")

        except Exception as e:
            errors += 1
            if verbose:
                print(f"    Error restoring {session_id}: {e}")

    local_conn.commit()
    local_conn.close()
    remote_conn.close()

    print(f"  Restored {restored} sessions from remote state.db ({errors} errors)")
    return {"restored": restored, "errors": errors}


# ============================================================
# Phase 3: Restore from session JSON files (supplementary)
# ============================================================

def phase3_restore_from_json(dry_run=False, verbose=False):
    """Download session JSON files from HF and import into local DB.
    
    This is a supplementary restore for sessions that exist in HF
    JSON files but were not in the remote state.db.
    """
    print("\n" + "=" * 60)
    print("Phase 3: Restore from session JSON files (supplementary)")
    print("=" * 60)

    from huggingface_hub import hf_hub_download

    local_ids = get_local_session_ids()
    # get_hf_session_file_list now returns dict: {session_id: hf_filepath}
    hf_session_ids = get_hf_session_file_list(None, verbose=verbose)

    if not hf_session_ids:
        print(" No session files found in HF Dataset")
        return {"restored": 0, "errors": 0}

    missing_ids = set(hf_session_ids.keys()) - local_ids
    print(f" Local DB sessions: {len(local_ids)}")
    print(f" HF unique sessions: {len(hf_session_ids)}")
    print(f"  Missing (need to restore from JSON): {len(missing_ids)}")

    if not missing_ids:
        print("  All HF sessions already in local DB")
        return {"restored": 0, "errors": 0}

    if dry_run:
        print(f"  [DRY RUN] Would download and import {len(missing_ids)} sessions")
        return {"restored": len(missing_ids), "errors": 0, "dry_run": True}

    # Import backup_sessions.py's import_session_to_db function
    sys.path.insert(0, '/data/.hermes/skills/devops/robust-db-persistence/scripts')
    from backup_sessions import import_session_to_db, phase1_json_to_db

    # Download missing sessions and import them
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(STATE_DB), timeout=30)
    restored = 0
    errors = 0

    for sid in sorted(missing_ids):
        hf_path = hf_session_ids[sid]
        try:
            # Download to sessions dir
            local_path = hf_hub_download(
                repo_id=HF_REPO,
                filename=hf_path,
                repo_type="dataset",
                token=HF_TOKEN
            )

            # Read and import
            with open(local_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Import using the same logic as backup_sessions.py
            if import_session_to_db(db, sid, local_path, dry_run=False):
                restored += 1
                if verbose and restored % 10 == 0:
                    print(f"    Progress: {restored}/{len(missing_ids)}")
            else:
                errors += 1

        except Exception as e:
            errors += 1
            if verbose:
                print(f"    Error restoring {sid} from JSON: {e}")

    db.commit()
    db.close()

    print(f"  Restored {restored} sessions from JSON ({errors} errors)")
    return {"restored": restored, "errors": errors}


# ============================================================
# Phase 4: Verify restoration
# ============================================================

def phase4_verify(verbose=False):
    """Verify restoration completeness."""
    print("\n" + "=" * 60)
    print("Phase 4: Verify restoration")
    print("=" * 60)

    local_count = get_local_session_count()
    local_ids = get_local_session_ids()

    # Count messages
    if STATE_DB.exists():
        conn = sqlite3.connect(str(STATE_DB), timeout=10)
        msg_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        conn.close()
    else:
        msg_count = 0

    hf_count = get_hf_session_count(None, verbose=verbose)

    print(f"  Local DB: {local_count} sessions, {msg_count} messages")
    print(f"  HF Dataset: {hf_count} session files")

    if local_count >= hf_count:
        print("  VERIFICATION PASSED: Local DB has all or more sessions than HF")
        return True
    else:
        gap = hf_count - local_count
        print(f"  VERIFICATION WARNING: {gap} sessions still missing")
        return False


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Hermes Agent Session Restore from Hugging Face Dataset"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without making changes")
    parser.add_argument("--force", action="store_true",
                        help="Restore even if local DB appears complete")
    parser.add_argument("--verbose", action="store_true",
                        help="Show detailed progress")
    parser.add_argument("--check", action="store_true",
                        help="Only check if restoration is needed")
    args = parser.parse_args()

    start_time = time.time()
    print(f"Session Restore from HF Dataset - {datetime.now().isoformat()}")
    print(f"Options: dry_run={args.dry_run}, force={args.force}, verbose={args.verbose}")

    # Resolve credentials
    if not get_hf_credentials():
        print("\nERROR: Cannot resolve HF_TOKEN or HF_DATASET_REPO!")
        print("Tried: os.environ, /proc/1/environ, /data/.hermes/.env")
        print("HF_TOKEN is a secret variable - it exists but is not in os.environ.")
        print("If /proc/1/environ is not accessible, set HF_TOKEN in /data/.hermes/.env")
        sys.exit(1)

    print(f"HF Dataset: {HF_REPO}")
    print(f"HF Token: {HF_TOKEN[:8]}...{HF_TOKEN[-4:]}")

    # Phase 1: Check
    needs_restore, reason = phase1_check(force=args.force, verbose=args.verbose)

    if args.check:
        sys.exit(0 if needs_restore else 1)

    if not needs_restore:
        print("\nNo restoration needed. Exiting.")
        sys.exit(0)

    print(f"\nRestoration reason: {reason}")

    # Phase 2: Restore from state.db
    p2_stats = phase2_restore_state_db(dry_run=args.dry_run, verbose=args.verbose)

    # Phase 3: Restore from JSON (supplementary)
    p3_stats = phase3_restore_from_json(dry_run=args.dry_run, verbose=args.verbose)

    # Phase 4: Verify
    if not args.dry_run:
        verified = phase4_verify(verbose=args.verbose)
    else:
        print("\n[DRY RUN] Skipping verification")
        verified = None

    # Summary
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("RESTORE SUMMARY")
    print("=" * 60)
    print(f"  Phase 2 (state.db): {p2_stats.get('restored', 0)} restored, {p2_stats.get('errors', 0)} errors")
    print(f"  Phase 3 (JSON): {p3_stats.get('restored', 0)} restored, {p3_stats.get('errors', 0)} errors")
    print(f"  Verification: {'PASSED' if verified else 'INCOMPLETE' if verified is not None else 'SKIPPED'}")
    print(f"  Total time: {elapsed:.2f}s")
    print(f"  Completed at: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
