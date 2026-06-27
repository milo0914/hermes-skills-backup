# Patent Search Report Location Reference

## Session Discovery (2026-05-19)

**Problem**: User asked "Where is the Merck patent search report .md file from session 4/29~5/12?"

**Search Process**: Extensive searching of:
- `/tmp/hermes_download/` - No standalone patent report found
- `/data/.hermes/sessions/` - Session JSON files exist but no extracted .md report
- `/data/.hermes/skills/` - Only skill reference documents (`patent-database-requirements.md`, `patent-search-strategy.md`)
- `/tmp/hermes-skills-backup/` - Only skill backups, no search reports

**Finding**: Session history from 2026-05-02 to 2026-05-03 shows patent search tasks were performed, but **no standalone report file was ever generated** at a predictable path.

## Session Artifacts Found

### Session Files Containing Patent Search Data
- `/data/.hermes/sessions/session_20260502_232646_6e7e45.json` - Initial patent search request
- `/data/.hermes/sessions/session_20260503_000244_604365.json` - Patent search execution
- `/data/.hermes/sessions/session_20260503_104130_802aa3.json` - Report generation mentioned

### Referenced Report Paths (from session history)
```
/data/merck_negative_dielectric_patents.md
/data/merck_negative_dielectric_patents_report.md
/tmp/merck_negative_dielectric_patents_report.md
```
**Status**: These files do NOT currently exist - they were either never created or were temporary and deleted.

## Root Cause Analysis

**Issue**: Patent search tasks complete with findings embedded in session history, but no standalone `.md` report file is generated at a predictable path.

**Why This Matters**: 
- Users expect to find reports at known file paths in future sessions
- Session JSON files are not user-readable as reports
- Without explicit file generation, search results are effectively lost to future context

## Recommended Workflow for Patent Search Tasks

### Step 1: Pre-Task Announcement
At the START of any patent search task, tell the user:
> "I will save the search report to `/tmp/merck-patent-report.md` when complete. You can reference this file in future sessions."

### Step 2: Perform Search
Use browser automation (browser-use or Playwright) to search patent databases.

### Step 3: Generate Standalone Report
ALWAYS create a standalone report file at a known path:

```bash
cat > /tmp/merck-negative-dielectric-patent-report.md << 'EOF'
# Merck KGaA Negative Dielectric Liquid Crystal Patent Report
**Generated**: 2026-05-19
**Search Query**: assignee:"Merck KGaA" AND "negative dielectric" AND "liquid crystal"
**Database**: Google Patents

## Patents Found
| Patent No | Title | Filing Date | Key Claim |
|-----------|-------|-------------|-----------|
| [Fill in from search results] |

## Search Methodology
- Database: Google Patents (via Playwright browser automation)
- Wait strategy: networkidle + 5s for JS rendering
- Query syntax: assignee:"Merck KGaA" AND "negative dielectric anisotropy"

## Sources
- https://patents.google.com/?q=assignee:%22Merck+KGaA%22+AND+%22negative+dielectric%22+AND+%22liquid+crystal%22
EOF
```

### Step 4: Document the Path
Save the report path to memory or mention it explicitly to the user so they can reference it in future sessions.

## Session Search Queries Used

```
# Search for Merck patent report
grep -l "Merck" /data/.hermes/sessions/*.json

# Search for .md file paths in sessions
grep -o "/tmp/[^"]*\.md\|/data/[^"]*\.md" /data/.hermes/sessions/session_20260503_*.json

# Search for report generation mentions
grep -o "報告已保存至[^\"\\`]*" /data/.hermes/sessions/session_20260503_*.json
```

## Key Learnings

1. **Session history ≠ file existence**: Just because a session mentions creating a file doesn't mean the file persists
2. **Predictable paths matter**: Users expect reports at known, documented paths
3. **Explicit file generation required**: Browser automation results must be explicitly saved to standalone files
4. **Session JSON is not a report**: Raw session data is not user-readable as a report

## Related Files

- `/tmp/hermes_download/skills/browser-automation/references/patent-database-requirements.md` - Patent database technical requirements
- `/tmp/hermes_download/skills/web-researcher/references/patent-search-strategy.md` - Patent search strategy and limitations
- `/data/.hermes/sessions/session_20260503_*.json` - Session files containing patent search history
