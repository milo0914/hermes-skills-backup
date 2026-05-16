---
name: github-skills-backup
description: Backup and restore Hermes Agent skills to and from GitHub repository
version: 1.0.0
tags: [backup, github, skills, devops, automation]
---

# GitHub Skills Backup Skill

## Purpose
Automatically backup all Hermes Agent skills to a GitHub repository and restore them when needed.

## Prerequisites
- GitHub account with a Personal Access Token (repo scope)
- Git installed in the environment
- GITHUB_TOKEN available via HuggingFace Spaces Secrets or environment variable

## Usage

### Backup Skills to GitHub

```bash
bash /tmp/github-skills-backup.sh
```

Or load this skill and say: "Backup all skills to GitHub"

### Restore Skills from GitHub

```bash
# Clone the backup repository
git clone https://github.com/milo0914/hermes-skills-backup.git /tmp/hermes-skills-backup

# Copy skills to Hermes Agent directory
cp -r /tmp/hermes-skills-backup/* /data/.hermes/skills/
```

## Script Location
- Main script: `/tmp/github-skills-backup.sh`
- This skill directory: `/data/.hermes/skills/devops/github-skills-backup/`

## Features
- Automatic GITHUB_TOKEN detection from environment/secrets
- Auto-create repository if not exists
- Smart exclusion of special directories (.hub, .archive, .curator_backups)
- Auto-generate README.md with skill list
- Full git workflow: init, commit, push

## Environment Variables
- `GITHUB_TOKEN`: GitHub Personal Access Token (required)
- `GITHUB_USER`: GitHub username (default: milo0914)
- `GITHUB_REPO`: Repository name (default: hermes-skills-backup)

## Related Skills
- skills-creator: For creating and managing skills
- hermes-agent: For Hermes Agent configuration
