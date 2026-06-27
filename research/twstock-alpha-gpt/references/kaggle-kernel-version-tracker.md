# Kaggle GRPO Kernel Version Tracker (2026-06-09)

追蹤所有 Kaggle GRPO 訓練 kernel 版本、slug、狀態與教訓。

## 所有 Kernel 版本

| # | 版本 | Slug | 類型 | GPU | 狀態 | 結果 | 推送日期 |
|---|------|------|------|-----|------|------|----------|
| 1 | v3.1 | `mhhuang14/twse-grpo-regime-aware-alpha-factor-training-v3-1` | notebook | T4 | ERROR | RuntimeError: tensor dimension mismatch (action.unsqueeze vs view) | 2026-06-08 |
| 2 | v3.2 | `mhhuang14/grpo-regime-aware-alpha-factor-training-v3-2-fix` | notebook | T4→CPU | COMPLETE | 合成數據，僅 financial(2882)完成，loss=-0.0000，公式=NASDAQ_CLOSE | 2026-06-08 |
| 3 | v3.3-nogpu | `mhhuang14/grpo-v33-nogpu-test` | notebook | 無 | COMPLETE | 同 v3.3-gpu 但無 GPU。結果相同：compute_features 只回傳 2882 單檔 | 2026-06-09 |
| 4 | v3.3-gpu | `mhhuang14/grpo-v33-dsfix` | notebook | T4→CPU(P100) | COMPLETE | os.walk + squeeze(0)，但 P100 不相容→CPU fallback。**compute_features 只回傳 2882 單檔**（groupby view bug，見 pitfall #77）| 2026-06-09 |
| 5 | v3.4 | `mhhuang14/grpo-regime-aware-factor-training-v3-4` | notebook | T4 | RUNNING | NaN 穩定性修復 | 2026-06-09 |
| 6 | v3.5 | `mhhuang14/grpo-regime-aware-factor-training-v3-5` | notebook | T4 | ERROR | IndentationError (L1555) | 2026-06-09 |
| 7 | v4 | `mhhuang14/grpo-regime-aware-factor-training-v4` | script | T4→CPU(P100) | COMPLETE | CPU fallback 成功，4 regime 訓練完成 | 2026-06-09 |
| 8 | v5 | `mhhuang14/grpo-regime-aware-factor-training-v5-3-bug-fix` | script | T4 | RUNNING→COMPLETE | 3-bug fix，**PPO loss≡0 確認**（loss=0.0000, clip_ratio=0%, mean_r=0.175→-0.504）+ dataset未掛載（fallback合成數據） | 2026-06-09 |
| 9 | 診斷 | `mhhuang14/diag-kaggle-input-path` | notebook | 無 | COMPLETE | 確認三層巢狀路徑結構 | 2026-06-09 |
| 10 | v5.1 | `mhhuang14/grpo-v51-reinforce-fix` | script | T4 | RUNNING | REINFORCE + os.walk + group_size=16 + lr_warmup_steps=500。build_v51.py 字串替換建構。 | 2026-06-09 |
| 11 | v5.5 | `mhhuang14/grpo-regime-aware-factor-training-v5-5` | script | T4 | COMPLETE | **PPO loss≡0 重現** (REINFORCE 未合入), 4檔只2882訓練, 公式=SP500_CLOSE單因子, WF t-stat=0.54 | 2026-06-10 |
| 12 | v5.6 | `mhhuang14/grpo-regime-aware-factor-training-v5-6` | script | P100→CPU | CANCELLED | REINFORCE loss 仍 -0.0000 (advantage zero-mean centering), GPU 未偵測 (sm_70 門檻) | 2026-06-10 |
| 13 | v5.7 | `mhhuang14/grpo-regime-aware-factor-training-v5-7` | script | P100→CPU | CANCELLED | min-max advantage + sm_50 門檻, 但 P100 sm_60 仍不相容 + CPU G=4 advantage 坍縮 (step 500+ adv=[0,0]) | 2026-06-10 |
| 14 | v5.8 | `mhhuang14/grpo-regime-aware-factor-training-v5-8` | script | T4(指定) | RUNNING | advantage collapse guard + entropy 0.05 + batch logits + sm_70 檢查 + --accelerator nvidia-tesla-t4 | 2026-06-10 |

