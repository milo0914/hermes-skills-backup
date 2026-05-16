# GitHub URL Installation Guide

## Converting GitHub URLs for Skill Installation

GitHub tree/blob URLs **do not work directly** with `hermes skills install`. You must convert them to raw file URLs.

### URL Conversion Pattern

**❌ Wrong - Tree/Blob URLs (don't work):**
```
https://github.com/user/repo/tree/branch/path/to/skill
https://github.com/user/repo/blob/branch/path/to/skill/SKILL.md
```

**✅ Correct - Raw URL (works):**
```
https://raw.githubusercontent.com/user/repo/branch/path/to/skill/SKILL.md
```

### Examples from Session 2026-05-02

| Original GitHub URL | Converted Raw URL | Status |
|---------------------|-------------------|---------|
| `https://github.com/NousResearch/hermes-agent/tree/af981227937f54ccd621673f1e86ee196134a005/skills/creative/claude-design` | `https://raw.githubusercontent.com/NousResearch/hermes-agent/af981227937f54ccd621673f1e86ee196134a005/skills/creative/claude-design/SKILL.md` | ✅ Installed |
| `https://github.com/NousResearch/hermes-agent/tree/e444d8f29cead99781cbd4306160b81887b3f4e5/skills/creative/songwriting-and-ai-music` | `https://raw.githubusercontent.com/NousResearch/hermes-agent/e444d8f29cead99781cbd4306160b81887b3f4e5/skills/creative/songwriting-and-ai-music/SKILL.md` | ✅ Installed |
| `https://github.com/amanning3390/hermeshub/tree/55e6fb944dbbb73212d01f6db89e3af016b7c42e/skills/web-researcher` | `https://raw.githubusercontent.com/amanning3390/hermeshub/55e6fb944dbbb73212d01f6db89e3af016b7c42e/skills/web-researcher/SKILL.md` | ✅ Installed |

### Installation Command Pattern

For skills from GitHub URLs that prompt for category:

```bash
# Pattern
printf "<category>\ny" | hermes skills install <raw-url>

# Examples
printf "creative\ny" | hermes skills install https://raw.githubusercontent.com/NousResearch/hermes-agent/main/skills/creative/claude-design/SKILL.md
printf "creative\ny" | hermes skills install https://raw.githubusercontent.com/NousResearch/hermes-agent/main/skills/creative/songwriting-and-ai-music/SKILL.md
printf "devops\ny" | hermes skills install https://raw.githubusercontent.com/NousResearch/hermes-agent/main/skills/software-development/systematic-debugging/SKILL.md
```

### Available Categories

Common categories used in Hermes skills:
- `creative` - Design, art, music, songwriting
- `devops` - Development operations, debugging, systematic processes
- `research` - Academic, search, analysis
- `productivity` - Tools for getting things done
- `software-development` - Coding, debugging, testing

### Quick Reference: Official Nous Research Skills

These official skills are available via direct URL installation:

**Creative:**
- `claude-design` - HTML artifact design (landing pages, decks, prototypes)
- `songwriting-and-ai-music` - Songwriting craft and Suno AI integration

**Software Development:**
- `systematic-debugging` - Four-phase root cause debugging methodology

**Installation:**
```bash
printf "creative\ny" | hermes skills install https://raw.githubusercontent.com/NousResearch/hermes-agent/refs/heads/main/skills/creative/claude-design/SKILL.md
printf "creative\ny" | hermes skills install https://raw.githubusercontent.com/NousResearch/hermes-agent/refs/heads/main/skills/creative/songwriting-and-ai-music/SKILL.md
printf "devops\ny" | hermes skills install https://raw.githubusercontent.com/NousResearch/hermes-agent/refs/heads/main/skills/software-development/systematic-debugging/SKILL.md
```

**Note:** These same skills may also be available via shorter identifiers. Always search first:
```bash
hermes skills search claude-design
hermes skills search songwriting
hermes skills search systematic-debugging
```
