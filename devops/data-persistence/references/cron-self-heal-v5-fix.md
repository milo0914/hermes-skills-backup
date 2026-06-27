# Cron Self-Heal v5 Fix — 2026-06-16, updated 2026-06-25

## 故障現象

Cron job `6527076f63be` (session-backup) 失敗，錯誤：
```
Script not found: /data/.hermes/scripts/backup-sessions.py
```

HF Space 重建清除 `/data/.hermes/scripts/`，cron 因找不到腳本而失效。

## 根因（v4 → v5 修正）

v4 `heal_skills_from_github()` 只檢查 category 目錄（如 `devops/`），若目錄已存在就跳過，不會恢復缺失的個別 skill（如 `robust-db-persistence`）。

## 修正（v5 skill-level 粒度）

已在以下 cron wrapper 中部署修正：
- `/data/.hermes/scripts/backup-sessions.py` (session-backup)
- `/data/.hermes/scripts/cron-sync-sessions.py` (sync-hermes-sessions-to-webui)
- `/data/.hermes/scripts/restore-from-hf.py` (restore-sessions-from-hf)
- `/data/.hermes/scripts/cron-skills-backup.sh` (Backup Hermes Skills to GitHub)

**關鍵修正邏輯**：
```python
# v4: category-level only
if not os.path.exists(cat_dst):
    shutil.copytree(cat_src, cat_dst)
# else: skip entirely

# v5: skill-level granularity
if not os.path.exists(cat_dst):
    shutil.copytree(cat_src, cat_dst)
else:
    for skill_name in os.listdir(cat_src):
        skill_src = os.path.join(cat_src, skill_name)
        skill_dst = os.path.join(cat_dst, skill_name)
        if os.path.isdir(skill_src) and not os.path.exists(skill_dst):
            shutil.copytree(skill_src, skill_dst)
```

## 冷啟動盲區（2026-06-25 發現）

v5 自癒邏輯存在 bootstrapping dependency：自癒代碼寫在 scripts/ 中的 wrapper 內，但 wrapper 本身需要先存在才能被 cron 觸發執行。當 HF Space 重建後 scripts/ **完全為空**時，沒有任何 cron 能觸發，自癒機制陷入死鎖。

**實測紀錄（2026-06-25）**：HF Space 重建後 3 個 cron 全部 error（session-backup、sync-sessions、restore-from-hf），scripts/ 目錄為空。skills/ 目錄（持久層）完好，但自癒無法啟動。

**手動修復步驟**：
1. `ls /data/.hermes/scripts/ | wc -l` — 確認為 0（全量丟失）
2. 從 skills/ 複製 7 個 wrapper 到 scripts/（見 data-persistence SKILL.md Pitfall #5 的完整指令）
3. `chmod 755 /data/.hermes/scripts/*`
4. 逐一觸發失敗的 cron：`cronjob(action='run', job_id='<id>')`
5. 等待 60s 確認 last_status 轉為 ok
6. 若遇 lock file（backup-sessions.lock），等待其自動過期或手動清除

**結論**：v5 自癒適用於「部分 wrapper 缺失」場景；「全量缺失」仍需外部 agent 手動干預。修復後首個 cron 觸發即可恢復 ALL_CRON_SCRIPTS 清單中所有 wrapper。

## 驗證步驟

1. 手動觸發 session-backup cron：
   ```bash
   cronjob(action='run', job_id='6527076f63be')
   ```
2. 確認 `last_status: ok`
3. 確認 `/data/.hermes/scripts/` 包含所有 7 個 wrapper
4. 執行 GitHub skills backup 推送持久化

## 關鍵文件

- Wrapper: `/data/.hermes/scripts/backup-sessions.py`
- 實際腳本: `/data/.hermes/skills/devops/robust-db-persistence/scripts/cron-backup-sessions.py`
- Cron Job ID: `6527076f63be`
- Schedule: `0 */2 * * *` (每 2 小時)
