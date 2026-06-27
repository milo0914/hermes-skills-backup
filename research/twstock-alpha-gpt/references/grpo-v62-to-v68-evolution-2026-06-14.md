# GRPO v6.2 → v6.8 演進總結 (2026-06-14)

## 版本對照表

| 版本 | 位置 | 關鍵特徵 | 主要修復 |
|------|------|----------|----------|
| **v5.9** | `/home/appuser/kaggle_kernel/grpo-regime-aware-factor-training-v5-9.ipynb` | Cross-sectional (20股, 5/regime), CPU G=16, Gumbel noise, diversity reward, temperature scheduling, adapt_finmind_data | 首次引入 4 regime × 5 股結構 |
| **v6.1** (檔名) / **v6.2** (docstring) | `/home/appuser/twstock_kernel/grpo-regime-aware-factor-training-v6-1.ipynb` | 強制真實數據, 移除合成 fallback, 修正 data_path 掛載點 | "No Synthetic" 政策, auto-scan /kaggle/input/ |
| **v6.8** (Kaggle 實際最新) | `/home/appuser/twstock_v68_kernel/twstock-grpo-regime-aware-factor-training-v6-8.ipynb` | 完整 RegimeTrainingPlan, advantage collapse fix, group_size=64 CPU, noise injection | RegimeTrainingPlan 完整實作, 4 regime 完整配置, CPU 模式優化 |

## 關鍵改版重點

### v5.9 → v6.1/v6.2: "No Synthetic" 政策
- **問題**: v5.9 仍有合成數據 fallback，導致訓練品質不穩定
- **修復**: 
  1. 移除所有合成數據生成程式碼
  2. `adapt_finmind_data` 找不到真實資料 → 直接 `raise FileNotFoundError`
  3. `data_path` 修正為 Kaggle dataset slug 掛載點
  4. 保留 inst/margin/futures/US 真實數據 merge 邏輯

### v6.1/v6.2 → v6.8: RegimeTrainingPlan 完整化 + Advantage Collapse Fix
- **RegimeTrainingPlan (v6.8 新增完整實作)**:
  - `feature_weights`: 4 regime 各自的 22 維因子權重
  - `operator_mask`: 4 regime 的 operator 啟用/禁用 (TRADITIONAL/FINANCIAL 禁用 SIGN/JUMP)
  - `training_params`: group_size / reward_horizon per regime
  - `create_plan()`: 依 stock_id 生成完整 regime_plan dict

- **Advantage Collapse Fix (v6.5+ → v6.7/v6.8)**:
  - CPU 模式: `group_size = max(config.group_size, 64)` (原 v5.9 為 16)
  - `train_steps = max(config.train_steps, 15000)`
  - `batch_size = max(config.batch_size, 256)`
  - Entropy coef: 0.15 (提升探索)
  - Gumbel noise scale: 1.5
  - Diversity penalty: 3.0
  - **關鍵**: advantage std < 1e-4 時注入小噪聲 `noise = torch.randn_like(advantages) * 0.1` (而非全隨機)

- **KNOWN_REGIMES 完整覆蓋 20 檔**:
  - LARGE_CAP: 2330, 2308, 2412, 1303, 1326 (5檔)
  - MID_CAP_TECH: 2454, 2382, 2317, 3034, 3711 (5檔)
  - TRADITIONAL: 1301, 1101, 2002, 2105, 2207 (5檔)
  - FINANCIAL: 2882, 2886, 2891, 2881, 2884 (5檔)
  - **注意**: StockRegime enum 有 SMALL_CAP 但 KNOWN_REGIMES 未使用

## 已知 Bug 仍在 v6.8 中 (需修復)

1. **Reward function 非 regime-aware**: `compute_group_rewards` 計算 group_mean/group_std 時跨 regime 混合，導致不同 regime 的 rewards 不可比較。應改為 **regime 內部 rank** + **cross-regime baseline**。

2. **Advantage normalization 缺失**: 沒有 group-level baseline subtraction，只有 clip。

3. **Entropy coef 仍偏高**: 0.15 配合 group_size=64 可能過度探索。

4. **v6.7 CPU mode logic 重複**: `auto_detect()` 中 CPU 分支設定 group_size=64，但下面又有 `config.group_size = max(config.group_size, 64)` 重複。

