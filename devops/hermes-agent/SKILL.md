---
name: hermes-agent
description: Configure, extend, or contribute to Hermes Agent itself
category: devops
---

# hermes-agent

Skill for configuring, extending, and managing Hermes Agent - its CLI, config, models, providers, tools, skills, voice, gateway, plugins, or any feature.

## When to Load

Load this skill whenever the user asks to:
- Configure or modify Hermes Agent settings
- Install, update, or manage skills
- Set up providers or models
- Troubleshoot Hermes Agent behavior
- Understand Hermes Agent commands or workflows
- Manage profiles, sessions, or the gateway

## Key Commands

### Skills Management
```bash
# Browse and search skills
hermes skills browse                    # Browse available skills
hermes skills browse --source official  # Browse official registry
hermes skills search <query>            # Search for skills
hermes skills inspect <skill-path>      # Preview before installing

# Install skills (the correct way - do NOT create manually)
hermes skills install official/<category>/<skill-name>
hermes skills install skills-sh/<path>  # From skills.sh registry
hermes skills install <url>             # Direct URL to SKILL.md
hermes skills install <url> --name <x>  # When frontmatter has no name

# Manage installed skills
hermes skills list                      # List installed skills
hermes skills update                    # Update hub-installed skills
hermes skills uninstall <skill>         # Remove a skill
hermes skills check                     # Check for updates
```

### Configuration
```bash
hermes config                           # Show/edit configuration
hermes setup                            # Interactive setup wizard
hermes model                            # Configure default model/provider
hermes auth                             # Manage API credentials
hermes doctor                           # Diagnose issues
hermes dump                             # Copy-pasteable setup summary
```

### Sessions and Profiles
```bash
hermes chat                             # Interactive chat
hermes chat -q "<prompt>"               # Single query mode
hermes chat -s skill1,skill2            # Preload skills
hermes --continue                       # Resume last session
hermes --resume <session-id>            # Resume specific session
hermes sessions                         # Browse/manage sessions
```

## Critical Pitfalls

### Installing Official Skills
**DO NOT** try to create official skills manually with `skill_manage(action='create')`. Official skills must be installed via:
```bash
hermes skills install official/<category>/<skill-name>
```

The manual creation approach fails because:
1. Official skills may have dependencies or registry metadata
2. The skill format requires specific YAML frontmatter that's hard to guess
3. The installation command handles validation and proper placement

**Correct workflow:**
1. User requests a skill (e.g., "install arxiv skill")
2. Try: `hermes skills install official/<category>/<skill>`
3. If not found, search: `hermes skills search <query>` to find the correct identifier
4. Skills may exist under different names or sources than expected (e.g., `gws-calendar` instead of `google-workspace`)
### Skill Installation Patterns Discovered

**Auto-resolution works best:** Skills from `skills.sh` registry can be installed using short names:
- `gws-calendar` → resolves to `skills-sh/googleworkspace/cli/gws-calendar`
- `gws-gmail` → resolves to `skills-sh/googleworkspace/cli/gws-gmail`
- `gws-docs` → resolves to `skills-sh/googleworkspace/cli/gws-docs`
- `gws-sheets` → resolves to `skills-sh/googleworkspace/cli/gws-sheets`
- `gws-drive` → resolves to `skills-sh/googleworkspace/cli/gws-drive`
- `scrapling` → resolves to `official/research/scrapling`
- `debugging` → resolves to `skills-sh/tursodatabase/turso/debugging`

**Full path syntax may fail:** Using `skills/productivity/google-workspace` or `skills-sh/googleworkspace/gws-docs` often fails. Use the short name or search first.

**Search before installing:** When a skill name doesn't work:
```bash
hermes skills search <query> # Shows correct identifiers
hermes skills inspect <id> # Preview before installing
hermes skills install <short-name> # Try short name first
hermes skills install <short-name> --force # Add --force if blocked
echo "y" | hermes skills install <short-name> --force # Also bypass confirmation
```

