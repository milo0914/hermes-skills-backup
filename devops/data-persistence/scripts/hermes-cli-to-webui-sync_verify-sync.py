#!/usr/bin/env python3
"""
Verify CLI-to-WebUI sync status.
Compares session and message counts between both DBs, checks ID overlap,
and reports any discrepancies.

Usage:
  python3 verify-sync.py
  python3 verify-sync.py --detail   # Show 5 most recent sessions per DB
"""
import sqlite3
import os
import argparse

CLI_DB = os.path.expanduser("~/.hermes/state.db")
WEBUI_DB = os.path.expanduser("~/.hermes-web-ui/hermes-web-ui.db")


def main():
    parser = argparse.ArgumentParser(description="Verify CLI-to-WebUI sync status")
    parser.add_argument("--detail", action="store_true", help="Show recent session samples")
    args = parser.parse_args()

    for path, label in [(CLI_DB, "CLI DB"), (WEBUI_DB, "Web UI DB")]:
        if not os.path.exists(path):
            print(f"ERROR: {label} not found at {path}")
            return 1

    cli = sqlite3.connect(CLI_DB, timeout=10)
    web = sqlite3.connect(WEBUI_DB, timeout=10)

    cli_sessions = cli.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    cli_msgs = cli.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    web_sessions = web.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    web_msgs = web.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

    print(f"CLI:    {cli_sessions} sessions, {cli_msgs} messages")
    print(f"Web UI: {web_sessions} sessions, {web_msgs} messages")

    # ID overlap
    cli_ids = set(r[0] for r in cli.execute("SELECT id FROM sessions").fetchall())
    web_ids = set(r[0] for r in web.execute("SELECT id FROM sessions").fetchall())
    overlap = cli_ids & web_ids
    cli_only = cli_ids - web_ids
    web_only = web_ids - cli_ids

    print(f"Overlap: {len(overlap)}, CLI-only: {len(cli_only)}, Web-only: {len(web_only)}")

    if cli_only:
        print(f"\nWARNING: {len(cli_only)} CLI sessions missing from Web UI — run sync!")

    if args.detail:
        print("\n--- Recent CLI sessions ---")
        rows = cli.execute(
            "SELECT id, source, model, title FROM sessions ORDER BY started_at DESC LIMIT 5"
        ).fetchall()
        for r in rows:
            print(f"  {r[0][:16]}... src={r[1]}, model={r[2]}, title={r[3]}")

        print("\n--- Recent Web UI sessions ---")
        rows = web.execute(
            "SELECT id, source, model, title FROM sessions ORDER BY started_at DESC LIMIT 5"
        ).fetchall()
        for r in rows:
            print(f"  {r[0][:16]}... src={r[1]}, model={r[2]}, title={r[3]}")

    cli.close()
    web.close()

    return 0 if not cli_only else 1


if __name__ == "__main__":
    raise SystemExit(main())
