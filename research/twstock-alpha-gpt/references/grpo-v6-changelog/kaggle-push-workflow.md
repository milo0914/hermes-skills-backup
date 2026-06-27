# Kaggle Kernel Push 版本管理工作流

## 重要注意事項 (v6.11 push 經驗更新)

### Kaggle CLI 指令
- 本環境使用 `python3 -m kaggle` 而非 `kaggle`（後者不適用）
- 認證檔: `~/.kaggle/kaggle.json` (534 bytes)

### Push 新版本時的 Slug 行為
- v6.11 push 時 title 改為 `...v6.11...`，Kaggle 自動建議新 slug
- 警告訊息: `Your kernel title does not resolve to the specified id.`
- 但 push 仍成功: `Kernel version 4 successfully pushed.`
- 結果: Kaggle 建立了新 URL: https://www.kaggle.com/mhhuang14/twstock-grpo-regime-aware-factor-training-v6-11
- 教訓: title/slug 不一致不影響 push，但 id 欄位必須是已存在的 kernel slug

## 原則
Kaggle kernel 的「版本」是內部 version number，不是 slug。
不要在 push 時嘗試創建新的 kernel slug（會報 Permission denied）。
正確做法：更新現有 kernel 的 `kernel-metadata.json` → push → 自動建立新版本。

## 步驟

1. 確認要上傳的 notebook 和 metadata 在同目錄
   ```
   push_dir/
   ├── twstock-grpo-regime-aware-factor-training-v6-X.ipynb
   └── kernel-metadata.json   # id 指向現有 kernel slug
   ```

2. `kernel-metadata.json` 的 `id` 必須是已存在的 kernel slug
   ```json
   {
     "id": "mhhuang14/twstock-grpo-regime-aware-factor-training-v6-9",
     "code_file": "twstock-grpo-regime-aware-factor-training-v6-11.ipynb",
     "title": "TWStock GRPO Regime-Aware Factor Training v6.11 (Early Stop + Param Tune + GPU Fix)"
   }
   ```
   - `id`: **不改**，沿用舊 slug
   - `code_file`: 新 notebook 檔名
   - `title`: 可以更新為新版本號（Kaggle 可能自動建新 slug）

3. Push
   ```bash
   python3 -m kaggle kernels push -p /path/to/push_dir
   ```
   成功輸出：`Kernel version N successfully pushed.`

4. 確認狀態
   ```bash
   python3 -m kaggle kernels status mhhuang14/twstock-grpo-regime-aware-factor-training-v6-9
   ```

5. 下載 Output
   ```bash
   python3 -m kaggle kernels output mhhuang14/twstock-grpo-regime-aware-factor-training-v6-9 -p ./output --force
   ```

## 常見錯誤
- ❌ `id` 設為不存在的 slug → `Permission denied`
- ❌ `title` 改為新名稱且 `id` 也改 → 同樣報錯
- ✅ 正確：只改 `code_file` 和 `title`，`id` 維持舊值
- ⚠️ title 與 id slug 不一致時 Kaggle 會警告，但 push 仍可成功

## 版本推送歷史

| 版本 | Kernel Version | 日期 | 備註 |
|------|---------------|------|------|
| v6.9 | v1 | 2026-06-15 | 初始推送 |
| v6.10 | v3 | 2026-06-15 | title 修正 + stock_id int 鍵修復 |
| v6.10 | v8 | 2026-06-15 | GPU sm_60 + 最終修正 |
| v6.11 | v4 | 2026-06-16 | Early Stop + Param Tune + GPU sm_50 |
