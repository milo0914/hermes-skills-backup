#!/usr/bin/env python3
"""
Hermes Agent Unified Session Sync Script

Three-phase unified sync:
  Phase 1: JSON → DB  (import orphan sessions from JSON files into SQLite)
  Phase 2: DB → JSON  (incremental backup from SQLite to JSON files)
  Phase 3: DB → HF    (optional: upload to Hugging Face Dataset)

Uses file locking to prevent concurrent execution.

Usage:
  python3 backup_sessions.py [--skip-hf] [--force-hf] [--dry-run] [--timeout SECONDS]

Options:
  --skip-hf     Skip Phase 3 (HF upload), even if HF_TOKEN is set
  --force-hf    Force HF upload even if no changes detected in Phase 1/2
  --dry-run     Show what would happen without making changes
  --timeout     Lock timeout in seconds (default: 300)
"""

import os
import sys
import json
import hashlib
import sqlite3
import fcntl
import time
import argparse
from datetime import datetime
from pathlib import Path

# Configuration
STATE_DB = Path("/data/.hermes/state.db")
SESSIONS_DIR = Path("/data/.hermes/sessions")
BACKUP_STATE_FILE = SESSIONS_DIR.parent / "backup_state.json"
LOCK_FILE = Path("/data/.hermes/bin/.backup.lock")
TIMEOUT = 300  # seconds


# ============================================================
# Phase 1: JSON → DB  (import orphan sessions)
# ============================================================

def get_db_session_ids(db):
    """Get set of session IDs from the database."""
    try:
        cursor = db.execute("SELECT id FROM sessions")
        return {row[0] for row in cursor.fetchall()}
    except sqlite3.OperationalError:
        return set()


def get_json_session_files(sessions_dir):
    """Scan sessions dir, return dict of session_id → filepath."""
    sessions = {}
    if not sessions_dir.exists():
        return sessions
    for fname in os.listdir(sessions_dir):
        if not fname.startswith("session_") or not fname.endswith(".json"):
            continue
        session_id = fname[8:-5]  # strip "session_" prefix and ".json" suffix
        sessions[session_id] = sessions_dir / fname
    return sessions


