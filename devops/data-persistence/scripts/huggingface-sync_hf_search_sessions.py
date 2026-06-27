#!/usr/bin/env python3
"""Search sessions in HF dataset backup by keywords.

Usage:
  python3 hf_search_sessions.py "keyword1,keyword2" [--limit N] [--include-cron]

Environment variables required:
  AUTH_TOKEN - HF write token
  HF_DATASET_REPO - e.g. "username/dataset-name"
"""

import argparse, json, os, sys
from huggingface_hub import hf_hub_download, list_repo_files

def main():
    parser = argparse.ArgumentParser(description='Search HF backup sessions by keywords')
    parser.add_argument('keywords', help='Comma-separated keywords to search')
    parser.add_argument('--limit', type=int, default=0, help='Limit to last N sessions (0=all)')
    parser.add_argument('--include-cron', action='store_true', help='Include cron sessions')
    args = parser.parse_args()

    token = os.environ.get('AUTH_TOKEN', '')
    repo_id = os.environ.get('HF_DATASET_REPO', '')
    if not token or not repo_id:
        print('ERROR: AUTH_TOKEN and HF_DATASET_REPO must be set', file=sys.stderr)
        sys.exit(1)

    keywords = [k.strip() for k in args.keywords.split(',')]

    files = list_repo_files(repo_id, repo_type='dataset', token=token)
    session_files = sorted([f for f in files if f.startswith('sessions/') and f.endswith('.json')])

    if not args.include_cron:
        session_files = [f for f in session_files if not os.path.basename(f).startswith('cron_')]

    if args.limit > 0:
        session_files = session_files[-args.limit:]

    print(f"Scanning {len(session_files)} sessions for keywords: {keywords}", flush=True)
    matches = []

    for idx, sf in enumerate(session_files):
        if idx % 100 == 0:
            print(f"  Progress: {idx}/{len(session_files)}...", flush=True)
        try:
            local_path = hf_hub_download(repo_id=repo_id, filename=sf, repo_type='dataset', token=token)
            with open(local_path, 'r', encoding='utf-8') as f:
                content = f.read()
            found = [kw for kw in keywords if kw.lower() in content.lower()]
            if found:
                data = json.loads(content)
                first_user = ''
                for msg in data.get('messages', []):
                    if msg.get('role') == 'user':
                        c = msg.get('content', '')
                        if isinstance(c, list):
                            c = ' '.join(p.get('text', '') for p in c if p.get('type') == 'text')
                        first_user = c[:400]
                        break
                matches.append({
                    'file': sf,
                    'keywords': found,
                    'model': data.get('model', ''),
                    'msg_count': len(data.get('messages', [])),
                    'first_user': first_user
                })
        except Exception:
            pass

    print(f"\n=== Found {len(matches)} matching sessions ===\n")
    for m in matches:
        print(f"File: {m['file']}")
        print(f"  Keywords: {', '.join(m['keywords'])}")
        print(f"  Model: {m['model']}, Messages: {m['msg_count']}")
        print(f"  First user msg: {m['first_user'][:300]}")
        print()

if __name__ == '__main__':
    main()
