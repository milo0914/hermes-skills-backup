# Session Recovery 調查紀錄 (2026-06-07)

## 背景

6/6 下午 13:00-17:00 的對話（包含 strategy review、eng review、架構修正、Kaggle notebook 推送）因 HF Space 重啟而丟失。本地 SQLite DB 在重啟後被清空，HF 備份 cron job 只覆蓋到 06:00 和 12:00 的快照。

## 調查結論

1. HF 備份 `milo0914/record-for-hermes` 掃描了 655 個 user session，找不到 strategy review 相關內容
2. 本地 SQLite DB 中 6/6 完全沒有 session 記錄（重啟清除）
3. git backup (`hermes-skills-backup`) 只有 1 個 commit (6/6 22:03)，skills 內容與 live 完全一致 — 說明 review 修正尚未寫入 skill
4. 全系統找不到任何 .ipynb 檔案或 kaggle push 紀錄
5. kaggle CLI 未安裝在當前環境

## 影響

strategy review 發現的架構問題和 phase 1-4 修正任務需要重新執行。當前 skill 程式碼停留在初始版本。

## HF 備份搜尋技術筆記

搜尋 655 個 session 的有效方法：
- 先用 `datasets` library 載入，按日期分區篩選
- 用 Python script 掃描 messages 中的 tool_calls 和 content 關鍵詞
- 注意：session JSON 的 messages 可能在 `data.messages` 或頂層 `messages`，結構不一致
- `eph_` 前綴的 session 是 Web UI 產生的臨時 ID，`session_` 前綴是 API server 產生的穩定 ID