**Anthropic official skills:** Available via `skills-sh/anthropics/skills/<skill-name>` pattern:
- `skill-creator` → Full skill creation workflow with evals, benchmarking, and description optimization
- Install: `hermes skills install skills-sh/anthropics/skills/skill-creator --force`
- Note: May show CAUTION verdict due to env var handling in eval scripts; safe to override for this trusted source
- Hub location: `/data/.hermes/skills/.hub/anthropics/skills/skill-creator/` (pre-installed in some environments)

**Vercel Labs skills:** Available via direct GitHub URL:
- `find-skills` → Skills.sh ecosystem discovery and installation guidance
- Install: `hermes skills install https://raw.githubusercontent.com/vercel-labs/skills/<commit>/skills/find-skills/SKILL.md`
- Requires category prompt during installation (use `printf "devops\\ny" | ...` pattern)

**superpowers-zh (Chinese community edition):** 20 skills for AI coding workflows:
- Source: https://github.com/jnMetaCode/superpowers-zh
- Installation: Clone repo and copy skills to `/data/.hermes/skills/superpowers-zh/`
- Skills include: `brainstorming`, `using-superpowers`, `chinese-code-review`, `mcp-builder`, `workflow-runner`, etc.
- All 20 skills auto-enable upon copying to skill directory
- See `references/superpowers-zh-skills.md` for full list and usage patterns

### Skill Name Format and Resolution

**Official skills:** `official/<category>/<skill-name>`

**Skills.sh registry:** Use the short name which auto-resolves:
```bash
hermes skills install gws-calendar # Auto-resolves to skills-sh/googleworkspace/cli/gws-calendar
hermes skills install gws-gmail # Auto-resolves to skills-sh/googleworkspace/cli/gws-gmail
hermes skills install gws-docs # Auto-resolves to skills-sh/googleworkspace/cli/gws-docs
hermes skills install gws-sheets # Auto-resolves to skills-sh/googleworkspace/cli/gws-sheets
hermes skills install gws-drive # Auto-resolves to skills-sh/googleworkspace/cli/gws-drive
hermes skills install debugging # Auto-resolves to skills-sh/tursodatabase/turso/debugging
```

**LobeHub registry:** `lobehub/<skill-name>` (e.g., `lobehub/singer`, `lobehub/suno`)

**Direct URLs:** Work if they point to valid SKILL.md files, but require raw GitHub URLs:
```bash
# Use raw.githubusercontent.com, not github.com tree/blob URLs
hermes skills install https://raw.githubusercontent.com/NousResearch/hermes-agent/refs/heads/main/skills/creative/claude-design/SKILL.md
hermes skills install https://raw.githubusercontent.com/NousResearch/hermes-agent/refs/heads/main/skills/creative/songwriting-and-ai-music/SKILL.md
hermes skills install https://raw.githubusercontent.com/NousResearch/hermes-agent/refs/heads/main/skills/software-development/systematic-debugging/SKILL.md
```

**Pro tip:** When in doubt, search first: `hermes skills search <query>` shows the correct identifier to use.

### Batch Installation Pattern

For installing multiple skills efficiently:

```bash
# Use printf to handle interactive prompts non-interactively
printf "<category>\ny" | hermes skills install <url>
# Example:
printf "creative\ny" | hermes skills install https://raw.githubusercontent.com/.../SKILL.md

# Or for skills that don't prompt for category:
echo "y" | hermes skills install <skill> --force
```

### Installing from GitHub URLs

**Pattern discovered:** GitHub tree/blob URLs don't work directly. Convert to raw URL:
- ❌ `https://github.com/user/repo/tree/branch/path/to/skill`
- ✅ `https://raw.githubusercontent.com/user/repo/branch/path/to/skill/SKILL.md`

**Example conversions:**
```bash
# Wrong - tree URL won't work
hermes skills install https://github.com/NousResearch/hermes-agent/tree/main/skills/creative/claude-design

# Correct - use raw URL
hermes skills install https://raw.githubusercontent.com/NousResearch/hermes-agent/main/skills/creative/claude-design/SKILL.md
```

