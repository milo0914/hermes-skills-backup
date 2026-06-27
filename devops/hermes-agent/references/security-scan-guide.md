# Security Scan Override Guide

## Understanding Security Verdicts

Hermes Agent automatically scans all community skills before installation. Here's what the verdicts mean:

### SAFE → Auto-approved
No concerning patterns found. Installation proceeds with standard confirmation.

### CAUTION → Requires `--force`
The skill contains patterns that could be risky but are often legitimate:

| Finding Type | Severity | What it means | Example triggers |
|-------------|----------|---------------|------------------|
| `privilege_escalation` | HIGH | Script runs system commands | `sudo apt install`, `curl \| bash` |
| `persistence` | MEDIUM | Modifies shell profiles | `echo 'export...' >> ~/.bashrc` |
| `exfiltration` | HIGH | Sends data externally | API calls with API keys, `curl` to external URLs |
| `supply_chain` | MEDIUM | Downloads/installs packages | `pip install`, `npm install`, `wget` scripts |

### BLOCKED → Cannot override
Critical security issues. Do not attempt to install unless you can modify the skill.

## Override Patterns

### Basic Override
```bash
hermes skills install <skill-name> --force
```

### Override + Skip Confirmation
For non-interactive installation:
```bash
echo "y" | hermes skills install <skill-name> --force
```

### When to Override

**Safe to override when:**
- ✅ You trust the source (official registries, well-known projects)
- ✅ The skill is from `skills.sh`, `lobehub`, or `official/` sources
- ✅ The findings match expected behavior (e.g., `pip install` for a Python tool)
- ✅ You've reviewed the skill code and understand what it does

**Do NOT override when:**
- ❌ Unknown source with no documentation
- ❌ Skill requests sensitive data without clear purpose
- ❌ Findings don't match the skill's stated purpose
- ❌ You're unsure what the skill does

## Common Skills Requiring Override

Based on installation history:

| Skill | Findings | Safe to Override? | Reason |
|-------|----------|-------------------|--------|
| `felo-search` | privilege_escalation, persistence | ✅ Yes | Installs CLI tools, adds env vars |
| `suno` | exfiltration, supply_chain | ✅ Yes | Calls Suno AI API (expected) |
| `scrapling` | supply_chain (multiple) | ✅ Yes | Installs Python packages for scraping |
| `powerpoint` | None (SAFE) | N/A | No override needed |
| `gws-*` | None (SAFE) | N/A | No override needed |

## Security Scan Process

1. **Quarantine**: Skill files are placed in `.hub/quarantine/<skill-name>/`
2. **Scan**: Automated analysis checks for concerning patterns
3. **Verdict**: SAFE, CAUTION, or BLOCKED
4. **Decision**: 
   - SAFE → Allowed, proceeds to confirmation
   - CAUTION → Blocked unless `--force` used
   - BLOCKED → Cannot proceed

## Best Practices

### Before Installing
1. Search for the skill: `hermes skills search <query>`
2. Inspect the skill: `hermes skills inspect <identifier>`
3. Check the source reputation (official, skills.sh, lobehub, etc.)
4. Review the findings if CAUTION verdict

### During Installation
```bash
# Safe pattern for known skills
hermes skills install scrapling --force

# For unknown skills, inspect first
hermes skills inspect scrapling
hermes skills install scrapling --force  # After review
```

### After Installation
1. Verify installation: `hermes skills list`
2. Check skill location: `/data/.hermes/skills/<skill-name>/`
3. Test the skill's functionality
4. Monitor for unexpected behavior

## Understanding Specific Findings

### supply_chain
**What it means:** The skill installs or downloads external packages

**Common triggers:**
- `pip install <package>`
- `npm install <package>`
- `curl https://... \| bash`
- `wget https://...`

**Why it's flagged:** Downloaded packages could contain malicious code

**When safe:** Installing from official package repositories (PyPI, npm) for well-known packages

### exfiltration  
**What it means:** The skill sends data to external services

**Common triggers:**
- API calls with authentication
- `curl` or `requests` to external URLs
- Skills that interact with AI services (Suno, OpenAI, etc.)

**Why it's flagged:** Could leak sensitive data or API keys

**When safe:** When the skill's purpose is to interact with that specific service

### privilege_escalation
**What it means:** The skill runs commands with elevated privileges

**Common triggers:**
- `sudo <command>`
- System package installation
- Modifying system files

**Why it's flagged:** Could compromise system security

**When safe:** Installing CLI tools that legitimately need system access

### persistence
**What it means:** The skill modifies startup files or environment

**Common triggers:**
- `echo '...' >> ~/.bashrc`
- `echo '...' >> ~/.zshrc`
- Modifying `/etc/...`

**Why it's flagged:** Could persist malicious code

**When safe:** Setting up environment variables for tools you'll use regularly

## Quick Reference

```bash
# Check if skill needs override
hermes skills inspect <skill-name>

# Install with override
hermes skills install <skill-name> --force

# Install with override + no prompts
echo "y" | hermes skills install <skill-name> --force

# Verify installation
hermes skills list

# If something goes wrong, uninstall
hermes skills uninstall <skill-name>
```

## Reporting Issues

If a skill behaves unexpectedly after installation:
1. Uninstall the skill: `hermes skills uninstall <skill-name>`
2. Check logs: `hermes logs`
3. Report to the skill's source repository
4. Notify via `hermes doctor` for diagnostics
