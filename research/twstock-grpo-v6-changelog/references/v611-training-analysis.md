# GRPO v6.11 訓練結果分析

Date: 2026-06-16 13:27 (Kaggle output download)
Kernel version: 4
Runtime: ~815 秒

## 1. 環境資訊

| 項目 | 值 |
|------|-----|
| 版本 | v6.11 |
| 裝置 | **CPU** (GPU fallback — P100 sm_60 與 PyTorch 2.10+cu128 不相容) |
| PyTorch | 2.10.0+cu128 (min sm_70, max sm_120) |
| GPU | Tesla P100-PCIE-16GB (sm_60, 17.1GB) — **不支援** |
| group_size | 16 (auto_detect CPU 覆蓋) |
| train_steps | 5000 (auto_detect CPU 覆蓋) |
| entropy_coef | 0.25 |
| diversity_penalty | 3.0 |
| temperature | 2.0→0.8 |

### GPU 問題詳情
PyTorch 2.10+cu128 最低支援 sm_70，Kaggle 分配 P100 (sm_60)。
v6.11 的 `cc[0] >= 5` 門檻通過了（60 >= 50），但 CUDA kernel 實測失敗：
```
CUDA error: no kernel image is available for execution on the device
(cudaErrorNoKernelImageForDevice)
```
→ `gpu_compatible = False` → `GRPO_FORCE_CPU=1`

**影響**: auto_detect CPU 模式覆蓋了 v6.11 的核心參數：
- group_size: 64→32 (LARGE_CAP), 24→24 (MID_CAP), 16 (其他)
- train_steps: 8000→5000
- batch_size: 256→128

## 2. Regime 結果對比

| Regime | Formula | Len | Train IC | Val IC | IC Gap | Best R | Steps | 狀態 |
|--------|---------|-----|----------|--------|--------|--------|--------|------|
| traditional | TX_INST_NET_OI | 1 | 0.0961 | +0.1127 | -0.0167 | 0.320 | 801 | ✓無overfit, △弱信號 |
| large_cap | ATR | 1 | 0.0509 | -0.0056 | +0.0566 | 0.028 | 801 | ✗overfit, ✗無效 |
| mid_cap_tech | ABSORPTION | 1 | 0.0632 | +0.0264 | +0.0368 | 0.047 | 801 | △弱信號 |
| financial | SP500_CLOSE | 1 | 0.0859 | +0.0518 | +0.0341 | 0.249 | 801 | △弱信號 |

## 3. v6.11 監控項目

| # | 項目 | 預期 | 實際 | 判定 |
|---|------|------|------|------|
| 1 | IC 持續改善到 step 8000 | best_step > 1000 | 全部 step 0 | ✗ 失敗 |
| 2 | 公式長度 >= 3 tokens | 3+ tokens | 全部 1 token | ✗ 失敗 |
| 3 | Large_Cap val_IC 轉正 | > 0 | -0.0056 | ✗ 失敗 |
| 4 | Early stopping 適當觸發 | n_steps < 8000 | 801 (過早) | △ 部分成功 |
| 5 | adv_std ≈ 0.577 | 穩定 | 0.576-0.577 | ✓ 成功 |

## 4. 問題診斷

### P0: GPU fallback → CPU 覆蓋所有參數
- 根因: Kaggle PyTorch 2.10+cu128 只支援 sm_70+，但分配 P100 (sm_60)
- v6.11 的 `cc[0] >= 5` 門檻通過了檢查，但 CUDA kernel 實測失敗
- auto_detect 偵測到 cpu → 強制覆蓋 group_size/train_steps/batch_size
- **v6.11 的核心參數調整（train_steps=8000, group_size=64 等）全部被覆蓋**
- 解法方案:
  (a) 安裝舊版 PyTorch 支援 sm_60（如 torch 2.4+cu118）
  (b) 在 save button 選擇 T4 GPU (sm_75)，迴避 P100
  (c) 在 auto_detect CPU 模式中保留更多 v6.11 參數

### P1: Early stopping 觸發過早 (step 800 vs 預期 8000)
- 全部 4 個 regime 在 step 800 觸發 early stop (僅 10% 進度)
- patience_counter 累積: step 200 (+200) → step 400 (+200) → step 600 (+200) → 600 >= 500
- 根因: val_IC 初期波動大，step 0 的 best_reward 可能高於後續
- early_stop_min_delta=1e-4 太嚴格（微小的 IC 噪聲就被視為「有改善」）
- 解法:
  (a) 增加 warmup: 只在 step > 1000 後才啟用 early stop
  (b) patience 門檻提高: 500 → 2000
  (c) 增加 min_delta: 1e-4 → 5e-4

### P2: 公式長度全部 = 1 token
- complexity weight 0.05 和 operator_bonus 0.1 太弱
- CPU 模式 group_size=16/32 樣本數少，單特徵很容易 dominate reward
- 解法:
  (a) operator_bonus: 0.1 → 0.5
  (b) complexity weight: 0.05 → 0.15
  (c) 增加運算子 token 的 logits bias

### P3: Large_Cap val_IC 仍為負
- CPU fallback 後 group_size=32 (非預期的 64)
- ATR 單因子 val_IC = -0.0056
- 與 v6.10 LIQ_SCORE (-0.0115) 相比微升，但仍是負值

## 5. 與 v6.10 對比

| Regime | v6.10 Formula | v6.11 Formula | v6.10 ValIC | v6.11 ValIC | Δ |
|--------|--------------|--------------|------------|------------|---|
| traditional | LIQ_SCORE | TX_INST_NET_OI | +0.0995 | +0.1127 | +0.0132 |
| large_cap | LIQ_SCORE | ATR | -0.0115 | -0.0056 | +0.0059 |
| mid_cap_tech | SP500_CLOSE | ABSORPTION | +0.0304 | +0.0264 | -0.0040 |
| financial | CLOSE_POS | SP500_CLOSE | +0.0518 | +0.0518 | ≈0.0000 |

**觀察**: 
- traditional 微升、large_cap 微升、mid_cap_tech 微降、financial 不變
- 整體差異極小 → 因為 CPU 覆蓋讓 v6.11 參數調整幾乎無效

## 6. v6.12 改進方向

### P0 解: GPU 相容性
- **方案 A (推薦)**: 在 Kaggle notebook 開頭加 `!pip install torch==2.4.0+cu118` 安裝支援 sm_60 的 PyTorch
- **方案 B**: auto_detect 中，當 GPU 是 P100 (sm_60) 時不降級到 CPU，而是直接用 CPU tensor 跑（目前邏輯已是如此，但 flag 錯誤）
- **方案 C**: 修改 auto_detect CPU 模式，不覆蓋 group_size 和 train_steps，只覆蓋 device

### P1 解: Early stopping 太早
- 在 early stop logic 加入 warmup: `if step < 1000: continue`
- patience: 500 → 2000 (或基於 train_steps 的比例，如 25%)
- min_delta: 1e-4 → 5e-4

### P2 解: 公式複雜度
- operator_bonus: 0.1 → 0.5
- complexity weight: 0.05 → 0.15
- 可考慮在 logits 層面直接 boost operator token 的初始概率

### P3 解: Large_Cap
- 確保 GPU 模式下 group_size=64 生效（方案 A 解決）
- 或 CPU 模式也保留 LARGE_CAP group_size=64
