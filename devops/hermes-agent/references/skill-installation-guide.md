# Skill Installation Reference

## Common Skill Identifiers by Category

### Google Workspace (skills.sh source)
All auto-resolve from short names. Install with: `hermes skills install <short-name>`

| Short Name | Full Path | Function |
|------------|-----------|----------|
| `gws-gmail` | `skills-sh/googleworkspace/cli/gws-gmail` | Gmail management |
| `gws-drive` | `skills-sh/googleworkspace/cli/gws-drive` | Google Drive file management |
| `gws-docs` | `skills-sh/googleworkspace/cli/gws-docs` | Google Docs editing |
| `gws-sheets` | `skills-sh/googleworkspace/cli/gws-sheets` | Google Sheets spreadsheets |
| `gws-calendar` | `skills-sh/googleworkspace/cli/gws-calendar` | Calendar events management |

### Music Creation (LobeHub source)
| Skill | Install Command | Function |
|-------|-----------------|------------|
| `singer` | `hermes skills install lobehub/singer` | AI singer/songwriter assistant |
| `suno` | `hermes skills install lobehub/suno --force` | Suno AI lyrics assistant (requires --force) |

### Research & Academia
| Skill | Install Command | Function |
|-------|-----------------|------------|
| `arxiv` | `hermes skills install arxiv` | arXiv paper search/download |
| `scrapling` | `hermes skills install scrapling --force` | Web scraping with anti-bot bypass |
| `debugging` | `hermes skills install debugging` | Turso database debugging |

### Web Scraping
| Skill | Install Command | Function | Notes |
|-------|-----------------|------------|-------|
| `scrapling` | `hermes skills install scrapling --force` | HTTP fetching, stealth browser, anti-bot bypass | Requires `--force` (supply chain warnings) |
| `web-researcher` | `hermes skills install web-researcher` | Web research assistant | From GitHub URL |

### Productivity
| Skill | Install Command | Function |
|-------|-----------------|------------|
| `powerpoint` | `hermes skills install powerpoint` | PowerPoint presentation control |
| `1password` | `hermes skills install 1password` | 1Password CLI integration |

### Development Tools
| Skill | Install Command | Function |
|-------|-----------------|------------|
| `felo-search` | `hermes skills install felo/felo-search --force` | Felo AI web search |
| `systematic-debugging` | `hermes skills install systematic-debugging` | Systematic debugging methodology |

### Creative & Design (Nous Research Official)
| Skill | Install Command | Function |
|-------|-----------------|------------|
| `claude-design` | Direct URL install | HTML artifact design (landing pages, prototypes) |
| `songwriting-and-ai-music` | Direct URL install | Songwriting craft and Suno AI music prompts |

## Security Override Patterns

Skills requiring `--force` flag (community source + CAUTION verdict):

**Common security findings:**
- `privilege_escalation`: Uses `sudo apt install` or system package managers
- `persistence`: Adds exports to `~/.bashrc` or shell profiles
- `exfiltration`: Handles API keys or makes external API calls
- `supply_chain`: Downloads scripts via curl/wget

**Override command:**
```bash
hermes skills install <skill-path> --force
```

## Installation Workflow

1. **Search first** (finds correct identifier):
   ```bash
   hermes skills search <query>
   ```

2. **Inspect** (preview before installing):
   ```bash
   hermes skills inspect <identifier>
   ```

3. **Install** (with force if needed):
   ```bash
   hermes skills install <identifier> [--force]
   ```

4. **Verify**:
   ```bash
   hermes skills list
   ```

## Common Skill Sources

| Source | Pattern | Trust Level | Example |
|--------|---------|-------------|---------|
| Official | `official/<cat>/<name>` | ★ official | `official/research/arxiv` |
| Skills.sh | Auto-resolved short name | community | `gws-calendar` |
| LobeHub | `lobehub/<name>` | community | `lobehub/singer` |
| ClawHub | Auto-resolved | community | `1password` |
| Direct URL | `https://.../SKILL.md` | varies | Any valid URL |

