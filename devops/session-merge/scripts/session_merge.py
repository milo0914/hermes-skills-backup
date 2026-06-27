#!/usr/bin/env python3
"""Session merge tool for Hermes Agent.

Merges multiple independent sessions into a logical group,
enabling cross-device conversation continuity.

Usage:
  # Merge specific sessions
  python session_merge.py merge SID1 SID2 [--name "My Group"] [--user-id USER]

  # Auto-suggest merges for a user
  python session_merge.py suggest [--user-id USER] [--hours 24]

  # Show group for a session
  python session_merge.py show SID

  # Unmerge a session from its group
  python session_merge.py unmerge SID --group-id GRP_ID

  # List all groups
  python session_merge.py list-groups [--user-id USER]

Options:
  --db-path     Override DB path (default: /data/.hermes/state.db)
  --dry-run     Show what would happen without making changes
"""

import argparse
import json
import sqlite3
import time
import uuid
from pathlib import Path


DB_PATH = Path("/data/.hermes/state.db")


def get_db(path: Path = DB_PATH) -> sqlite3.Connection:
    return sqlite3.connect(str(path), timeout=30)


def ensure_tables(db: sqlite3.Connection):
    """Create merge-related tables if they don't exist."""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS session_groups (
            group_id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            user_id TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        
        CREATE TABLE IF NOT EXISTS session_group_members (
            group_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            joined_at REAL NOT NULL,
            relation_type TEXT NOT NULL DEFAULT 'member',
            note TEXT DEFAULT '',
            PRIMARY KEY (group_id, session_id)
        );
        
        CREATE TABLE IF NOT EXISTS session_links (
            session_id_a TEXT NOT NULL,
            session_id_b TEXT NOT NULL,
            link_type TEXT NOT NULL,
            created_at REAL NOT NULL,
            created_by TEXT DEFAULT 'user',
            PRIMARY KEY (session_id_a, session_id_b, link_type)
        );
    """)
    db.commit()


def cmd_merge(args):
    db = get_db(args.db_path)
    ensure_tables(db)
    
    session_ids = args.session_ids
    if len(session_ids) < 2:
        print("Error: Need at least 2 session IDs to merge")
        return 1
    
    # Verify sessions exist
    for sid in session_ids:
        row = db.execute("SELECT id, title FROM sessions WHERE id = ?", (sid,)).fetchone()
        if not row:
            print(f"Error: Session not found in DB: {sid}")
            return 1
    
    group_name = args.name or ""
    if not group_name:
        # Use first session's title
        row = db.execute("SELECT title FROM sessions WHERE id = ?", (session_ids[0],)).fetchone()
        group_name = row[0] if row and row[0] else "Merged Group"
    
    if args.dry_run:
        print(f"[DRY RUN] Would create group: {group_name}")
        for i, sid in enumerate(session_ids):
            relation = "primary" if i == 0 else "continuation"
            print(f"  {sid} → {relation}")
        return 0
    
    group_id = f"grp-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    now = time.time()
    
    db.execute("""
        INSERT INTO session_groups (group_id, name, user_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (group_id, group_name, args.user_id, now, now))
    
    for i, sid in enumerate(session_ids):
        relation = "primary" if i == 0 else "continuation"
        db.execute("""
            INSERT OR IGNORE INTO session_group_members 
            (group_id, session_id, joined_at, relation_type, note)
            VALUES (?, ?, ?, ?, ?)
        """, (group_id, sid, now, relation, ""))
    
    # Create bidirectional links
    for i in range(len(session_ids)):
        for j in range(i + 1, len(session_ids)):
            a, b = sorted([session_ids[i], session_ids[j]])
            db.execute("""
                INSERT OR IGNORE INTO session_links 
                (session_id_a, session_id_b, link_type, created_at, created_by)
                VALUES (?, ?, ?, ?, ?)
            """, (a, b, "merged", now, "user"))
    
    db.commit()
    db.close()
    
    print(f"Created group: {group_id}")
    print(f"  Name: {group_name}")
    print(f"  Members: {len(session_ids)}")
    for i, sid in enumerate(session_ids):
        relation = "primary" if i == 0 else "continuation"
        print(f"    {sid} [{relation}]")
    
    return 0


def cmd_suggest(args):
    db = get_db(args.db_path)
    ensure_tables(db)
    
    cutoff = time.time() - (args.hours * 3600)
    
    if args.user_id:
        sessions = db.execute("""
            SELECT id, title, model, source, created_at 
            FROM sessions WHERE created_at > ? AND user_id = ?
            ORDER BY created_at ASC
        """, (cutoff, args.user_id)).fetchall()
    else:
        sessions = db.execute("""
            SELECT id, title, model, source, created_at 
            FROM sessions WHERE created_at > ?
            ORDER BY created_at ASC
        """, (cutoff,)).fetchall()
    
    if len(sessions) < 2:
        print(f"Not enough sessions (found {len(sessions)}) in the last {args.hours}h")
        return 0
    
    # Find similar sessions
    suggestions = []
    for i, sa in enumerate(sessions):
        words_a = set((sa[1] or "").lower().split())
        if not words_a:
            continue
        for sb in sessions[i+1:]:
            words_b = set((sb[1] or "").lower().split())
            if not words_b:
                continue
            intersection = words_a & words_b
            union = words_a | words_b
            sim = len(intersection) / len(union) if union else 0
            time_gap_h = abs(sa[4] - sb[4]) / 3600
            
            if sim > 0.3:
                suggestions.append({
                    "a": sa[0], "b": sb[0],
                    "title_a": sa[1], "title_b": sb[1],
                    "similarity": round(sim, 2),
                    "gap_hours": round(time_gap_h, 1),
                })
    
    if not suggestions:
        print("No merge suggestions found")
    else:
        print(f"Found {len(suggestions)} merge suggestion(s):")
        for s in sorted(suggestions, key=lambda x: -x["similarity"]):
            print(f"  {s['a']} + {s['b']}")
            print(f"    Titles: \"{s['title_a']}\" / \"{s['title_b']}\"")
            print(f"    Similarity: {s['similarity']}, Time gap: {s['gap_hours']}h")
    
    db.close()
    return 0


def cmd_show(args):
    db = get_db(args.db_path)
    ensure_tables(db)
    
    group = db.execute("""
        SELECT sg.group_id, sg.name, sg.user_id
        FROM session_groups sg
        JOIN session_group_members sgm ON sg.group_id = sgm.group_id
        WHERE sgm.session_id = ?
    """, (args.session_id,)).fetchone()
    
    if not group:
        print(f"Session {args.session_id} is not in any group")
        # Check for direct links
        links = db.execute("""
            SELECT session_id_a, session_id_b, link_type
            FROM session_links
            WHERE session_id_a = ? OR session_id_b = ?
        """, (args.session_id, args.session_id)).fetchall()
        if links:
            print(f"Direct links ({len(links)}):")
            for l in links:
                other = l[1] if l[0] == args.session_id else l[0]
                print(f"  ↔ {other} [{l[2]}]")
        db.close()
        return 0
    
    group_id, name, user_id = group
    members = db.execute("""
        SELECT s.id, s.title, s.source, s.created_at, sgm.relation_type, sgm.note
        FROM sessions s
        JOIN session_group_members sgm ON s.id = sgm.session_id
        WHERE sgm.group_id = ?
        ORDER BY s.created_at ASC
    """, (group_id,)).fetchall()
    
    print(f"Group: {group_id}")
    print(f"  Name: {name}")
    print(f"  User: {user_id or 'unknown'}")
    print(f"  Members ({len(members)}):")
    for m in members:
        from datetime import datetime
        ts = datetime.fromtimestamp(m[3]).strftime("%Y-%m-%d %H:%M") if m[3] else "?"
        print(f"    {m[0]} [{m[4]}] {ts}")
        print(f"      Title: {m[1] or '(untitled)'}")
        if m[5]:
            print(f"      Note: {m[5]}")
    
    db.close()
    return 0


def cmd_unmerge(args):
    db = get_db(args.db_path)
    ensure_tables(db)
    
    if args.dry_run:
        print(f"[DRY RUN] Would remove {args.session_id} from group {args.group_id}")
        return 0
    
    db.execute("""
        DELETE FROM session_group_members 
        WHERE group_id = ? AND session_id = ?
    """, (args.group_id, args.session_id))
    
    # Clean up empty groups
    remaining = db.execute("""
        SELECT COUNT(*) FROM session_group_members WHERE group_id = ?
    """, (args.group_id,)).fetchone()[0]
    
    if remaining <= 1:
        db.execute("DELETE FROM session_group_members WHERE group_id = ?", (args.group_id,))
        db.execute("DELETE FROM session_groups WHERE group_id = ?", (args.group_id,))
        print(f"Group {args.group_id} dissolved (only {remaining} member remaining)")
    else:
        print(f"Removed {args.session_id} from group {args.group_id} ({remaining} members remain)")
    
    db.commit()
    db.close()
    return 0


def cmd_list_groups(args):
    db = get_db(args.db_path)
    ensure_tables(db)
    
    if args.user_id:
        groups = db.execute("""
            SELECT sg.group_id, sg.name, sg.user_id, COUNT(sgm.session_id)
            FROM session_groups sg
            JOIN session_group_members sgm ON sg.group_id = sgm.group_id
            WHERE sg.user_id = ?
            GROUP BY sg.group_id
            ORDER BY sg.updated_at DESC
        """, (args.user_id,)).fetchall()
    else:
        groups = db.execute("""
            SELECT sg.group_id, sg.name, sg.user_id, COUNT(sgm.session_id)
            FROM session_groups sg
            JOIN session_group_members sgm ON sg.group_id = sgm.group_id
            GROUP BY sg.group_id
            ORDER BY sg.updated_at DESC
        """).fetchall()
    
    if not groups:
        print("No session groups found")
    else:
        print(f"Session groups ({len(groups)}):")
        for g in groups:
            print(f"  {g[0]}: \"{g[1]}\" (user={g[2] or 'unknown'}, members={g[3]})")
    
    db.close()
    return 0


def main():
    parser = argparse.ArgumentParser(description="Session merge tool")
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--dry-run", action="store_true")
    sub = parser.add_subparsers(dest="command")
    
    # merge
    p_merge = sub.add_parser("merge", help="Merge sessions into a group")
    p_merge.add_argument("session_ids", nargs="+", help="Session IDs to merge")
    p_merge.add_argument("--name", default="", help="Group name")
    p_merge.add_argument("--user-id", default=None, help="User ID")
    
    # suggest
    p_suggest = sub.add_parser("suggest", help="Suggest sessions to merge")
    p_suggest.add_argument("--user-id", default=None, help="Filter by user")
    p_suggest.add_argument("--hours", type=int, default=24, help="Time window in hours")
    
    # show
    p_show = sub.add_parser("show", help="Show group for a session")
    p_show.add_argument("session_id", help="Session ID")
    
    # unmerge
    p_unmerge = sub.add_parser("unmerge", help="Remove session from group")
    p_unmerge.add_argument("session_id", help="Session ID")
    p_unmerge.add_argument("--group-id", required=True, help="Group ID")
    
    # list-groups
    p_list = sub.add_parser("list-groups", help="List all groups")
    p_list.add_argument("--user-id", default=None, help="Filter by user")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    commands = {
        "merge": cmd_merge,
        "suggest": cmd_suggest,
        "show": cmd_show,
        "unmerge": cmd_unmerge,
        "list-groups": cmd_list_groups,
    }
    
    return commands[args.command](args)


if __name__ == "__main__":
    exit(main())
