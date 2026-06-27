# Cron Self-Heal v5 Fix — 2026-06-10

## 故障現象

Cron job `6527076f63be` (session-backup) 執行失敗：
```
SELF-HEAL: Script not found at /data/.hermes/skills/devops/robust-db-persistence/scripts/backup_sessions.py
SELF-HEAL: Restoring skills from GitHub…
SELF-HEAL: Skills restored from GitHub
ERROR: Script still not found at …/backup_sessions.py after self-heal
```

自癒邏輯報告「Skills restored from GitHub」但實際上並未恢復缺失的 skill。

## 根因：heal_skills_from_github() category-level 粒度缺陷

v4 的 `heal_skills_from_github()` 採用 category-level 檢查：

```python
for category in os.listdir(clone_dir):
    cat_dst = os.path.join(SKILLS_DIR, category)
    if not os.path.exists(cat_dst):         # ← 只檢查 category 目錄
        shutil.copytree(cat_src, cat_dst)    # ← 整個 category 缺失才複製
    # 若 cat_dst 已存在 → 完全跳過！
```

**問題**：HF Space 重建後，`devops/` 目錄可能因其他 skill（如 `github-skills-backup`、`hermes-cli-to-webui-sync`）已透過其他 cron 恢復而不為空，但 `robust-db-persistence` 這個子目錄仍然缺失。v4 邏輯看到 `devops/` 存在就跳過 → `robust-db-persistence` 永遠不會被恢復。

## 修正：v5 skill-level 粒度

```python
for category in os.listdir(clone_dir):
    cat_src = os.path.join(clone_dir, category)
    cat_dst = os.path.join(SKILLS_DIR, category)

    if not os.path.exists(cat_dst):
        # 整個 category 缺失 → 全複製
        shutil.copytree(cat_src, cat_dst)
    else:
        # category 存在 → 逐 skill 檢查
        for skill_name in os.listdir(cat_src):
            skill_src = os.path.join(cat_src, skill_name)
            skill_dst = os.path.join(cat_dst, skill_name)
            if os.path.isdir(skill_src) and not os.path.exists(skill_dst):
                shutil.copytree(skill_src, skill_dst)
```

## 影響範圍

所有 4 個 cron wrapper 的 `heal_skills_from_github()` 均需同步更新：
1. `cron-backup-sessions.py` — robust-db-persistence
2. `cron-restore-from-hf.py` — robust-db-persistence
3. `cron-sync-sessions.py` — hermes-cli-to-webui-sync
4. `cron-skills-backup.sh` — github-skills-backup

## 驗證步驟

1. 部署修正後的 wrapper 到 `/data/.hermes/scripts/`
2. `cronjob(action='run', job_id='6527076f63be')` — 確認 exit code 0
3. `cronjob(action='run', job_id='33001a64cdf4')` — 確認其他 cron 也正常
4. 執行 GitHub skills backup 推送持久化
