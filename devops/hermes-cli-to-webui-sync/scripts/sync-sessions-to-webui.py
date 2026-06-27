#!/usr/bin/env python3
"""
Incremental sync: Hermes CLI state.db → Web UI hermes-web-ui.db

Syncs sessions and messages that exist in CLI DB but are missing from Web UI DB,
and updates sessions that have changed (new message_count, title, etc).

Usage:
  python3 sync-sessions-to-webui.py [--dry-run] [--verbose]
"""
import sqlite3
import argparse
import os
import sys
import time

CLI_DB = os.path.expanduser("~/.hermes/state.db")
WEBUI_DB = os.path.expanduser("~/.hermes-web-ui/hermes-web-ui.db")

# Common columns that exist in both DBs (sessions table)
COMMON_COLS = [
    "id", "source", "user_id", "model", "title",
    "started_at", "ended_at", "end_reason",
    "message_count", "tool_call_count",
    "input_tokens", "output_tokens",
    "cache_read_tokens", "cache_write_tokens", "reasoning_tokens",
    "billing_provider", "estimated_cost_usd", "actual_cost_usd", "cost_status",
]

# Web UI NOT NULL constraints with defaults
WEBUI_NOTNULL_DEFAULTS = {
    "profile": "default",
    "source": "api_server",
    "model": "",
    "message_count": 0,
    "tool_call_count": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "estimated_cost_usd": 0.0,
    "cost_status": "",
    "preview": "",
}

# Web UI-only columns that need defaults
WEBUI_DEFAULTS = {
    "profile": "default",
    "preview": "",
    "last_active": None,
    "workspace": None,
}

# Columns for messages table
# CLI DB messages: id, session_id, role, content, tool_call_id, tool_calls, tool_name, timestamp, token_count, finish_reason, reasoning, reasoning_content, reasoning_details, codex_reasoning_items, codex_message_items
# Web UI messages: id, session_id, role, content, tool_call_id, tool_calls, tool_name, timestamp, token_count, finish_reason, reasoning, reasoning_details, reasoning_content
# Note: Web UI has reasoning_details but NOT reasoning_content, codex_reasoning_items, codex_message_items
MESSAGE_COLS_COMMON = [
    "id", "session_id", "role", "content", "tool_call_id", "tool_calls", "tool_name",
    "timestamp", "token_count", "finish_reason", "reasoning"
]
# CLI-only message columns (will be mapped to Web UI fields)
CLI_MSG_EXTRA = ["reasoning_content", "reasoning_details", "codex_reasoning_items", "codex_message_items"]


def coalesce_for_webui(session_dict):
    """Replace NULL values with Web UI NOT NULL defaults."""
    result = dict(session_dict)
    for col, default in WEBUI_NOTNULL_DEFAULTS.items():
        if col in result and result[col] is None:
            result[col] = default
    return result


def get_cli_sessions(conn_cli):
    """Fetch all sessions from CLI DB with common columns."""
    cols = ", ".join(COMMON_COLS)
    rows = conn_cli.execute(f"SELECT {cols} FROM sessions").fetchall()
    col_indices = {col: i for i, col in enumerate(COMMON_COLS)}
    result = {}
    for row in rows:
        sid = row[col_indices["id"]]
        result[sid] = dict(zip(COMMON_COLS, row))
    return result


def get_webui_sessions(conn_webui):
    """Fetch all sessions from Web UI DB (common cols only) for comparison."""
    cols = ", ".join(COMMON_COLS)
    rows = conn_webui.execute(f"SELECT {cols} FROM sessions").fetchall()
    result = {}
    for row in rows:
        sid = row[0]
        result[sid] = dict(zip(COMMON_COLS, row))
    return result


def needs_update(cli_session, webui_session):
    """Check if CLI session has newer data than Web UI version."""
    mutable_fields = [
        "title", "ended_at", "end_reason",
        "message_count", "tool_call_count",
        "input_tokens", "output_tokens",
        "cache_read_tokens", "cache_write_tokens", "reasoning_tokens",
        "billing_provider", "estimated_cost_usd", "actual_cost_usd", "cost_status",
    ]
    cli = coalesce_for_webui(cli_session)
    for field in mutable_fields:
        cli_val = cli.get(field)
        webui_val = webui_session.get(field)
        if isinstance(cli_val, str) or isinstance(webui_val, str):
            if (cli_val or "") != (webui_val or ""):
                return True
        elif cli_val != webui_val:
            return True
    return False