**Category prompt handling:** When installing from URLs, you'll be prompted for a category. Use `printf` to provide it:
```bash
printf "creative\ny" | hermes skills install <url>  # For creative skills
printf "devops\ny" | hermes skills install <url>    # For devops skills
printf "research\ny" | hermes skills install <url>  # For research skills
```

### Security Scanning and Overrides

Skills from community sources undergo automatic security scanning. Common findings:

**CAUTION verdict (requires --force):**
- **HIGH privilege_escalation**: Scripts using `sudo` or system package installation
- **MEDIUM persistence**: Adding to `~/.bashrc`, `~/.zshrc`, or shell profiles
- **HIGH exfiltration**: API key handling, external API calls to third-party services
- **MEDIUM supply_chain**: curl/wget downloading from external URLs, `pip install` commands

**Typical patterns that trigger CAUTION:**
- `pip install <package>` - Python package installation (supply chain risk)
- `python3 -m pip install` - Explicit pip invocation
- External API calls to services like `api.aimusicapi.ai`
- Browser automation with headless Chrome/Firefox
- `curl "https://..."` - Downloading external scripts or data

**Override when you trust the source:**
```bash
hermes skills install <skill> --force # Override security warnings
echo "y" | hermes skills install <skill> --force # Also bypass confirmation prompt
printf "category\ny" | hermes skills install <url> --force # For URL installs with category prompt
```

**Session discoveries (2026-05-02):**
- `scrapling` - 12 findings (supply chain: pip install, curl)
- `suno` - 3 findings (exfiltration: API key handling)
- `felo-search` - 3 findings (privilege escalation: sudo, persistence: bashrc)
- `web-researcher` - SAFE (no override needed)
- `songwriting-and-ai-music` - SAFE (official Nous skill)
- `claude-design` - SAFE (official Nous skill)
- `systematic-debugging` - SAFE (official Nous skill)
- `debugging` (Turso) - 1 finding (supply chain: curl to external API)
```

**Installed skill locations:** `/data/.hermes/skills/<skill-name>/` (or `~/.hermes/skills/` on local systems)

### Common Skill Sources

| Source | Pattern | Example | Trust Level |
|--------|---------|---------|-------------|
| Official | `official/<cat>/<name>` | `official/research/arxiv` | ★ official |
| Skills.sh | Auto-resolved short name | `gws-calendar` | community |
| LobeHub | `lobehub/<name>` | `lobehub/singer` | community |
| ClawHub | Auto-resolved | `1password` | community |
| Direct URL | `https://.../SKILL.md` | Any URL | varies |

### SKILL.md Format Requirements
Skills must start with YAML frontmatter:
```yaml
---
name: skill-name
description: Brief description
category: category-name
---
```

Without proper frontmatter, skill creation fails with: "SKILL.md must start with YAML frontmatter (---)"

### Verification Steps

After installing a skill:
1. Run `hermes skills list` to confirm installation
2. Check the skill is enabled
3. Test the skill's slash command: `/<skill-name> help`

### User Language Preferences

When user communicates in Chinese (or other non-English languages):
- Match the user's language in your responses
- Provide concise installation confirmations with clear status tables
- Use emoji indicators (✅ ❌ ✨ 🎉) for visual clarity
- Present skill lists in tabular format with source and status columns

Example response pattern for Chinese users:
```
✅ 已成功安裝 `powerpoint` 技能！
目前技能總數：9 個
```

## References

- Documentation: https://hermes-agent.nousresearch.com/docs/skills
- Skills Hub: https://agentskills.io (670+ skills across 4 registries)
- CLI Reference: https://hermes-agent.nousresearch.com/docs/reference/cli-commands
- Skill Sources: See `references/skill-sources.md` for detailed source patterns
- Session Analysis: See `hermes-session-analysis` skill for session persistence debugging
- Data Persistence: See `data-persistence` skill for backup/recovery strategies