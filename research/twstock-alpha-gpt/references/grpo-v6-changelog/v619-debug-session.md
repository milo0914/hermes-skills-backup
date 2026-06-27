# v6.19 Kaggle 實測結果與 Debug Session (2026-06-18/19)

## 任務背景
用戶要求推送 v6.19 到 Kaggle 並修復訓練崩潰問題。

## 推送過程問題

### 1. Notebook source 格式錯誤（關鍵）
- 原本本地 notebook 的 code cell `source` 為 `list`（包含字面 `\n` 字符）而非 `str`
- Kaggle 遇到 `source=list` 時**跳過所有 cell 執行**，只跑 nbconvert 轉 HTML
- 症狀：Kernel 狀態直接從 RUNNING 跳到 COMPLETE（<20秒），無 stdout/stderr 訓練日誌

### 2. 修復方案：從 GitHub 獲取正確版本
```bash
git clone https://$GITHUB_TOKEN@github.com/milo0914/aidigmoney.git /tmp/aidigmoney
# repo 中 "GRPO Regime-Aware Factor Training v6.19-composite score F" 為正確 .ipynb
```
- 正確版本：`source=str`、真實換行、1833 行、語法通過
- 本地版本因 .py→.ipynb 轉換失敗導致格式損壞

### 3. Metadata 格式關鍵差異
- ❌ v6.19 初始：`accelerator: "GPU_T4"`, `machine_shape: "NvidiaTeslaT4"`, `is_idle_no_idle: true` → Kernel 即時 COMPLETE
- ✅ v6.18 風格：`machine_shape: "Gpu"`, `docker_image` 具體 sha256、**無** `accelerator`、**無** `is_idle_no_idle` → 正常 RUNNING ~20分鐘

## 訓練結果分析

### 環境
- GPU：P100 (sm_60) → CUDA probe 失敗 → CPU fallback (GRPO_FORCE_CPU=1)
- 數據：成功載入 5 CSV，20 檔股票，7 檔 mid_cap_tech

### 參數
- `group_size=32`, `train_steps=6000`, `device=cpu`
- `early_stop_patience=3000`, `early_stop_warmup=1000`
- `short_formula_penalty=5.0`, `operator_bonus=0.5`

### 結果 — **仍有 Collapse**
| 指標 | 結果 | 問題 |
|------|------|------|
| `best_reward` | -5.0 | 全群體觸發 `short_formula_penalty` |
| `val_IC` / `train_IC` | 0.0 / 0.0 | 無有效信號 |
| `with_ops` | 23/32 → 0/32 | 探索完全崩潰 |
| 最佳公式 | `[29]` (INVALID) | 退化為單 feature token |

### 關鍵觀察
1. **Rank-based advantage 正常**：`adv_std ≈ 0.577` 全程穩定
2. **v6.18 強制重種觸發 4 次**（step 1992/2992/3992/4992）但無法恢復探索
3. **Early stop 條件有效**：`has_exploration` 正確引用 composite-best，但探索已完全歸零
4. **探索崩潰時序**：
   - Step 0: with_ops=23/32, avg_ops=0.72, avg_len=2.2 (warmup 有效)
   - Step 600: with_ops=10/32 (eps boost 到 0.486)
   - Step 1200: with_ops=5/32, best_ops=0, best_len=1
   - Step 2000+: with_ops 振盪 0-8/32，best_composite 鎖定

## 待修復方向 (v6.20)

### P0 (必須)
1. **`short_formula_penalty=5.0` 過大** → 導致所有候選 reward=-5.0，advantage 全零
2. **Warmup operator seed 生成** 需確保長度 ≥4 的有效公式（目前 3-token 被 penalty 扣分）
3. **CPU 模式 G=32 可能仍偏小** → 建議 G≥64 + batch=128

### P1
4. **Debug `compute_group_rewards`** 對 invalid 公式的處理
5. **Re-seed template 長度** ≥ min_formula_len (4)
6. **Val_IC 雙向獎懲** 在 reward 中生效（目前 val_ic_bonus=2.0 可能未正確加入）

### P2
7. **Kaggle metadata 文檔化** v6.18 風格為標準

## 關鍵經驗總結

1. **Notebook source 必須是 str + 真換行** — 最隱蔽致命坑 (kaggle-api pitfall #72)
2. **Metadata 用 v6.18 風格（Gpu + docker_image）** — 非 accelerator/machine_shape 組合
3. **kernels output 阻塞行為** — RUNNING 時不回傳 "still running"，只能間接監控
4. **GitHub repo 為權威來源** — 本地格式損壞時優先從 `milo0914/aidigmoney` clone
5. **P100 分配常態化** — 必須有 CPU fallback 邏輯，且 G≥16
6. **v6.18 composite score 機制半實作** — v6.19 修復了 best_idx 選擇但 reward 結構仍有缺陷

## 相關檔案
- Kaggle Kernel: https://www.kaggle.com/code/mhhuang14/twstock-grpo-v6-19-composite-score-full-fix
- 本地 log: `/tmp/kout_v619_final/twstock-grpo-v6-19-composite-score-full-fix.log`
- 輸出: `best_strategy_per_regime.json`, `training_report.json`