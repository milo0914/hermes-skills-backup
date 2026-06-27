# Cron Self-Heal v5 Fix — 2026-06-10

## 故障現象

Cron job `6527076f63be` (session-backup) 失敗 — 自癒報告成功但實際未恢復缺失 skill。

## 根因

v4 `heal_skills_from_github()` 只檢查 category 目錄是否存在。若 `devops/` 因其他 skill 已恢復而不為空，即使 `robust-db-persistence` 缺失也會跳過整個 category。

## 修正

v5 改為 skill-level 粒度：category 已存在時逐 skill 檢查，僅複製缺失項。

詳見 `devops/robust-db-persistence/references/cron-self-heal-v5-fix.md`（完整分析）。
