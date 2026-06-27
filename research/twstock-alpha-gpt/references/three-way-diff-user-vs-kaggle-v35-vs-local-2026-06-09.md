# 三版差異分析: 用戶版 vs Kaggle v3.5 vs 本地版

日期: 2026-06-09

## 版本來源

| 版本 | 檔案 | 行數 | 來源 |
|------|------|------|------|
| 用戶版 | `Gem-grpo-v3.3+alpha-factor-training` (ipynb) | 883 | https://github.com/milo0914/aidigmoney (commit 55b8d69) |
| Kaggle v3.5 | `grpo_regime_training_kaggle_v35.py` | 2207 | 本地 scripts/ 推送版 |
| 本地版 | `ai_dig_money_core.py` | 1913 | 五階段篩選管線 |

用戶版已下載至 `/tmp/user_version.py` (41031 chars, 883 lines)

## 一、定位差異

| | 用戶版 (883行) | Kaggle v3.5 (2207行) | 本地版 (1913行) |
|---|---|---|---|
| 定位 | 純 GRPO 訓練 (精簡修復版) | 純 GRPO 訓練 (完整+監控) | 完整篩選管線 (Stage1-4) |
| GRPO 引擎 | 完整內聯 | 完整內聯 | **空殼** (import 不存在模組) |
| 因子數 | 22 | 22 | 22 |
| VOCAB | 34 | 34 | 34 |
| Loss 函數 | **PPO clipped** (ratio≡1 bug) | **REINFORCE** (修復) | N/A (空殼) |
| NaN Guard | **無** | 完整 (step+param) | N/A |
| Data Leakage | **修復** (per-stock 80/20 split) | **無** (全量訓練) | N/A |
| Warmup | 有 | 有 | N/A |
| Walk-Forward | 有 | 有 | **無** |
| robust_normalize | 有 | 有 | **無** |
| GitHubLogPusher | stub (disabled) | 完整實作 | **無** |
| MTPHead | **啟用** (3-pool fusion) | **停用** (純 mean pool) | N/A |
| Synthetic data main() | 有 (standalone) | Kaggle dataset loading | N/A |

## 二、CEO Strategy Review — 用戶版優於 Kaggle v3.5 的改進

### S1. Data Leakage 修復 (用戶版 L770-788)

用戶版在 `train_all_regimes()` 中按每檔股票獨立做 80/20 時間切割，再合併 train/val 集合:

```python
# 用戶版 L770-788
for stock_id in stocks:
    data = stock_data_map[stock_id]
    feat, ret = data.get("feat"), data.get("returns")
    n_train = int(ret.shape[0] * 0.8)
    all_train_feat.append(feat[:, :n_train])
    all_train_returns.append(ret[:n_train])
    all_val_feat.append(feat[:, n_train:])
    all_val_returns.append(ret[n_train:])
```

v3.5 沒有驗證集切割，只在 `compute_group_rewards` 裡用 `val_ic=0`。

### S2. MTPHead 啟用 (用戶版 L524-535, L554-556)

用戶版啟用了 3-pool fusion (mean+max+first + gating):

```python
# 用戶版 L524-535 MTPHead
class MTPHead(nn.Module):
    def __init__(self, d_model, vocab_size, dropout=0.1):
        super().__init__()
        self.head_mean, self.head_max, self.head_first = [nn.Linear(d_model, vocab_size) for _ in range(3)]
        self.gate = nn.Linear(d_model * 3, 3, bias=False)
        self.head_critic = nn.Linear(d_model, 1)
    def forward(self, h):
        pool_mean, pool_max, pool_first = h.mean(dim=1), h.max(dim=1).values, h[:, 0, :]
        logits_mean, logits_max, logits_first = self.head_mean(pool_mean), self.head_max(pool_max), self.head_first(pool_first)
        weights = F.softmax(self.gate(torch.cat([pool_mean, pool_max, pool_first], dim=-1)), dim=-1)
        logits = weights[:, 0:1] * logits_mean + weights[:, 1:2] * logits_max + weights[:, 2:3] * logits_first
        return logits, self.head_critic(pool_mean).squeeze(-1)
```

v3.5 只用 mean pooling + 單獨 linear head。MTPHead 更有表達力。

### S3. Entropy 計算修復 (用戶版 L724-727)

用戶版收集每條路徑的真實 entropy 並加總，保持梯度連接:

```python
# 用戶版 L724-727
if all_entropies:
    entropy_loss = torch.stack(all_entropies).mean()
    loss -= self.config.entropy_coef * entropy_loss
```

v3.5 用 detached `no_grad` 單獨計算 entropy（不參與梯度），削弱了探索。

### S4. 精簡化

883 行 vs 2207 行，去掉了冗餘的 `generate_synthetic_data()` / Kaggle dataset loading / JSON 儲存等，邏輯更聚焦。

## 三、CEO Strategy Review — Kaggle v3.5 優於用戶版的改進

### S5. REINFORCE Loss (v3.5 L1515-1522)

v3.5 修了 PPO ratio≡1 零收斂 bug。用戶版仍用 PPO clipped surrogate (L720-722):

