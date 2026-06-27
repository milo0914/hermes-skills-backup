#!/usr/bin/env python3
"""One-shot JSON-to-DB sync tool for Hermes Agent sessions.

Scans /data/.hermes/sessions/ for JSON files not present in state.db,
and imports them into the SQLite database so they appear in the Web UI.

Usage:
  python sync_json_to_db.py [--dry-run] [--sessions-dir DIR] [--db-path PATH]

Options:
  --dry-run         Show what would be imported without making changes
  --sessions-dir    Override sessions directory (default: /data/.hermes/sessions)
  --db-path         Override DB path (default: /data/.hermes/state.db)
"""

import argparse
import json
import os
import sqlite3
import time
from pathlib import Path


def get_db_session_ids(db: sqlite3.Connection) -> set:
    cursor = db.execute("SELECT id FROM sessions")
    return {row[0] for row in cursor.fetchall()}


def get_json_session_ids(sessions_dir: Path) -> dict:
    sessions = {}
    for fname in os.listdir(sessions_dir):
        if not fname.startswith("session_") or not fname.endswith(".json"):
            continue
        session_id = fname[8:-5]
        fpath = sessions_dir / fname
        try:
            mtime = os.path.getmtime(fpath)
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            sessions[session_id] = {
                "filepath": str(fpath),
                "mtime": mtime,
                "source": data.get("source", data.get("platform", "unknown")),
                "model": data.get("model", "unknown"),
                "user_id": data.get("user_id", "unknown"),
                "title": data.get("title", ""),
                "msg_count": len(data.get("messages", [])),
            }
        except Exception:
            sessions[session_id] = {
                "filepath": str(fpath),
                "mtime": mtime,
                "source": "unknown",
                "model": "unknown",
                "user_id": "unknown",
                "title": "",
                "msg_count": 0,
            }
    return sessions


def import_session(db: sqlite3.Connection, session_id: str, filepath: str, dry_run: bool = False) -> bool:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        source = data.get("source", data.get("platform", "unknown"))
        model = data.get("model", "unknown")
        model_config = json.dumps(data.get("model_config", {}), ensure_ascii=False)
        system_prompt = data.get("system_prompt", "")
        user_id = data.get("user_id", "unknown")
        parent_session_id = data.get("parent_session_id")
        created_at = data.get("created_at", data.get("start_time", time.time()))
        title = data.get("title", "")
        
        if dry_run:
            return True
        
        db.execute("""
            INSERT OR IGNORE INTO sessions 
            (id, source, model, model_config, system_prompt, user_id,
             parent_session_id, created_at, updated_at, title)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, source, model, model_config, system_prompt,
              user_id, parent_session_id, created_at, time.time(), title))
        
        messages = data.get("messages", [])
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = "\n".join(
                    p.get("text", "") for p in content 
                    if isinstance(p, dict) and p.get("type") == "text"
                )
            db.execute("""
                INSERT OR IGNORE INTO messages 
                (session_id, role, content, timestamp)
                VALUES (?, ?, ?, ?)
            """, (session_id, role, content, msg.get("timestamp", time.time())))
        
        db.commit()
        return True
    except Exception as e:
        print(f"  ERROR: Failed to import {session_id}: {e}")
        try:
            db.rollback()
        except:
            pass
        return False


def main():
    parser = argparse.ArgumentParser(description="Sync JSON session backups to SQLite DB")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sessions-dir", default="/data/.hermes/sessions")
    parser.add_argument("--db-path", default="/data/.hermes/state.db")
    args = parser.parse_args()
    
    sessions_dir = Path(args.sessions_dir)
    db_path = Path(args.db_path)
    
    if not sessions_dir.exists():
        print(f"Error: {sessions_dir} not found")
        return 1
    if not db_path.exists():
        print(f"Error: {db_path} not found")
        return 1
    
    db = sqlite3.connect(str(db_path), timeout=30)
    
    try:
        db_ids = get_db_session_ids(db)
        json_sessions = get_json_session_ids(sessions_dir)
        
        orphan_ids = sorted(set(json_sessions.keys()) - db_ids)
        
        print(f"DB sessions: {len(db_ids)}")
        print(f"JSON sessions: {len(json_sessions)}")
        print(f"Orphans (JSON only): {len(orphan_ids)}")
        print()
        
        if not orphan_ids:
            print("No orphan sessions found. DB is in sync.")
            return 0
        
        # Group orphans by type
        eph_ids = [s for s in orphan_ids if s.startswith("eph_")]
        date_ids = [s for s in orphan_ids if s[:4].isdigit() and "_" in s[:9]]
        uuid_ids = [s for s in orphan_ids if "-" in s and not s.startswith(("eph_", "cron_"))]
        other_ids = [s for s in orphan_ids if s not in eph_ids and s not in date_ids and s not in uuid_ids]
        
        print(f"Orphan breakdown:")
        print(f"  eph_ (ephemeral): {len(eph_ids)}")
        print(f"  date format:      {len(date_ids)}")
        print(f"  UUID format:      {len(uuid_ids)}")
        print(f"  other:            {len(other_ids)}")
        print()
        
        if args.dry_run:
            print(f"[DRY RUN] Would import {len(orphan_ids)} sessions:")
            for sid in orphan_ids[:20]:
                meta = json_sessions[sid]
                print(f"  {sid}")
                print(f"    source={meta['source']}, model={meta['model']}, msgs={meta['msg_count']}")
            if len(orphan_ids) > 20:
                print(f"  ... and {len(orphan_ids) - 20} more")
        else:
            imported = 0
            errors = 0
            for i, sid in enumerate(orphan_ids):
                filepath = json_sessions[sid]["filepath"]
                if import_session(db, sid, filepath, dry_run=False):
                    imported += 1
                else:
                    errors += 1
                if (i + 1) % 50 == 0:
                    print(f"  Progress: {i+1}/{len(orphan_ids)}")
            
            print()
            print(f"Import complete: {imported} imported, {errors} errors")
            
            # Verify
            db_ids_after = get_db_session_ids(db)
            remaining = len(set(json_sessions.keys()) - db_ids_after)
            print(f"Remaining orphans: {remaining}")
        
    finally:
        db.close()
    
    return 0


if __name__ == "__main__":
    exit(main())
