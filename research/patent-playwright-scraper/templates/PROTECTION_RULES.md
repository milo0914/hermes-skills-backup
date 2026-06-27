# Patent Research Repo — Protection Rules

This repository contains historical patent research reports from Hermes Agent.
Each report is stored as an independent `.tar.gz` archive with a timestamp.

## ⚠️ CRITICAL RULES

### 1. NEVER overwrite existing files

- All reports must be pushed as **timestamped `.tar.gz` archives**
  (e.g., `patent-report-20260521_120000.tar.gz`)
- **DO NOT** push loose files (`.md`, `.json`) to the repo root
  — they will overwrite previous reports with the same name
- **DO NOT** use `git add -A` then `git push` without checking
  what existing files would be overwritten

### 2. ALWAYS use the push script

The correct way to push new reports:

```bash
# Option A: Use the skill's push script
./scripts/push_patent_report_github.sh <report_dir> [commit_msg] [repo_url] [branch]

# Option B: Use the E2E script (auto-push in Stage 7)
python scripts/merck_lc_e2e_2024_2026.py
```

### 3. If you must push manually

1. `git fetch origin main` — get the latest remote state
2. `git checkout -b main origin/main` — start from remote
3. Add ONLY the new `.tar.gz` file: `git add patent-report-YYYYMMDD_HHMMSS.tar.gz`
4. Verify: `git diff --cached --name-only` should show ONLY new files
5. `git commit -m "patent-research: new report YYYYMMDD"`
6. `git push origin main`

### 4. DO NOT force push

- `git push --force` is **never** allowed on this repo
- If push is rejected, use `git pull --rebase` first

### 5. Report directory structure

Expected structure in this repo:

```
patent-report-20260521_120000.tar.gz
patent-report-20260522_143000.tar.gz
patent-report-20260523_091500.tar.gz
PROTECTION_RULES.md
README.md
```

Each `.tar.gz` contains:
- Extracted patents JSON
- Markdown report
- README with extraction metadata

## Why these rules exist

Hermes Agent runs patent research autonomously. Without these rules,
an agent could accidentally overwrite months of accumulated research
by pushing a new report with the same filename as an old one.
The `.tar.gz` + timestamp pattern ensures every report is preserved
independently and never overwritten.