5. **adapt_finmind_data 使用 os.walk**: v6.8 仍用 os.walk 而非 glob 遞迴，掛載路徑不穩定時會漏檔。已有 fix_adapt_finmind.py 修復版但未合入。

6. **data_path 硬編碼**: main() 中 `data_path = "/kaggle/input"` 未使用 auto-detect，依賴 adapt_finmind_data 內部掃描。

## 實體檔案對照

```
本地開發環境:
├── /home/appuser/twstock_kernel/
│   ├── grpo-regime-aware-factor-training-v6-1.ipynb     # v6.1 檔名 / v6.2 docstring
│   ├── kernel-metadata.json                             # id 指向 v6.8
│   ├── kernel-metadata-v6.1.json                        # 原 v6.1 metadata
│   ├── twstock-v6-0-data-fetch-20-stocks-5y-v2.py       # Data fetch kernel v4.4
│   ├── fix_adapt_finmind.py                             # adapt_finmind_data glob 修復腳本
│   └── fix_meta_title.py / change_slug.py               # metadata 修改工具
│
├── /home/appuser/twstock_v68_kernel/                    # Kaggle pull 下來的 v6.8
│   ├── twstock-grpo-regime-aware-factor-training-v6-8.ipynb
│   └── kernel-metadata.json
│
├── /home/appuser/kaggle_kernel/
│   ├── grpo-regime-aware-factor-training-v5-9.ipynb     # v5.9 參考
│   └── grpo-regime-aware-factor-training-v6-1.ipynb     # v6.1 副本
│
├── /home/appuser/twstock_kernel_out/twstock_v6_data/    # Kernel output 下載
│   ├── price_ohlcv.csv    (2.16 MB, 23,066 rows)
│   ├── inst_flow.csv      (1.69 MB, 25,042 rows)
│   ├── margin.csv         (837 KB, 25,042 rows)
│   ├── futures_oi.csv     (116 KB, 2,674 rows)
│   └── us_indices.csv     (123 KB, 3,765 rows)
│
├── /home/appuser/twstock_v6_data/                       # 複製給 dataset 用
│   ├── (同上 5 CSV) + dataset-metadata.json
│
└── /home/appuser/twstock_v6_data_backup/                # 備份
```

## Kaggle 端狀態

| 資源 | slug | 狀態 |
|------|------|------|
| Data Fetch Kernel | `mhhuang14/twstock-v6-0-data-fetch-20-stocks-5y-v2` | v4.4 (FinMind REST API) - COMPLETE |
| Training Kernel | `mhhuang14/twstock-grpo-regime-aware-factor-training-v6-8` | **最新 v6.8** (private, GPU enabled) |
| Training Kernel (舊) | `mhhuang14/grpo-regime-aware-factor-training-v5-9` | v5.9 |
| Dataset | `mhhuang14/twstock-v6-0-real-data-20stocks-5y` | **已更新 2026-06-14 10:00** (1.55 MB, 5 CSV) |
| Dataset (舊) | `mhhuang14/twstock-grpo-training-data` | 400 KB (舊版) |

## 下一步建議修復方向 (v6.9)

1. **Regime-aware reward**: `compute_group_rewards` 改為按 regime 分組計算 advantages
2. **Entropy coef**: 降至 0.05-0.08
3. **Advantage normalization**: 加入 group-level baseline subtraction
4. **合併 fix_adapt_finmind.py**: 將 glob 遞迴掃描合入 notebook
5. **data_path auto-detect**: main() 直接呼叫掃描函數而非硬編碼
6. **SMALL_CAP regime**: 決定是否啟用 (需額外 5 檔股票)

## 相關參考文檔
- `references/finmind-rest-api-workaround-2026-06-14.md` — Data fetch kernel FinMind REST API 解法
- `references/kaggle-kernel-version-management-2026-06-14.md` — 三層版號管理
- `references/kaggle-dataset-auto-scan-pattern-2026-06-13.md` — auto-scan 掛載模式
- `references/grpo-advantage-collapse-fix-pattern-2026-06-13.md` — Advantage collapse 修復模式
- `references/grpo-v61-regime-bugs-found-2026-06-14.md` — v6.1/v6.2 regime bugs 分析
- `references/dataset-v2-push-2026-06-14.md` — 本次 dataset 推送記錄