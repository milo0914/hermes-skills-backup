#!/usr/bin/env python3
"""Migrate eph_ and legacy date-format session IDs to unified format.

This script:
1. Renames session JSON files from eph_/date format to unified format
2. Updates session_id inside each JSON file
3. Updates SQLite DB records (if present)
4. Updates backup_state.json mapping

Unified format: {prefix}-YYYYMMDD-HHMMSS-{short6}
  - eph_mooXXXX_YYYYYY → eph-migrated-XXXX-YYYY
  - 20260502_152315_349039 → legacy-20260502-152315-349039
  - UUID format: unchanged
  - cron_ format: unchanged

Usage:
  python migrate_legacy_sessions.py [--dry-run] [--sessions-dir /data/.hermes/sessions]

Options:
  --dry-run         Show what would be changed without making changes
  --sessions-dir    Override sessions directory (default: /data/.hermes/sessions)
"""

import argparse
import json
import os
import re
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime


def migrate_session_id(old_id: str) -> str:
    """Convert legacy session ID to unified format.
    
    Rules:
    - eph_mooXXXX_YYYYYY → eph-migrated-XXXX-YYYY
    - 20260502_152315_349039 → legacy-20260502-152315-349039
    - UUID (xxx-xxx-xxx) → unchanged
    - cron_xxx → unchanged
    - api-xxx → unchanged
    """
    # eph_ prefix: ephemeral sessions from old TUI
    if old_id.startswith("eph_"):
        parts = old_id[4:]  # Remove 'eph_'
        return f"eph-migrated-{parts.replace('_', '-')}"
    
    # Date format: YYYYMMDD_HHMMSS_XXXXXX
    if re.match(r'^\d{8}_\d{6}_', old_id):
        return f"legacy-{old_id.replace('_', '-')}"
    
    # Already unified or standard format
    return old_id


def needs_migration(session_id: str) -> bool:
    """Check if a session ID needs migration."""
    return session_id != migrate_session_id(session_id)


def run_migration(sessions_dir: Path, db_path: Path, dry_run: bool = False) -> dict:
    """Execute the migration and return a summary."""
    stats = {
        "total_json": 0,
        "migrated_json": 0,
        "migrated_db": 0,
        "migrated_backup": 0,
        "errors": [],
        "mapping": {},
    }
    
    db = None
    if db_path.exists() and not dry_run:
        try:
            db = sqlite3.connect(str(db_path))
        except Exception as e:
            stats["errors"].append(f"DB connection failed: {e}")
    
    # Step 1: Migrate JSON session files
    for fname in sorted(os.listdir(sessions_dir)):
        if not fname.startswith("session_") or not fname.endswith(".json"):
            continue
        
        stats["total_json"] += 1
        old_id = fname[8:-5]  # Remove 'session_' prefix and '.json' suffix
        new_id = migrate_session_id(old_id)
        
        if old_id == new_id:
            continue
        
        old_path = sessions_dir / fname
        new_path = sessions_dir / f"session_{new_id}.json"
        
        if dry_run:
            print(f"  [DRY] {old_id} → {new_id}")
            stats["migrated_json"] += 1
            stats["mapping"][old_id] = new_id
            continue
        
        try:
            # Read and update JSON content
            with open(old_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            data["session_id"] = new_id
            # Also update any internal references
            if "parent_session_id" in data and data["parent_session_id"] == old_id:
                data["parent_session_id"] = new_id
            
            # Write new file
            with open(new_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Remove old file
            os.unlink(old_path)
            
            stats["migrated_json"] += 1
            stats["mapping"][old_id] = new_id
            
            # Update DB if record exists
            if db:
                try:
                    cursor = db.execute(
                        "UPDATE sessions SET id = ? WHERE id = ?",
                        (new_id, old_id)
                    )
                    if cursor.rowcount > 0:
                        stats["migrated_db"] += cursor.rowcount
                        # Also update messages table
                        db.execute(
                            "UPDATE messages SET session_id = ? WHERE session_id = ?",
                            (new_id, old_id)
                        )
                except Exception as e:
                    stats["errors"].append(f"DB update failed for {old_id}: {e}")
                    
        except Exception as e:
            stats["errors"].append(f"JSON migration failed for {old_id}: {e}")
    
    # Step 2: Update backup_state.json
    backup_path = sessions_dir.parent / "backup_state.json"
    if backup_path.exists() and stats["mapping"]:
        if dry_run:
            stats["migrated_backup"] = len(stats["mapping"])
            print(f"  [DRY] Would update backup_state.json ({len(stats['mapping'])} entries)")
        else:
            try:
                with open(backup_path, "r", encoding="utf-8") as f:
                    backup = json.load(f)
                
                sessions = backup.get("sessions", {})
                updated = 0
                for old_id, new_id in stats["mapping"].items():
                    if old_id in sessions:
                        entry = sessions.pop(old_id)
                        if "filepath" in entry:
                            entry["filepath"] = entry["filepath"].replace(old_id, new_id)
                        sessions[new_id] = entry
                        updated += 1
                
                with open(backup_path, "w", encoding="utf-8") as f:
                    json.dump(backup, f, indent=2, ensure_ascii=False)
                
                stats["migrated_backup"] = updated
            except Exception as e:
                stats["errors"].append(f"backup_state.json update failed: {e}")
    
    # Commit DB changes
    if db:
        try:
            db.commit()
        except Exception as e:
            stats["errors"].append(f"DB commit failed: {e}")
        finally:
            db.close()
    
    return stats


def main():
    parser = argparse.ArgumentParser(description="Migrate legacy session IDs to unified format")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without executing")
    parser.add_argument("--sessions-dir", default="/data/.hermes/sessions", help="Sessions directory")
    parser.add_argument("--db-path", default="/data/.hermes/state.db", help="State DB path")
    args = parser.parse_args()
    
    sessions_dir = Path(args.sessions_dir)
    db_path = Path(args.db_path)
    
    if not sessions_dir.exists():
        print(f"Error: Sessions directory not found: {sessions_dir}")
        return 1
    
    print(f"Session ID Migration {'(DRY RUN)' if args.dry_run else ''}")
    print(f"Sessions dir: {sessions_dir}")
    print(f"DB path: {db_path}")
    print()
    
    stats = run_migration(sessions_dir, db_path, dry_run=args.dry_run)
    
    print()
    print("=== Migration Summary ===")
    print(f"Total JSON files scanned: {stats['total_json']}")
    print(f"JSON files migrated: {stats['migrated_json']}")
    print(f"DB records updated: {stats['migrated_db']}")
    print(f"Backup entries updated: {stats['migrated_backup']}")
    if stats['errors']:
        print(f"Errors: {len(stats['errors'])}")
        for err in stats['errors']:
            print(f"  - {err}")
    print()
    
    if stats['mapping']:
        print("ID Mapping (old → new):")
        for old_id, new_id in sorted(stats['mapping'].items()):
            print(f"  {old_id} → {new_id}")
    
    return 0 if not stats['errors'] else 1


if __name__ == "__main__":
    exit(main())