```python
# 用戶版 L720-722 — BUG: ratio≡1.0, loss≡0
ratio = torch.exp(log_probs_tensor - log_probs_tensor.detach())  # ≡ 1.0
clipped_ratio = torch.clamp(ratio, 1.0 - self.config.clip_eps, 1.0 + self.config.clip_eps)
loss = -torch.min(ratio * advantages, clipped_ratio * advantages).mean()  # ≡ -advantages.mean() ≡ 0
```

這是最嚴重的 bug — 模型不會收斂。正確做法 (v3.5):

```python
# v3.5 L1521-1522 — REINFORCE
loss = -(log_probs_tensor * advantages.detach()).mean()
```

### S6. NaN Guard (v3.5 L1544-1563)

v3.5 有 step-level NaN skip + param-level reinit。用戶版完全沒有 NaN 保護:

```python
# v3.5 L1544-1563
if torch.isnan(loss) or torch.isinf(loss):
    print(f" [NaN GUARD] step {step}: loss is NaN/Inf, skipping")
    continue
# ...
has_nan = any(p.isnan().any() for p in self.model.parameters())
if has_nan:
    print(f" [NaN GUARD] step {step}: NaN in params, reinitializing")
    self.model = build_looped_transformer(self.config).to(self.config.device)
    self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.config.lr, weight_decay=1e-5)
    self._old_log_probs = None
    continue
```

### S7. Train/Val IC 獨立計算

v3.5 的 `_compute_ic` 回傳 array（每公式獨立 IC）。用戶版的 `_compute_ic_array` 也有，但 reward calculator 裡 `train_ic[i]` 取值邏輯不同。

## 四、兩版共同缺失

### S8. TWFeatureEngineer 4個因子恆為0

用戶版 L320: `for f in ["TX_MTX_SPREAD", "NASDAQ_CLOSE", "SP500_CLOSE", "DOWJONES_CLOSE"]: g[f] = 0`

這4個因子全部填0！v3.5 也只計算了 TX_MTX_SPREAD 但美股也是0。

修復:
- `TX_MTX_SPREAD = TX_INST_NET_OI - MTX_RETAIL_OI`
- 美股因子需從 us_indices_df merge close 價再 robust_normalize

## 五、Eng Review — Bug / 改進清單 (三版交叉比對)

### CRITICAL (阻礙訓練收斂)

| # | Bug | 用戶版 | v3.5 | 本地版 | 綜合版修法 |
|---|---|---|---|---|---|
| E1 | PPO ratio≡1 零收斂 | YES (L720) | 修復 (REINFORCE) | N/A | 採用 v3.5 REINFORCE loss |
| E2 | NaN Guard 缺失 | YES | 修復 | N/A | 採用 v3.5 NaN guard |
| E3 | 本地版 import 不存在模組 | N/A | N/A | YES (L837) | 移除 import，改為內聯 class |
| E4 | 本地版隨機 returns | N/A | N/A | YES (L877) | 採用用戶版真實前向報酬計算 |
| E5 | TX_MTX_SPREAD 恆為0 | YES (L320) | YES | N/A | 補實作: g["TX_MTX_SPREAD"] = g["TX_INST_NET_OI"] - g["MTX_RETAIL_OI"] |
| E6 | 美股指數因子恆為0 | YES (L320) | YES | N/A | 補實作: merge us_indices_df |

### HIGH (功能缺失 / 品質)

| # | 項目 | 用戶版 | v3.5 | 本地版 | 綜合版修法 |
|---|---|---|---|---|---|
| E7 | Walk-Forward 驗證 | 有 (L825) | 有 | **無** | 採用用戶版 WF |
| E8 | robust_normalize | 有 (L232) | 有 | **無** | 採用用戶版 |
| E9 | RegimeConfig.feature_weights 22維 | 16維 (L193) | 16維 | 16維 | 補6個v3.1因子權重 |
| E10 | Data Leakage 防護 | 有 (L770) | **無** | N/A | 採用用戶版 per-stock split |
| E11 | MTPHead 啟用 | 有 | **無** (mean only) | N/A | 採用用戶版 MTPHead |
| E12 | 本地版缺 close in feature_df | N/A | N/A | YES (E12) | compute_features 保留 close |
| E13 | 用戶版 main() 只用合成數據 | YES | Kaggle dataset | N/A | 保留 Kaggle dataset loading |

### MEDIUM (運維 / 品質)

| # | 項目 | 用戶版 | v3.5 | 本地版 | 綜合版修法 |
|---|---|---|---|---|---|
| E14 | GitHubLogPusher | stub | 完整 | **無** | 採用 v3.5 完整版 |
| E15 | 用戶版 StableRankMonitor 精簡 | 有 (5行) | 完整 (40行) | **無** | 用戶版精簡即可 |
| E16 | Entropy 計算方式 | 路徑真實 | detached no_grad | N/A | 採用用戶版（梯度連接） |
| E17 | GPU capability 閾值 | sm_70 (L32) | sm_50 (v3.5) | sm_70 | 統一 sm_50 (放寬相容) |
| E18 | LoRD decay | inline (L735-743) | 抽成 _apply_lord_decay() | N/A | 抽方法較佳 |