## Session-Specific Install Summary

### Session 2026-05-02: Bulk Skill Installation

This reference was updated based on a session where the following skills were successfully installed:

**Google Workspace Suite (5 skills):**
- `gws-gmail` - Gmail management
- `gws-drive` - Google Drive file management 
- `gws-calendar` - Google Calendar management
- `gws-docs` - Google Docs editing
- `gws-sheets` - Google Sheets spreadsheets

**Music Creation (2 skills):**
- `singer` - AI singer/songwriter assistant (LobeHub)
- `suno` - Suno AI lyrics assistant (LobeHub, requires --force)

**Research & Web (3 skills):**
- `arxiv` - arXiv paper search/download
- `scrapling` - Web scraping with anti-bot bypass (requires --force, 12 security findings)
- `web-researcher` - Web research assistant (from GitHub URL)

**Productivity & Tools (3 skills):**
- `powerpoint` - PowerPoint presentation control
- `1password` - 1Password CLI integration
- `felo-search` - Felo AI web search (requires --force)

**Creative & Design (2 skills - Nous Research Official):**
- `claude-design` - HTML artifact design (from GitHub URL)
- `songwriting-and-ai-music` - Songwriting and Suno AI integration (from GitHub URL)

**Development Tools (2 skills):**
- `systematic-debugging` - Systematic debugging methodology (from GitHub URL)
- `debugging` - Turso database debugging (skills.sh)

**Total installed in session:** 19 skills (15 hub-installed, 4 local)

**Key discoveries:**
1. GitHub tree/blob URLs must be converted to raw.githubusercontent.com format
2. Category prompts can be automated with `printf "category\ny"`
3. Security scan findings vary widely: `scrapling` (12), `suno` (3), `felo-search` (3)
4. Short names auto-resolve for skills.sh registry (e.g., `gws-calendar`, `debugging`)
- GitHub URLs don't work directly - use the registry name instead
- **GitHub URL conversion needed**: Convert `github.com/.../tree/...` to `raw.githubusercontent.com/...`

**"Installation blocked: CAUTION verdict"**
- Security scan found concerning patterns
- Review findings and use `--force` if you trust the source
- Example: `hermes skills install felo/felo-search --force`
- Common for skills that: install Python packages, use pip, call external APIs
- Session 2026-05-02 discoveries: `scrapling` (12 findings), `suno` (3 findings), `felo-search` (3 findings)

**"Confirm [y/N]:" prompt keeps appearing**
- Use `echo "y" | hermes skills install <skill>` to bypass
- Or use `--force` flag which sometimes skips confirmation
- Combined: `echo "y" | hermes skills install <skill> --force`
- For URL installs with category prompt: `printf "category\ny" | hermes skills install <url>`

**GitHub URL installation fails**
- GitHub URLs like `https://github.com/.../tree/...` don't work directly
- Convert to raw URL: `https://raw.githubusercontent.com/user/repo/branch/path/SKILL.md`
- Or better: search for the skill name in the registry
- Example: GitHub URL for scrapling → use `hermes skills install scrapling`

**Skill installs but shows different name**
- Some skills install with a different name than expected
- Check `hermes skills list` to see the actual installed name
- Use that name for the slash command: `/<installed-name>`

**Category prompt during URL installation**
- When installing from URLs, you'll be prompted to pick a category
- Press Enter to install "flat" (no category)
- Or type an existing category name (e.g., `devops`, `research`, `creative`)
- Or type a new category name to create it
- Use `printf "<category>\ny"` to automate this

**"Confirm [y/N]:" prompt**
- Interactive confirmation required for third-party skills
- Use `echo "y" | hermes skills install <skill>` for non-interactive installation
- For skills requiring both category and confirmation: `printf "creative\ny" | hermes skills install <url>`
