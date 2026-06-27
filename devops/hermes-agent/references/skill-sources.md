# Skill Sources Reference

This document catalogs the major skill sources and their installation patterns.

## Official Registries

### 1. Skills.sh Registry
**URL:** https://skills.sh/  
**Trust Level:** Community (varies by author)

**Installation Pattern:**
```bash
# Auto-resolving short names (preferred)
hermes skills install gws-calendar
hermes skills install gws-gmail
hermes skills install debugging
hermes skills install skill-creator

# Full path (may fail)
hermes skills install skills-sh/googleworkspace/cli/gws-calendar  # Avoid
```

**Notable Skills:**
- `gws-*` series (Google Workspace integration)
- `debugging` (Turso database debugging)
- `skill-creator` (Anthropic official - skill creation workflow)

### 2. Anthropic Official Skills
**Source:** https://github.com/anthropics/skills  
**Trust Level:** Trusted

**Installation Pattern:**
```bash
hermes skills install skills-sh/anthropics/skills/skill-creator --force
```

**Key Skills:**
- `skill-creator`: Complete skill creation, testing, and optimization workflow
  - Includes eval framework, benchmarking, description optimization
  - May trigger CAUTION verdict due to env var handling in eval scripts
  - Safe to override for this trusted source

### 3. Vercel Labs Skills
**Source:** https://github.com/vercel-labs/skills  
**Trust Level:** Community (trusted source)

**Installation Pattern:**
```bash
# Direct URL installation
hermes skills install https://raw.githubusercontent.com/vercel-labs/skills/main/skills/find-skills/SKILL.md
```

**Key Skills:**
- `find-skills`: Skills.sh ecosystem discovery and installation guidance

### 4. LobeHub
**Trust Level:** Community

**Installation Pattern:**
```bash
hermes skills install lobehub/singer
hermes skills install lobehub/suno
```

### 5. ClawHub
**Trust Level:** Community

**Installation Pattern:**
```bash
hermes skills install 1password
hermes skills install arxiv
hermes skills install felo-search
```

## Direct URL Installation

### GitHub Raw URLs (Works)
```bash
# Correct format
hermes skills install https://raw.githubusercontent.com/NousResearch/hermes-agent/main/skills/creative/claude-design/SKILL.md
hermes skills install https://raw.githubusercontent.com/vercel-labs/skills/main/skills/find-skills/SKILL.md
```

### GitHub Tree/Blob URLs (Don't Work Directly)
```bash
# Wrong - won't work
https://github.com/user/repo/tree/main/path/to/skill
https://github.com/user/repo/blob/main/path/to/skill/SKILL.md

# Correct conversion
https://raw.githubusercontent.com/user/repo/main/path/to/skill/SKILL.md
```

## Installation Command Patterns

### Basic Installation
```bash
# Simple install (no prompts)
hermes skills install <skill-name>

# Install with force override (for CAUTION verdicts)
hermes skills install <skill-name> --force
echo "y" | hermes skills install <skill-name> --force
```

### URL Installation with Category Prompt
```bash
# When installing from URLs, you'll be prompted for category
printf "devops\\ny" | hermes skills install https://raw.githubusercontent.com/.../SKILL.md
printf "creative\\ny" | hermes skills install https://raw.githubusercontent.com/.../SKILL.md
printf "research\\ny" | hermes skills install https://raw.githubusercontent.com/.../SKILL.md
```

### Search Before Installing
```bash
# Find the correct identifier
hermes skills search <query>
hermes skills inspect <identifier>

# Then install
hermes skills install <short-name>
hermes skills install <short-name> --force  # If blocked
```

## Security Scan Verdicts

### SAFE (No Override Needed)
- Official Nous Research skills
- Well-known community skills with clean patterns

### CAUTION (Override with --force)
Common triggers:
- `pip install` commands (supply chain risk)
- `curl`/`wget` to external URLs
- API key handling
- Browser automation
- `sudo` usage
- Shell profile modifications

**Override pattern:**
```bash
hermes skills install <skill> --force
echo "y" | hermes skills install <skill> --force
```

## Skill Locations

**Installed Skills:** `/data/.hermes/skills/<skill-name>/`  
**Hub Skills:** `/data/.hermes/skills/.hub/<source>/skills/`

## Verification

After installation:
```bash
# Confirm installation
hermes skills list

# Check status
hermes skills list | grep <skill-name>
```

### 6. Gstack (garrytan/gstack)
**Source:** https://github.com/garrytan/gstack
**Trust Level:** Community (YC-affiliated, well-known)
**Detail Page:** https://skills.sh/garrytan/gstack/gstack

**Description:** Fast headless browser QA testing + plan review suite. Designed for Claude Code workflows (references CLAUDE.md, TODOS.md). Includes CEO/design/eng review, QA, autoplan, and upgrade management.

**Installation Identifiers:**
```bash
# Main skill (auto-resolves to skills-sh/garrytan/gstack/gstack)
hermes skills install gstack --force

# Sub-skills via skills.sh full path
hermes skills install skills-sh/garrytan/gstack/office-hours --force
hermes skills install skills-sh/garrytan/gstack/plan-ceo-review --force
hermes skills install skills-sh/garrytan/gstack/plan-design-review --force
hermes skills install skills-sh/garrytan/gstack/plan-eng-review --force
hermes skills install skills-sh/garrytan/gstack/qa --force
hermes skills install skills-sh/garrytan/gstack/review --force

# Autoplan via GitHub source
hermes skills install garrytan/gstack/autoplan --force
```

**Security scan verdict:** Always DANGEROUS due to:
- CRITICAL persistence: modifies CLAUDE.md (designed for Claude Code workflows)
- HIGH privilege_escalation: `allowed-tools` declarations
- MEDIUM supply_chain: `git clone` in setup scripts
- These are by-design for Claude Code integration; safe to --force override

**Batch install pattern (all 7 at once):**
```bash
for skill in gstack \
  skills-sh/garrytan/gstack/office-hours \
  skills-sh/garrytan/gstack/plan-ceo-review \
  skills-sh/garrytan/gstack/plan-design-review \
  skills-sh/garrytan/gstack/plan-eng-review \
  skills-sh/garrytan/gstack/qa \
  skills-sh/garrytan/gstack/review \
  garrytan/gstack/autoplan; do
  echo "y" | hermes skills install "$skill" --force 2>&1
done
```

**Installed skill names:** gstack-upgrade, office-hours, plan-ceo-review, plan-design-review, plan-eng-review, qa, review, autoplan

**Note:** The main `gstack` skill installs as `gstack-upgrade` (the SKILL.md frontmatter name). The `gstack` search also returns results from other authors (aicreator-windo, aradotso/trending-skills) — use the full `skills-sh/garrytan/gstack/` prefix to ensure correct source.

## Quick Reference Table

| Source | Pattern | Example | Trust |
|--------|---------|---------|-------|
| Official | `official/<cat>/<name>` | `official/research/arxiv` | ★ |
| Skills.sh | Short name | `gws-calendar`, `debugging` | Community |
| Anthropic | `skills-sh/anthropics/skills/<name>` | `skill-creator` | Trusted |
| LobeHub | `lobehub/<name>` | `lobehub/singer` | Community |
| ClawHub | Auto-resolved | `1password`, `arxiv` | Community |
| Gstack | `skills-sh/garrytan/gstack/<name>` | `gstack`, `qa`, `review` | Community |
| Direct URL | Raw GitHub URL | See above | Varies |