def get_webui_msg_columns(conn_webui):
    """Get actual columns from Web UI messages table."""
    rows = conn_webui.execute("PRAGMA table_info(messages)").fetchall()
    return {row[1] for row in rows}


def sync_messages(conn_cli, conn_webui, dry_run=False, verbose=False):
    """Sync messages from CLI DB to Web UI DB."""
    # Get all session IDs in WebUI
    webui_session_ids = set(r[0] for r in conn_webui.execute("SELECT id FROM sessions").fetchall())
    # Get all session IDs in CLI
    cli_session_ids = set(r[0] for r in conn_cli.execute("SELECT id FROM sessions").fetchall())
    # Only sync messages for sessions that exist in both
    syncable_ids = webui_session_ids & cli_session_ids

    if not syncable_ids:
        if verbose:
            print("No overlapping sessions for message sync.")
        return 0, 0

    # Get Web UI messages columns
    webui_msg_cols = get_webui_msg_columns(conn_webui)

    # Get all messages from CLI for these sessions
    placeholders = ", ".join(["?"] * len(syncable_ids))
    # Fetch from CLI with all columns
    rows = conn_cli.execute(
        f"SELECT id, session_id, role, content, tool_call_id, tool_calls, tool_name, timestamp, token_count, finish_reason, reasoning, reasoning_content, reasoning_details, codex_reasoning_items, codex_message_items FROM messages WHERE session_id IN ({placeholders})",
        tuple(syncable_ids)
    ).fetchall()

    if not rows:
        if verbose:
            print("No messages to sync.")
        return 0, 0

    # Get existing message IDs in Web UI (to avoid duplicates)
    existing_msg_ids = set(r[0] for r in conn_webui.execute("SELECT id FROM messages").fetchall())

    inserted = 0
    skipped = 0

    if dry_run:
        total_to_insert = len([r for r in rows if r[0] not in existing_msg_ids])
        if verbose:
            print(f"Messages to sync: {total_to_insert} (from {len(rows)} CLI messages, {len(existing_msg_ids)} already in WebUI)")
        return 0, 0

    for row in rows:
        msg_id = row[0]
        if msg_id in existing_msg_ids:
            continue

        # Map CLI columns to Web UI columns
        session_id = row[1]
        role = row[2]
        content = row[3]
        tool_call_id = row[4]
        tool_calls = row[5]
        tool_name = row[6]
        timestamp = row[7]
        token_count = row[8]
        finish_reason = row[9]
        reasoning = row[10]
        reasoning_content = row[11]
        reasoning_details = row[12]
        codex_reasoning_items = row[13]
        codex_message_items = row[14]

        # Build INSERT dynamically based on available Web UI columns
        insert_cols = ["id", "session_id", "role", "content", "tool_call_id", "tool_calls", "tool_name", "timestamp", "token_count", "finish_reason", "reasoning"]
        values = [msg_id, session_id, role, content, tool_call_id, tool_calls, tool_name, timestamp, token_count, finish_reason, reasoning]

        # Handle reasoning_details if present in Web UI
        if "reasoning_details" in webui_msg_cols:
            insert_cols.append("reasoning_details")
            # Prefer reasoning_details, fall back to reasoning_content or codex_reasoning_items
            rd_value = reasoning_details
            if not rd_value and reasoning_content:
                rd_value = reasoning_content
            if not rd_value and codex_reasoning_items:
                rd_value = codex_reasoning_items
            values.append(rd_value)

        if "reasoning_content" in webui_msg_cols:
            insert_cols.append("reasoning_content")
            values.append(reasoning_content)

        placeholders = ", ".join(["?"] * len(insert_cols))
        sql = f"INSERT INTO messages ({', '.join(insert_cols)}) VALUES ({placeholders})"

        try:
            conn_webui.execute(sql, values)
            inserted += 1
        except Exception as e:
            print(f"ERROR inserting message {msg_id}: {e}")
            skipped += 1

    return inserted, skipped


