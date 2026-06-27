# Session 2026-05-10: Skill Installation Discoveries

## Summary

This session focused on installing Anthropic's official `skill-creator` and Vercel Labs' `find-skills` skills, revealing important patterns for skill source resolution and installation workflows.

## Key Discoveries

### 1. Anthropic skill-creator Installation

**Issue:** The skill existed in `.hub/anthropics/skills/skill-creator/` but was not loaded in the active skills list.

**Resolution:**
```bash
# Search for the skill
hermes skills search skill-creator

# Install from skills.sh registry
hermes skills install skills-sh/anthropics/skills/skill-creator --force
```

**Security Scan Result:** CAUTION (expected for trusted source)
- HIGH exfiltration: Environment variable handling in eval scripts
- MEDIUM execution: Subprocess calls in eval-viewer
- Decision: ALLOWED (trusted source)

**Files Installed:**
- `SKILL.md` (complete workflow documentation)
- `agents/` directory (grader.md, comparator.md, analyzer.md)
- `scripts/` directory (run_loop.py, run_eval.py, aggregate_benchmark.py, etc.)
- `eval-viewer/` directory (generate_review.py, viewer.html)
- `assets/eval_review.html`
- `references/schemas.md`

### 2. Vercel Labs find-skills Installation

**Pattern:** Direct GitHub URL installation
```bash
hermes skills install https://raw.githubusercontent.com/vercel-labs/skills/c99a72b371b5b4da865f5afa87c5a686f3a46766/skills/find-skills/SKILL.md
```

**Category Prompt:** Installation from URLs prompts for category assignment.

**Resolution Pattern:**
```bash
printf "devops\ny" | hermes skills install <url>
```

**Note:** This overwrote the existing local `find-skills` skill (which was Hermes-specific) with the Vercel Labs version (skills.sh ecosystem focused).

### 3. Skill Resolution Patterns Confirmed

**Working Patterns:**
- ✅ Short names auto-resolve: `gws-calendar`, `debugging`, `skill-creator`
- ✅ Skills.sh registry: `skills-sh/anthropics/skills/skill-creator`
- ✅ Direct raw GitHub URLs (with proper format)

**Failing Patterns:**
- ❌ Full path syntax: `skills-sh/googleworkspace/cli/gws-calendar` (may fail)
- ❌ GitHub tree/blob URLs (must convert to raw)

### 4. Security Scan Patterns

**CAUTION Triggers Observed:**
- Environment variable handling (`os.environ` access)
- Subprocess execution (`subprocess.run`, `subprocess.Popen`)
- Base64 decoding (obfuscation detection)

**Override Pattern:**
```bash
hermes skills install <skill> --force
echo "y" | hermes skills install <skill> --force
```

## Installed Skills Count

After session:
- **26 total skills** enabled
- 19 hub-installed
- 7 local
- 0 disabled

## Workflow Recommendations

### For Anthropic Official Skills
1. Search: `hermes skills search skill-creator`
2. Inspect: `hermes skills inspect skills-sh/anthropics/skills/skill-creator`
3. Install: `hermes skills install skills-sh/anthropics/skills/skill-creator --force`

### For Vercel Labs Skills
1. Get raw URL from GitHub
2. Install with category: `printf "devops\ny" | hermes skills install <url>`
3. Or use skills.sh registry if available

### For Any Skill
1. Always search first: `hermes skills search <query>`
2. Inspect before installing: `hermes skills inspect <identifier>`
3. Use short names when possible (auto-resolution)
4. Use `--force` for trusted sources that trigger CAUTION

## Files Created/Updated

1. **hermes-agent skill updated:**
   - Added Anthropic and Vercel Labs installation patterns
   - Added `references/skill-sources.md` (comprehensive source catalog)
   - Updated references section

2. **New skills installed:**
   - `skill-creator` (Anthropic official)
   - `find-skills` (Vercel Labs - replaced local version)

## Pitfalls to Document

1. **Hub skills not auto-loading:** Skills in `.hub/` directory may not appear in active skills list until explicitly installed via `hermes skills install`

2. **Name collision:** Installing a skill with the same name as an existing local skill will overwrite it. Verify the source before installing.

3. **Category prompts:** URL-based installations always prompt for category. Use `printf` or `echo` to handle non-interactively.

4. **Security scan false positives:** Trusted skills may trigger CAUTION due to generic patterns (env handling, subprocess). Verify source reputation before overriding.
