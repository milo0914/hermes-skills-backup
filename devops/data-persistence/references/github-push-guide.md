# GitHub Push Guide for Hermes Backup System

## Overview

This guide covers pushing Hermes Agent backup scripts to GitHub for version control and sharing.

## Prerequisites

1. **GitHub Account** - Free account at https://github.com
2. **Personal Access Token** - Required for API access
3. **Git installed** - Usually available in most environments

## Creating Personal Access Token

### Step 1: Navigate to Token Settings
- Go to: https://github.com/settings/tokens/new
- Or: Settings → Developer settings → Personal access tokens → Tokens (classic)

### Step 2: Configure Token
- **Note**: `Hermes Backup System` (or any descriptive name)
- **Expiration**: 90 days recommended (set reminder!)
- **Scopes** (required):
  - ✅ `repo` - Full control of private repositories
  - ✅ `workflow` - Update GitHub Action workflows

### Step 3: Generate and Copy
- Click "Generate token"
- **IMMEDIATELY COPY** the token (format: `ghp_xxxxxxxxxxxx`)
- ⚠️ Token will NOT be shown again!

### Step 4: Set Environment Variable
```bash
export GITHUB_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxx"
```

## Method 1: Automated Push Script (Recommended)

### Quick Push (One Command)
```bash
export GITHUB_TOKEN="ghp_xxx" && \
bash /data/.hermes/bin/push_to_github_final.sh
```

### What the Script Does
1. Checks for GitHub token
2. Validates local Git repository
3. Sets up remote URL with authentication
4. Switches to main branch
5. Pushes all files to GitHub
6. Returns repository URL

### Full Script Location
- Script: `/data/.hermes/bin/push_to_github_final.sh`
- Guide: `/tmp/GITHUB_PUSH_GUIDE.md`

## Method 2: Manual Push

### Step 1: Prepare Local Repository
```bash
cd /tmp/hermes-backup-github
```

### Step 2: Set Remote URL
```bash
export GITHUB_USER="milo0914"
export REPO_NAME="hermes-sessions-backup"
export GITHUB_TOKEN="ghp_xxx"

git remote set-url origin "https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${REPO_NAME}.git"
```

### Step 3: Switch to Main Branch
```bash
git branch -M main
```

### Step 4: Push
```bash
git push -u origin main
```

## Method 3: Using GitHub CLI

### Install GitHub CLI
```bash
# Follow: https://cli.github.com/
```

### Authenticate
```bash
gh auth login
```

### Create Repository
```bash
gh repo create milo0914/hermes-sessions-backup --public
```

### Push
```bash
cd /tmp/hermes-backup-github
git remote add origin https://github.com/milo0914/hermes-sessions-backup.git
git branch -M main
git push -u origin main
```

## Repository Structure

After pushing, your repository should contain:

```
hermes-sessions-backup/
├── backup_sessions.py        # Core backup script (7.9KB)
├── startup_backup.sh         # Startup backup wrapper (700B)
├── install_backup_system.sh  # Installation script (3.0KB)
├── setup_backup_cron.py      # Cron setup script (1.5KB)
├── README.md                 # Documentation (5.4KB)
├── requirements.txt          # Python dependencies
├── .gitignore               # Git ignore rules
├── LICENSE                  # MIT License
└── .env.example             # Environment variables template
```

## Common Issues

### Issue 1: Authentication Failed
**Symptom:** `fatal: Authentication failed`

**Solutions:**
1. Check token is valid (not expired)
2. Verify token has `repo` scope
3. Try regenerating token
4. Check username matches token owner

### Issue 2: Repository Already Exists
**Symptom:** `remote: Repository already exists`

**Solutions:**
1. Use different repository name
2. Delete existing repository on GitHub
3. Push to different branch: `git push -u origin develop`

### Issue 3: Large Files
**Symptom:** Slow push or timeout

**Solutions:**
1. Compress old session files: `gzip session_old.json`
2. Add to `.gitignore`: `*.json` (if sessions are large)
3. Use Git LFS for large files

### Issue 4: Token Security
**Best Practices:**
- Never commit `.env` or token files to Git
- Use `.gitignore` for sensitive files
- Rotate tokens every 90 days
- Use separate tokens for different purposes
- Monitor token usage in GitHub settings

## Post-Push Actions

### 1. Verify Repository
```bash
# Visit repository
https://github.com/milo0914/hermes-sessions-backup
```

### 2. Add Repository Description
- Description: "Hermes Agent session backup system with incremental sync and HuggingFace integration"
- Website: "https://hermes-agent.nousresearch.com/docs"

### 3. Set Branch Protection (Optional)
1. Settings → Branches → Add branch protection rule
2. Branch name pattern: `main`
3. Require pull request reviews before merging

### 4. Add Badges to README
```markdown
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub stars](https://img.shields.io/github/stars/milo0914/hermes-sessions-backup)](https://github.com/milo0914/hermes-sessions-backup)
```

## Automation: Auto-Push on Backup

To automatically push to GitHub after each backup:

```python
# Add to backup_sessions.py after successful backup
def push_to_github_if_configured():
    github_repo = os.environ.get('GITHUB_REPO', '')
    github_token = os.environ.get('GITHUB_TOKEN', '')
    
    if not github_repo or not github_token:
        return  # Skip if not configured
    
    try:
        from git import Repo
        repo = Repo('/tmp/hermes-backup-github')
        repo.git.push('origin', 'main')
        print("Auto-pushed to GitHub")
    except Exception as e:
        print(f"Auto-push failed: {e}")
```

## Security Checklist

- [ ] Token stored in environment variable (not in code)
- [ ] `.env` file in `.gitignore`
- [ ] Token has minimal required scopes
- [ ] Token expiration date set
- [ ] Repository visibility set correctly (public/private)
- [ ] Sensitive data excluded from commits
- [ ] Branch protection enabled (for production)

## Related Files

- `/data/.hermes/bin/push_to_github_final.sh` - Automated push script
- `/data/.hermes/bin/push_to_github_api.py` - Python API-based push
- `/tmp/GITHUB_PUSH_GUIDE.md` - User-facing guide
- `/tmp/hermes-backup-github/` - Local Git repository

## Next Steps

After pushing to GitHub:
1. Share repository URL with team
2. Set up CI/CD for automated testing
3. Add contribution guidelines
4. Monitor issues and pull requests
5. Regular updates and maintenance
