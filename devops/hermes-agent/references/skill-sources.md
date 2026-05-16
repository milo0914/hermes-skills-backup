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

## Quick Reference Table

| Source | Pattern | Example | Trust |
|--------|---------|---------|-------|
| Official | `official/<cat>/<name>` | `official/research/arxiv` | ★ |
| Skills.sh | Short name | `gws-calendar`, `debugging` | Community |
| Anthropic | `skills-sh/anthropics/skills/<name>` | `skill-creator` | Trusted |
| LobeHub | `lobehub/<name>` | `lobehub/singer` | Community |
| ClawHub | Auto-resolved | `1password`, `arxiv` | Community |
| Direct URL | Raw GitHub URL | See above | Varies |