## 六、綜合版 TODO 清單 (排序)

### Phase A: Critical Bug 修復 (訓練收斂阻塞)

1. **[E1] REINFORCE Loss 替換 PPO** — 用戶版 L720 的 `ratio = exp(lp - lp.detach())` 恆等1，需改為 `loss = -(log_probs * advantages.detach()).mean()` (v3.5 L1522)
2. **[E2] NaN Guard 移植** — step-level NaN skip + param-level reinit (v3.5 L1544-1563)
3. **[E3] 本地版 phase2 內聯 GRPO** — 移除 `from grpo_alpha_trainer import`，將用戶版精簡 GRPO 引擎移植為本地版 inner class
4. **[E4] 本地版 returns 修正** — 移除 `np.random.randn()`，改為用 close 算真實前向報酬 (用戶版 L869-872)
5. **[E5] TX_MTX_SPREAD 計算** — compute_features 補 `g["TX_MTX_SPREAD"] = g["TX_INST_NET_OI"] - g["MTX_RETAIL_OI"]`
6. **[E6] 美股指數因子計算** — merge us_indices_df 的 Nasdaq/SP500/DowJones close 並 robust_normalize

### Phase B: 架構改進 (訓練品質)

7. **[E10] Data Leakage 防護** — 用戶版 per-stock 80/20 時間切割，移植到 Kaggle 訓練版
8. **[E11] MTPHead 啟用** — 用戶版 3-pool fusion (mean+max+first+gating) 替換 v3.5 的 mean-only head
9. **[E16] Entropy 梯度連接** — 用戶版收集真實路徑 entropy 並 backward，替換 v3.5 的 detached no_grad
10. **[E9] RegimeConfig 22維權重** — 補 TX_INST_NET_OI / MTX_RETAIL_OI / TX_MTX_SPREAD / NASDAQ_CLOSE / SP500_CLOSE / DOWJONES_CLOSE 各 regime 權重

### Phase C: 驗證框架 (上線品質)

11. **[E7] Walk-Forward 移植到本地版** — 本地版 run_daily_scan 最終步加入 WF 驗證
12. **[E8] robust_normalize 移植到本地版** — compute_features 用 MAD 替換純 zscore
13. **[E12] 本地版 feature_df 保留 close** — compute_features 輸出保留 close 欄位供 phase2 算前向報酬
14. **[E13] Kaggle 整合 main()** — 保留 Kaggle dataset loading 路徑 + 用戶版合成數據 fallback

### Phase D: 運維 + 清理

15. **[E14] GitHubLogPusher 完整版** — 移植 v3.5 的 token-based push
16. **[E18] LoRD decay 抽方法** — `_apply_lord_decay()` 獨立方法
17. **[E17] GPU capability sm_50 放寬** — 統一三版閾值
18. **[E15] StableRankMonitor** — 用戶版精簡版即可
19. 三版統一為一個綜合版 (Kaggle + 本地版共用同一份 GRPO 引擎)

## 七、用戶版代碼位置索引

| 模組 | 用戶版行號 | 說明 |
|------|-----------|------|
| check_environment | L19-47 | GPU 檢查 (sm_70) |
| FEATURE_NAMES | L53-59 | 22 因子 |
| OPERATOR_NAMES/ARITY | L61-69 | 12 算子 |
| StackVM | L75-126 | 公式執行 VM |
| StackVMState | L132-169 | 引導式解碼 |
| StockRegime | L175-189 | 4 股性定義 |
| RegimeConfig | L191-210 | feature_weights (16維) + operator_mask + training_params |
| RegimeTrainingPlan | L212-226 | create_plan() |
| robust_normalize | L232-251 | MAD 正規化 |
| TWFeatureEngineer | L253-353 | compute_features (22因子, 4因子填0) |
| GRPOConfig | L359-401 | auto_detect() |
| GitHubLogPusher | L403-407 | stub (disabled) |
| GRPORewardCalculator | L413-478 | _spearman_corr + compute_group_rewards |
| build_looped_transformer | L484-558 | RMSNorm/SwiGLU/QKNorm/MTPHead/LoopedTransformer |
| StableRankMonitor | L564-584 | 精簡版 |
| GRPOAlphaTrainer | L586-804 | init_torch, _compute_ic_array, train_torch_regime, train_all_regimes |
| decode_formula | L810-823 | 反編譯器 |
| walk_forward_validation | L825-844 | 5-fold OOS 驗證 |
| main | L846-884 | 合成數據 demo |

## 八、建議執行策略

以用戶版為基底（精簡 + Data Leakage 修復 + MTPHead + Entropy 梯度），修入 v3.5 REINFORCE + NaN Guard，補全 TWFeatureEngineer 缺失的 4 個因子計算，然後將修好的 GRPO 引擎內聯到本地 `ai_dig_money_core.py`。

最大風險: **E1 (PPO→REINFORCE)** — 用戶版的 PPO 實作在 on-policy GRPO 下 ratio≡1，loss 恆為0，模型完全不會收斂。這是唯一阻礙訓練成功的 blocker。