def sync(dry_run=False, verbose=False):
    if not os.path.exists(CLI_DB):
        print(f"ERROR: CLI DB not found at {CLI_DB}")
        return 1
    if not os.path.exists(WEBUI_DB):
        print(f"ERROR: Web UI DB not found at {WEBUI_DB}")
        return 1

    conn_cli = sqlite3.connect(CLI_DB, timeout=10)
    conn_cli.execute("PRAGMA journal_mode=WAL")
    conn_cli.execute("PRAGMA busy_timeout=5000")

    conn_webui = sqlite3.connect(WEBUI_DB, timeout=10)
    conn_webui.execute("PRAGMA journal_mode=WAL")
    conn_webui.execute("PRAGMA busy_timeout=5000")
    conn_webui.execute("PRAGMA synchronous=NORMAL")

    # --- Phase 1: Sync sessions ---
    cli_sessions = get_cli_sessions(conn_cli)
    webui_sessions = get_webui_sessions(conn_webui)
    webui_ids = set(webui_sessions.keys())

    cli_ids = set(cli_sessions.keys())
    new_ids = cli_ids - webui_ids
    common_ids = cli_ids & webui_ids

    update_ids = set()
    for sid in common_ids:
        if needs_update(cli_sessions[sid], webui_sessions[sid]):
            update_ids.add(sid)

    print(f"CLI DB sessions:    {len(cli_ids)}")
    print(f"Web UI DB sessions: {len(webui_ids)}")
    print(f"New to insert:      {len(new_ids)}")
    print(f"Changed to update:  {len(update_ids)}")

    if dry_run:
        if verbose and new_ids:
            print(f"\nNew session IDs (first 10):")
            for sid in sorted(new_ids)[:10]:
                s = cli_sessions[sid]
                title = s.get('title') or '<none>'
                print(f"  {sid}: title={title[:60]}, model={s.get('model') or ''}")
            if len(new_ids) > 10:
                print(f"  ... and {len(new_ids)-10} more")
        if verbose and update_ids:
            print(f"\nUpdated session IDs (first 10):")
            for sid in sorted(update_ids)[:10]:
                s = cli_sessions[sid]
                title = s.get('title') or '<none>'
                print(f"  {sid}: title={title[:60]}, msgs={s.get('message_count') or 0}")
            if len(update_ids) > 10:
                print(f"  ... and {len(update_ids)-10} more")
        # Also show message sync dry-run
        sync_messages(conn_cli, conn_webui, dry_run=True, verbose=verbose)
        print("\n[DRY RUN] No changes made.")
        conn_cli.close()
        conn_webui.close()
        return 0

    # Build INSERT statement for new sessions
    all_cols = COMMON_COLS + list(WEBUI_DEFAULTS.keys())
    insert_placeholders = ", ".join(["?"] * len(all_cols))
    insert_sql = f"INSERT INTO sessions ({', '.join(all_cols)}) VALUES ({insert_placeholders})"

    # Build UPDATE statement for changed sessions
    update_cols = [c for c in COMMON_COLS if c != "id"]
    update_set = ", ".join([f"{c}=?" for c in update_cols])
    update_sql = f"UPDATE sessions SET {update_set} WHERE id=?"

    inserted = 0
    updated = 0

    try:
        conn_webui.execute("BEGIN TRANSACTION")

        # Insert new sessions
        for sid in new_ids:
            s = coalesce_for_webui(cli_sessions[sid])
            values = [s.get(c) for c in COMMON_COLS]
            values.append(WEBUI_DEFAULTS["profile"])
            values.append(WEBUI_DEFAULTS["preview"])
            values.append(s.get("started_at"))
            values.append(WEBUI_DEFAULTS["workspace"])
            conn_webui.execute(insert_sql, values)
            inserted += 1

        # Update changed sessions
        for sid in update_ids:
            s = coalesce_for_webui(cli_sessions[sid])
            values = [s.get(c) for c in update_cols]
            values.append(sid)
            conn_webui.execute(update_sql, values)
            updated += 1

        # --- Phase 2: Sync messages ---
        if verbose:
            print("\nSyncing messages...")
        msg_inserted, msg_skipped = sync_messages(conn_cli, conn_webui, dry_run=False, verbose=verbose)

        conn_webui.commit()
    except Exception as e:
        conn_webui.rollback()
        print(f"ERROR: Sync failed: {e}")
        conn_cli.close()
        conn_webui.close()
        return 1

    print(f"\nSync completed: {inserted} sessions inserted, {updated} sessions updated")
    if msg_inserted or msg_skipped:
        print(f"Messages: {msg_inserted} inserted, {msg_skipped} skipped")

    # Verify
    final_count = conn_webui.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    final_msgs = conn_webui.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    print(f"Web UI DB after sync: {final_count} sessions, {final_msgs} messages")

    conn_cli.close()
    conn_webui.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Hermes CLI sessions to Web UI DB")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be synced without making changes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show details of synced sessions")
    args = parser.parse_args()
    sys.exit(sync(dry_run=args.dry_run, verbose=args.verbose))
