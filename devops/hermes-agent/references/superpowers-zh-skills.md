# Superpowers-zh Skills Reference

## Overview

**superpowers-zh** is the Chinese community edition of [superpowers](https://github.com/obra/superpowers) — a comprehensive skills framework for AI coding tools with full translation and 6 China-specific skills.

**Source:** https://github.com/jnMetaCode/superpowers-zh  
**Installation:** Clone and copy to `/data/.hermes/skills/superpowers-zh/`  
**Total Skills:** 20 (14 translated + 6 China-original)

## Installation Method

```bash
# Clone the repository
cd /tmp
git clone --depth 1 https://github.com/jnMetaCode/superpowers-zh.git

# Copy skills to Hermes Agent directory
mkdir -p /data/.hermes/skills/superpowers-zh
cp -r /tmp/superpowers-zh/skills/* /data/.hermes/skills/superpowers-zh/

# Verify installation (automatic in Hermes Agent)
hermes skills list | grep superpowers
```

**Note:** Skills auto-enable upon copying to the skill directory. No `hermes skills install` command needed for local copies.

## Installed Skills (20 total)

### Core Skills (2)
| Skill | Description |
|-------|-------------|
| `using-superpowers` | Start every session by establishing how to find and use skills |
| `subagent-driven-development` | Subagent-driven development workflow |

### Process & Methodology (7)
| Skill | Description |
|-------|-------------|
| `brainstorming` | **Must use before any creative work** — explore intent, requirements, design before implementation |
| `writing-plans` | Write implementation plans |
| `executing-plans` | Execute plans with checkpoints |
| `writing-skills` | Create and improve skills |
| `systematic-debugging` | Systematic debugging methodology |
| `test-driven-development` | Test-driven development (TDD) |
| `verification-before-completion` | Verify before claiming completion |

### Code Review & Collaboration (3)
| Skill | Description |
|-------|-------------|
| `requesting-code-review` | Request code review |
| `receiving-code-review` | Receive and implement code review feedback |
| `chinese-code-review` | 🇨🇳 Chinese-style code review (China-original) |

### Git Workflows (3)
| Skill | Description |
|-------|-------------|
| `chinese-git-workflow` | 🇨🇳 Chinese Git workflow (Gitee/Coding/JiHu GitLab/CNB) |
| `chinese-commit-conventions` | 🇨🇳 Conventional Commits Chinese adaptation |
| `using-git-worktrees` | Using Git worktrees |

### Documentation & MCP (3)
| Skill | Description |
|-------|-------------|
| `chinese-documentation` | 🇨🇳 Chinese documentation standards (avoid machine translation) |
| `mcp-builder` | 🇨🇳 MCP server construction (China-original) |
| `workflow-runner` | 🇨🇳 Workflow runner (multi-role YAML orchestration) |

### Other Skills (3)
| Skill | Description |
|-------|-------------|
| `dispatching-parallel-agents` | Dispatch parallel agents |
| `finishing-a-development-branch` | Finish a development branch |
| `using-superpowers` | Using superpowers guide |

## China-Original Skills (6)

These are unique to superpowers-zh and not found in the English upstream:

1. **chinese-code-review** — Code review adapted for Chinese team communication culture
2. **chinese-commit-conventions** — Conventional Commits with Chinese localization
3. **chinese-documentation** — Chinese technical documentation standards
4. **chinese-git-workflow** — Git workflow for Chinese platforms (Gitee, Coding.net, JiHu GitLab, CNB)
5. **mcp-builder** — MCP server construction methodology
6. **workflow-runner** — Multi-role YAML workflow orchestration

## Usage Patterns

### Automatic Triggers
These skills auto-trigger based on context:

| Scenario | Triggered Skill |
|----------|----------------|
| Starting new task/feature | `brainstorming` → `writing-plans` |
| Bug fixing | `systematic-debugging` |
| Code review request | `requesting-code-review` / `chinese-code-review` |
| Writing documentation | `chinese-documentation` |
| Git commit | `chinese-commit-conventions` |
| Using Gitee/Coding | `chinese-git-workflow` |
| Testing required | `test-driven-development` |
| Before completion | `verification-before-completion` |

### Chinese Context Detection
When the following are detected, Chinese-specific skills should be prioritized:

- Chinese comments in code, Chinese README, or `.gitee` directory → Enable Chinese series skills
- Git commit history contains Chinese → Use `chinese-commit-conventions`
- User communicates in Chinese → All output in Chinese, prioritize Chinese skills

**Stacking:** Chinese skills stack with translated skills (not mutually exclusive). Example:
- Code review: Use `requesting-code-review` (process) + `chinese-code-review` (style)

## Key Principles

### Skill Priority Rules
1. **Process skills first** (brainstorming, debugging) — determine HOW to handle task
2. **Implementation skills second** — execute the task

Example: "Let's build X" → brainstorming first, then implementation skill

### Red Lines (from using-superpowers)
- **Must call skill before any response** (including clarification questions)
- **1% rule:** If there's even 1% chance a skill applies, call it
- **No rationalization:** Don't skip skills by claiming "this is simple" or "I already know"

### User Instruction Priority
1. **User's explicit instructions** (CLAUDE.md, GEMINI.md, AGENTS.md, direct requests) — HIGHEST
2. **Superpowers skills** — override default system behavior where they conflict
3. **Default system prompts** — LOWEST

## Supported Tools (17 total)

superpowers-zh supports installation via `npx superpowers-zh` for:
- Claude Code, Copilot CLI, Hermes Agent, Cursor, Windsurf, Kiro
- Gemini CLI, Codex, Aider, Trae, VS Code (Copilot)
- DeerFlow, OpenCode, OpenClaw, Qwen Code, Antigravity, Claw Code

## References

- **Upstream (English):** https://github.com/obra/superpowers (159k+ stars)
- **Chinese Edition:** https://github.com/jnMetaCode/superpowers-zh
- **Skills.sh:** https://skills.sh/ (skill discovery platform)