def import_session_to_db(db, session_id, filepath, dry_run=False):
    """Import a single JSON session file into SQLite.
    
    Adapts to the actual DB schema:
      sessions: id, source, user_id, model, model_config, system_prompt,
                parent_session_id, started_at, ended_at, end_reason,
                message_count, tool_call_count, input_tokens, output_tokens, ...
      messages: id, session_id, role, content, tool_call_id, tool_calls,
                tool_name, timestamp, token_count, finish_reason, ...
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Support both raw session JSON and wrapped export format
        if "data" in data and "session_id" in data:
            # backup_sessions.py export format: {"session_id": ..., "data": {...}}
            session_data = data["data"]
        else:
            # Raw session JSON
            session_data = data

        # Map JSON fields to DB columns (using actual schema: started_at, not created_at)
        source = session_data.get("source", session_data.get("platform", "unknown"))
        user_id = session_data.get("user_id")  # NULL if not set (DB allows NULL)
        model = session_data.get("model", "unknown")
        model_config = json.dumps(session_data.get("model_config", {}), ensure_ascii=False) if session_data.get("model_config") else None
        system_prompt = session_data.get("system_prompt")  # NULL if not set
        parent_session_id = session_data.get("parent_session_id")  # NULL if not set
        # started_at: try multiple field names, fall back to current time
        started_at = session_data.get("started_at",
                     session_data.get("created_at",
                     session_data.get("start_time", time.time())))
        # title: must use None (not "") because there's a partial unique index
        # idx_sessions_title_unique ON sessions(title) WHERE title IS NOT NULL
        # Empty string "" violates this; NULL is excluded from the index
        title_raw = session_data.get("title")
        title = title_raw if title_raw else None
        message_count = session_data.get("message_count",
                        len(session_data.get("messages", [])))

        if dry_run:
            return True

        db.execute("""
            INSERT OR IGNORE INTO sessions
            (id, source, user_id, model, model_config, system_prompt,
             parent_session_id, started_at, title, message_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, source, user_id, model, model_config, system_prompt,
              parent_session_id, started_at, title, message_count))

        messages = session_data.get("messages", [])
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = "\n".join(
                    p.get("text", "") for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                )
            timestamp = msg.get("timestamp", time.time())
            tool_call_id = msg.get("tool_call_id")
            tool_calls = json.dumps(msg.get("tool_calls"), ensure_ascii=False) if msg.get("tool_calls") else None
            tool_name = msg.get("tool_name")
            token_count = msg.get("token_count")
            finish_reason = msg.get("finish_reason")
            db.execute("""
                INSERT OR IGNORE INTO messages
                (session_id, role, content, tool_call_id, tool_calls,
                 tool_name, timestamp, token_count, finish_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (session_id, role, content, tool_call_id, tool_calls,
                  tool_name, timestamp, token_count, finish_reason))

        db.commit()
        return True

    except Exception as e:
        print(f"  ERROR: Failed to import {session_id}: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return False


def phase1_json_to_db(db, sessions_dir, dry_run=False):
    """Phase 1: Import orphan JSON sessions into SQLite."""
    print("=" * 60)
    print("Phase 1: JSON → DB (import orphan sessions)")
    print("=" * 60)

    db_ids = get_db_session_ids(db)
    json_sessions = get_json_session_files(sessions_dir)

    orphan_ids = sorted(set(json_sessions.keys()) - db_ids)

    print(f"  DB sessions: {len(db_ids)}")
    print(f"  JSON sessions: {len(json_sessions)}")
    print(f"  Orphans (JSON only, not in DB): {len(orphan_ids)}")

    if not orphan_ids:
        print("  No orphans found. DB is in sync.")
        return {"scanned": len(json_sessions), "imported": 0, "errors": 0}

    # Breakdown by type
    eph_ids = [s for s in orphan_ids if s.startswith("eph_")]
    date_ids = [s for s in orphan_ids if s[:4].isdigit() and "_" in s[:9]]
    uuid_ids = [s for s in orphan_ids if "-" in s and not s.startswith(("eph_", "cron_"))]
    other_ids = [s for s in orphan_ids if s not in eph_ids and s not in date_ids and s not in uuid_ids]

    print(f"  Orphan breakdown:")
    print(f"    eph_ (ephemeral): {len(eph_ids)}")
    print(f"    date format: {len(date_ids)}")
    print(f"    UUID format: {len(uuid_ids)}")
    print(f"    other (cron etc): {len(other_ids)}")

    if dry_run:
        print(f"  [DRY RUN] Would import {len(orphan_ids)} sessions")
        return {"scanned": len(json_sessions), "imported": len(orphan_ids), "errors": 0}

    imported = 0
    errors = 0
    for i, sid in enumerate(orphan_ids):
        filepath = str(json_sessions[sid])
        if import_session_to_db(db, sid, filepath, dry_run=False):
            imported += 1
        else:
            errors += 1
        if (i + 1) % 50 == 0:
            print(f"  Progress: {i+1}/{len(orphan_ids)}")

    print(f"  Import complete: {imported} imported, {errors} errors")
    return {"scanned": len(json_sessions), "imported": imported, "errors": errors}


# ============================================================
# Phase 2: DB → JSON  (incremental backup)
# ============================================================

def get_file_hash(filepath):
    """Calculate MD5 hash of a file."""
    if not os.path.exists(filepath):
        return None
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_backup_state():
    """Load the backup state from JSON file."""
    if os.path.exists(BACKUP_STATE_FILE):
        try:
            with open(BACKUP_STATE_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"sessions": {}, "last_backup": None}
    return {"sessions": {}, "last_backup": None}


def save_backup_state(state):
    """Save the backup state to JSON file."""
    state["last_backup"] = datetime.now().isoformat()
    with open(BACKUP_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def extract_sessions_from_db(db_path):
    """Extract session data from the state database."""
    sessions = {}
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        if 'sessions' in tables:
            cursor.execute("SELECT * FROM sessions")
            for row in cursor.fetchall():
                session_data = dict(row)
                session_id = session_data.get('id') or session_data.get('session_id')
                if session_id:
                    sessions[str(session_id)] = session_data
        else:
            for table in tables:
                if 'session' in table.lower() or 'message' in table.lower():
                    try:
                        cursor.execute(f"SELECT * FROM {table}")
                        for row in cursor.fetchall():
                            data = dict(row)
                            session_id = data.get('id') or data.get('session_id') or data.get('uuid')
                            if session_id:
                                sessions[str(session_id)] = data
                    except sqlite3.Error:
                        continue
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        conn.close()

    return sessions


def export_session_to_json(session_id, session_data, output_dir, dry_run=False):
    """Export a single session to a JSON file."""
    filename = f"session_{session_id}.json"
    filepath = output_dir / filename

    export_data = {
        "session_id": session_id,
        "exported_at": datetime.now().isoformat(),
        "data": session_data
    }

    if not dry_run:
        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)

    return filepath, get_file_hash(filepath) if not dry_run else None


def phase2_db_to_json(db_path, sessions_dir, dry_run=False):
    """Phase 2: Incremental backup from SQLite to JSON files."""
    print("\n" + "=" * 60)
    print("Phase 2: DB → JSON (incremental backup)")
    print("=" * 60)

    backup_state = load_backup_state()

    print(f"  Reading sessions from {db_path}")
    sessions = extract_sessions_from_db(db_path)
    print(f"  Found {len(sessions)} sessions in database")

    updated_count = 0
    new_count = 0
    unchanged_count = 0

    for session_id, session_data in sessions.items():
        session_filename = f"session_{session_id}.json"
        session_filepath = sessions_dir / session_filename

        # Calculate current data hash
        current_hash = hashlib.md5(
            json.dumps(session_data, sort_keys=True, default=str).encode()
        ).hexdigest()

        # Check if session needs update
        needs_update = True
        if session_id in backup_state.get("sessions", {}):
            stored_hash = backup_state["sessions"].get(session_id, {}).get("hash")
            if stored_hash == current_hash and session_filepath.exists():
                unchanged_count += 1
                needs_update = False

        if needs_update:
            if not dry_run:
                filepath, file_hash = export_session_to_json(session_id, session_data, sessions_dir)
                backup_state["sessions"][session_id] = {
                    "hash": current_hash,
                    "filepath": str(filepath),
                    "updated_at": datetime.now().isoformat()
                }
            if session_filepath.exists() or dry_run:
                updated_count += 1
                print(f"  Updated session: {session_id}")
            else:
                new_count += 1
                print(f"  New session exported: {session_id}")

    if not dry_run:
        save_backup_state(backup_state)

    print(f"  Backup summary:")
    print(f"    New sessions: {new_count}")
    print(f"    Updated sessions: {updated_count}")
    print(f"    Unchanged sessions: {unchanged_count}")
    print(f"    Total sessions: {len(sessions)}")

    has_changes = (new_count + updated_count) > 0
    return {"new": new_count, "updated": updated_count, "unchanged": unchanged_count, "has_changes": has_changes}


# ============================================================
# Phase 3: DB → HF  (upload to Hugging Face Dataset, optional)
# ============================================================

def phase3_db_to_hf(force=False, dry_run=False):
    """Phase 3: Upload backup data to Hugging Face Dataset.

    Only runs if HF_DATASET_REPO and HF_TOKEN are set.
    Uses data_sync.py's DatasetManager for the actual upload.
    """
    print("\n" + "=" * 60)
    print("Phase 3: DB → HF (Hugging Face Dataset upload)")
    print("=" * 60)

    hf_repo = os.environ.get('HF_DATASET_REPO', '')
    hf_token = os.environ.get('HF_TOKEN', '') or os.environ.get('HUGGING_FACE_HUB_TOKEN', '')

    if not hf_repo:
        print("  HF_DATASET_REPO not set, skipping HF upload.")
        return {"uploaded": False, "reason": "HF_DATASET_REPO not set"}
    if not hf_token:
        print("  HF_TOKEN not set, skipping HF upload.")
        return {"uploaded": False, "reason": "HF_TOKEN not set"}

    if dry_run:
        print(f"  [DRY RUN] Would upload to HF dataset: {hf_repo}")
        return {"uploaded": True, "dry_run": True}

    try:
        # Import data_sync module
        sys.path.insert(0, '/app/src')
        from data_sync import DatasetManager

        manager = DatasetManager(dataset_repo=hf_repo, token=hf_token)
        if not manager.validate():
            print("  DatasetManager validation failed, skipping HF upload.")
            return {"uploaded": False, "reason": "validation failed"}

        print(f"  Uploading to HF dataset: {hf_repo}")
        success = manager.upload_to_dataset(force=force)

        if success:
            print("  HF upload completed successfully.")
            return {"uploaded": True}
        else:
            print("  HF upload failed.")
            return {"uploaded": False, "reason": "upload_failed"}

    except ImportError as e:
        print(f"  Cannot import data_sync module: {e}")
        print("  Skipping HF upload (data_sync.py not available).")
        return {"uploaded": False, "reason": f"import_error: {e}"}
    except Exception as e:
        print(f"  HF upload error: {e}")
        return {"uploaded": False, "reason": f"error: {e}"}


# ============================================================
# Main: orchestrate all three phases
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Hermes Agent Unified Session Sync (3-phase)"
    )
    parser.add_argument("--skip-hf", action="store_true",
                        help="Skip Phase 3 (HF upload)")
    parser.add_argument("--force-hf", action="store_true",
                        help="Force HF upload even if no changes")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without making changes")
    parser.add_argument("--timeout", type=int, default=TIMEOUT,
                        help="Lock timeout in seconds (default: 300)")
    args = parser.parse_args()

    start_time = time.time()
    print(f"Starting unified session sync at {datetime.now().isoformat()}")
    print(f"Options: skip_hf={args.skip_hf}, force_hf={args.force_hf}, dry_run={args.dry_run}")

    # ---- Lock mechanism ----
    if os.path.exists(LOCK_FILE):
        lock_age = time.time() - os.path.getmtime(LOCK_FILE)
        if lock_age < args.timeout:
            print(f"Backup already running (lock file exists, age: {lock_age:.1f}s). Exiting.")
            sys.exit(0)
        else:
            print("Stale lock file found. Removing and continuing.")
            os.remove(LOCK_FILE)

    lock_fd = None
    try:
        lock_fd = open(LOCK_FILE, 'w')
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fd.write(f"{os.getpid()}\n{datetime.now().isoformat()}")
        lock_fd.flush()
    except (IOError, OSError) as e:
        print(f"Could not acquire lock. Another backup may be running. Error: {e}")
        sys.exit(1)

    try:
        # Ensure sessions directory exists
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

        # ---- Phase 1: JSON → DB ----
        db = sqlite3.connect(str(STATE_DB), timeout=30)
        try:
            p1_stats = phase1_json_to_db(db, SESSIONS_DIR, dry_run=args.dry_run)
        finally:
            db.close()

        # ---- Phase 2: DB → JSON ----
        p2_stats = phase2_db_to_json(STATE_DB, SESSIONS_DIR, dry_run=args.dry_run)

        # ---- Phase 3: DB → HF (optional) ----
        p3_stats = {"uploaded": False, "reason": "skipped"}
        if not args.skip_hf:
            # Only upload if there were changes in Phase 1/2, or --force-hf
            has_changes = p1_stats.get("imported", 0) > 0 or p2_stats.get("has_changes", False)
            if has_changes or args.force_hf:
                p3_stats = phase3_db_to_hf(force=args.force_hf, dry_run=args.dry_run)
            else:
                print("\n" + "=" * 60)
                print("Phase 3: DB → HF (skipped, no changes)")
                print("=" * 60)
                print("  No changes detected in Phase 1/2. Use --force-hf to force upload.")

        # ---- Summary ----
        elapsed = time.time() - start_time
        print("\n" + "=" * 60)
        print("SYNC SUMMARY")
        print("=" * 60)
        print(f"  Phase 1 (JSON→DB): {p1_stats.get('imported', 0)} imported, {p1_stats.get('errors', 0)} errors")
        print(f"  Phase 2 (DB→JSON): {p2_stats.get('new', 0)} new, {p2_stats.get('updated', 0)} updated, {p2_stats.get('unchanged', 0)} unchanged")
        print(f"  Phase 3 (DB→HF): {p3_stats}")
        print(f"  Total time: {elapsed:.2f}s")
        print(f"  Completed at: {datetime.now().isoformat()}")

    finally:
        # Release lock
        try:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            lock_fd.close()
            os.remove(LOCK_FILE)
        except Exception:
            pass


if __name__ == "__main__":
    main()
