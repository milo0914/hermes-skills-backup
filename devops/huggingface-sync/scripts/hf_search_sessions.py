#!/usr/bin/env python3
"""Search sessions in HF dataset backup by keywords.

Usage:
  python3 hf_search_sessions.py "keyword1,keyword2" [--repo REPO] [--limit N] [--include-cron] [--date-range START,END] [--content-only]

Environment variables (or .env fallback):
  AUTH_TOKEN        - HF write token (also reads from /data/.hermes/.env)
  HF_DATASET_REPO  - e.g. "username/dataset-name" (can override with --repo)

Improvements over v1:
  - Reads AUTH_TOKEN from .env if not in env vars
  - Supports --repo to override HF_DATASET_REPO
  - Handles nested JSON format (data key wrapping)
  - Skips empty sessions (0 messages)
  - Supports --date-range for filtering by session filename date
  - Supports --content-only to search message content only (not metadata)
"""

import argparse, json, os, sys
from huggingface_hub import hf_hub_download, list_repo_files

def load_env_fallback():
    """Read /data/.hermes/.env and return dict of key=value pairs."""
    env = {}
    env_path = '/data/.hermes/.env'
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, val = line.split('=', 1)
                    env[key.strip()] = val.strip()
    return env

def get_token():
    """Get HF token from env var or .env fallback."""
    token = os.environ.get('AUTH_TOKEN', '')
    if not token:
        env = load_env_fallback()
        token = env.get('AUTH_TOKEN', '')
    return token

def get_repo_id(cli_repo):
    """Get repo ID from CLI arg, env var, or .env fallback."""
    if cli_repo:
        return cli_repo
    repo = os.environ.get('HF_DATASET_REPO', '')
    if not repo:
        env = load_env_fallback()
        repo = env.get('HF_DATASET_REPO', '')
    return repo

def extract_messages(data):
    """Extract messages list from either flat or nested JSON format."""
    messages = data.get('messages', [])
    if not messages and 'data' in data and isinstance(data['data'], dict):
        messages = data['data'].get('messages', [])
    return messages

def extract_model(data):
    """Extract model from either flat or nested JSON format."""
    model = data.get('model', '')
    if not model and 'data' in data and isinstance(data['data'], dict):
        model = data['data'].get('model', '')
    return model

def extract_first_user(messages):
    """Extract first real user message content."""
    for msg in messages:
        if msg.get('role') == 'user':
            c = msg.get('content', '')
            if isinstance(c, list):
                c = ' '.join(p.get('text', '') for p in c if p.get('type') == 'text')
            if not c.startswith('[Tool result:'):
                return c[:400]
    return ''

def parse_date_range(date_range_str):
    """Parse date range like '20260606,20260607' into filename prefix filters."""
    if not date_range_str:
        return None, None
    parts = date_range_str.split(',')
    start = parts[0].strip() if len(parts) > 0 else None
    end = parts[1].strip() if len(parts) > 1 else None
    return start, end

def main():
    parser = argparse.ArgumentParser(description='Search HF backup sessions by keywords')
    parser.add_argument('keywords', help='Comma-separated keywords to search')
    parser.add_argument('--repo', help='HF dataset repo (overrides HF_DATASET_REPO)')
    parser.add_argument('--limit', type=int, default=0, help='Limit to last N sessions (0=all)')
    parser.add_argument('--include-cron', action='store_true', help='Include cron sessions')
    parser.add_argument('--date-range', help='Filter by date range in filename: "20260606,20260607"')
    parser.add_argument('--content-only', action='store_true', help='Search message content only (skip metadata)')
    args = parser.parse_args()

    token = get_token()
    repo_id = get_repo_id(args.repo)

    if not token:
        print('ERROR: AUTH_TOKEN not found in env vars or .env', file=sys.stderr)
        sys.exit(1)
    if not repo_id:
        print('ERROR: HF_DATASET_REPO not set. Use --repo or set env var.', file=sys.stderr)
        sys.exit(1)

    keywords = [k.strip() for k in args.keywords.split(',')]
    date_start, date_end = parse_date_range(args.date_range)

    files = list_repo_files(repo_id, repo_type='dataset', token=token)
    session_files = sorted([f for f in files if f.startswith('sessions/') and f.endswith('.json')])

    if not args.include_cron:
        session_files = [f for f in session_files if not os.path.basename(f).startswith('cron_')]

    # Date range filter based on filename
    if date_start or date_end:
        filtered = []
        for sf in session_files:
            basename = os.path.basename(sf)
            # Extract date from filename like session_20260606_134631_f375c2.json
            # or session_82f18f90-63f0-4d3c-b3fa-9d476b7b4d8e.json
            date_part = ''
            for part in basename.replace('session_', '').replace('.json', '').split('_'):
                if len(part) == 8 and part.isdigit():
                    date_part = part
                    break
            if not date_part:
                continue  # UUID-based filenames can't be date-filtered
            if date_start and date_part < date_start:
                continue
            if date_end and date_part > date_end:
                continue
            filtered.append(sf)
        session_files = filtered

    if args.limit > 0:
        session_files = session_files[-args.limit:]

    print(f"Scanning {len(session_files)} sessions for keywords: {keywords}", flush=True)
    if date_start or date_end:
        print(f"Date range filter: {date_start or '...'} to {date_end or '...'}", flush=True)

    matches = []
    empty_count = 0

    for idx, sf in enumerate(session_files):
        if idx % 100 == 0:
            print(f"  Progress: {idx}/{len(session_files)}...", flush=True)
        try:
            local_path = hf_hub_download(repo_id=repo_id, filename=sf, repo_type='dataset', token=token)
            with open(local_path, 'r', encoding='utf-8') as f:
                content = f.read()

            data = json.loads(content)
            messages = extract_messages(data)
            model = extract_model(data)

            # Skip empty sessions
            if len(messages) == 0:
                empty_count += 1
                continue

            # Search scope
            search_text = content if not args.content_only else ''
            if args.content_only:
                # Only search message content, not metadata/system prompts
                search_parts = []
                for msg in messages:
                    c = msg.get('content', '')
                    if isinstance(c, list):
                        c = ' '.join(p.get('text', '') for p in c if p.get('type') == 'text')
                    search_parts.append(c)
                search_text = '\n'.join(search_parts)

            found = [kw for kw in keywords if kw.lower() in search_text.lower()]
            if found:
                first_user = extract_first_user(messages)
                matches.append({
                    'file': sf,
                    'keywords': found,
                    'model': model,
                    'msg_count': len(messages),
                    'first_user': first_user,
                })
        except Exception as e:
            pass

    print(f"\n=== Found {len(matches)} matching sessions (skipped {empty_count} empty) ===\n")
    for m in matches:
        print(f"File: {m['file']}")
        print(f"  Keywords: {', '.join(m['keywords'])}")
        print(f"  Model: {m['model']}, Messages: {m['msg_count']}")
        print(f"  First user msg: {m['first_user'][:300]}")
        print()

if __name__ == '__main__':
    main()