## 409 Conflict 歷史

| 嘗試 Slug | 衝突對象 | 原因 | 解決方案 |
|-----------|----------|------|----------|
| `grpo-v33-regime-dataset-fix` | 已存在 kernel | slug 重複 | 改用 `grpo-v33-dsfix` |
| `grpo-regime-aware-factor-training` (v5) | v5 original | title 衝突 | 加版號 `v5-3-bug-fix` |

## Dataset

| Slug | 內容 | 版本 | 備註 |
|------|------|------|------|
| `mhhuang14/twstock-grpo-training-data` | twstock_daily.csv (真實 FinMind) | v1 | 4檔股票 2022-01-03~2025-06-30 |

## 訓練結果摘要

### v3.2 (合成數據，CPU-only)
- 唯一完成 regime: FINANCIAL (2882)
- 最佳公式: NASDAQ_CLOSE (合成數據無意義)
- Val IC: 0.203, WF IC: 0.242, t-stat: 1.12
- loss: -0.0000 (全部步數，.4f 格式)

### v3.3 (os.walk + squeeze fix, 但 P100+view bug)
- 兩個 kernel (GPU + NoGPU) 都完成
- **P100 GPU 不相容** → fallback CPU (G=4, batch=16, steps=3000)
- **compute_features view bug**: 4 檔股票 → 只有 2882 的 843 rows 被回傳
  - 每檔單獨呼叫正常（843 rows），全量呼叫只回傳最後一檔
  - 根因：`result_frames.append(g[keep_cols])` 存的是 view 而非 copy
  - 修復：`.copy()` — `result_frames.append(g[keep_cols].copy())`
- 只訓練到 2882 (financial)，reward=1.3729, val_IC=0.1816
- walk_forward_results: 只有 2882 一筆
- training_history: 空 list

### v4 (CPU fallback, P100 不相容)
- 4 regime 全部訓練完成 (CPU 模式)
- Train IC: 1301=0.1975, 2330=0.1391, 2454=0.1041, 2882=0.2199
- GitHubLogPusher 因 GITHUB_TOKEN 未注入而失敗

### v5.5 (T4 GPU, PPO loss≡0 重現)
- **致命問題**: PPO ratio≡1 → loss≡0 (REINFORCE 修復未合入 v5.5 source)
- Step 0~19500: loss=-0.0000 全部
- Reward: step 0 mean_r=-0.159 → step 500 mean_r=1.296 → 停滯到結束
- Regime 分群: 只有 mid_cap_tech: [2882] 進入訓練 (其他3檔消失)
- 最佳公式: SP500_CLOSE (token [20], 單因子退化)
- Walk-Forward 2882: Mean IC=0.071, t-stat=0.54, Positive folds=80%
- training_history.json: {"2882": []} (空記錄)
- 詳見 references/kaggle-v55-training-analysis.md

## Cron 監控歷史

| Cron 名稱 | Job ID | 目標 Kernel | 排程 | 狀態 |
|-----------|--------|-------------|------|------|
| kaggle-grpo-v32-monitor | 3f173f04501b | v3.2 | 每5m×12 | completed |
| kaggle-grpo-v33-monitor | — | v3.3-gpu | 每5m | paused |

## 教訓

1. **每次重大修改用新 slug** — 避免與已完成 kernel 的 slug 衝突
2. **先推 CPU 診斷版** — 驗證路徑/數據邏輯再推 GPU 版
3. **kernel-metadata.json 的 id 必須匹配 title 推導的 slug** — 否則 push 成功但可能產生幽靈 kernel
4. **Kaggle GPU slot 限制 2 個** — 多個 GPU kernel 同時排隊會 409
5. **P100 (sm_60) 與 PyTorch 2.10+cu128 不相容** — 必須 CUDA probe + CPU fallback
6. **pandas DataFrame view vs copy** — groupby 迴圈中 `list.append(g[subset])` 存的是 view，最終 concat 只保留最後一個迭代。必須 `.copy()`
7. **版本回退是最隱蔽的 bug** — v5.5 重現了 v3.5 已修復的 PPO loss≡0 問題，因為建構新版本時基於舊 source 未合入修復。建構前必須過 checklist：REINFORCE loss、_safe_logits、os.walk、.copy()
