#!/usr/bin/env python3
"""Daemon-mode JSON-to-DB sync service for Hermes Agent.

Runs as a background process, periodically scanning JSON session backups
and importing any sessions missing from the SQLite database.

This catches sessions that were missed due to:
- Deferred DB writes (run_agent.py: _session_db_created = False)
- SQLite lock failures during concurrent writes
- Process crashes before flush
- HF Space restarts between session creation and DB write

Usage:
  python sync_daemon.py [--interval SECONDS] [--once]

Options:
  --interval    Sync interval in seconds (default: 300)
  --once        Run a single sync pass and exit
"""

import argparse
import json
import logging
import os
import signal
import sqlite3
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [sync-daemon] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SESSIONS_DIR = Path("/data/.hermes/sessions")
DB_PATH = Path("/data/.hermes/state.db")
DEFAULT_INTERVAL = 300  # 5 minutes

running = True


def handle_signal(signum, frame):
    global running
    logger.info("Received signal %d, shutting down...", signum)
    running = False


def get_db_session_ids(db: sqlite3.Connection) -> set:
    cursor = db.execute("SELECT id FROM sessions")
    return {row[0] for row in cursor.fetchall()}


def import_session(db: sqlite3.Connection, session_id: str, filepath: str) -> bool:
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
        logger.error("Import failed for %s: %s", session_id, e)
        try:
            db.rollback()
        except:
            pass
        return False


def sync_pass() -> dict:
    """Run a single sync pass. Returns stats dict."""
    stats = {"scanned": 0, "imported": 0, "errors": 0, "skipped": 0}
    
    if not SESSIONS_DIR.exists() or not DB_PATH.exists():
        logger.warning("Sessions dir or DB not found, skipping")
        return stats
    
    try:
        db = sqlite3.connect(str(DB_PATH), timeout=30)
    except Exception as e:
        logger.error("DB connection failed: %s", e)
        return stats
    
    try:
        db_ids = get_db_session_ids(db)
        
        for fname in os.listdir(SESSIONS_DIR):
            if not fname.startswith("session_") or not fname.endswith(".json"):
                continue
            
            stats["scanned"] += 1
            session_id = fname[8:-5]
            
            if session_id in db_ids:
                stats["skipped"] += 1
                continue
            
            filepath = str(SESSIONS_DIR / fname)
            if import_session(db, session_id, filepath):
                stats["imported"] += 1
            else:
                stats["errors"] += 1
    finally:
        db.close()
    
    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    
    if args.once:
        stats = sync_pass()
        logger.info("Sync complete: scanned=%d imported=%d errors=%d",
                     stats["scanned"], stats["imported"], stats["errors"])
        return 0
    
    logger.info("Starting sync daemon (interval=%ds)", args.interval)
    
    while running:
        try:
            stats = sync_pass()
            if stats["imported"] > 0 or stats["errors"] > 0:
                logger.info(
                    "Sync: scanned=%d imported=%d errors=%d skipped=%d",
                    stats["scanned"], stats["imported"], stats["errors"], stats["skipped"]
                )
            else:
                logger.debug("Sync: all up to date (%d sessions)", stats["scanned"])
        except Exception as e:
            logger.error("Sync pass error: %s", e)
        
        # Sleep in small increments for responsive shutdown
        for _ in range(args.interval):
            if not running:
                break
            time.sleep(1)
    
    logger.info("Sync daemon stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
