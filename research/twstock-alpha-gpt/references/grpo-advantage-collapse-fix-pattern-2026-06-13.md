# GRPO Advantage Collapse Fix Pattern (2026-06-13)

## 現象
- Step 400 起 `adv_std=0.0000`，log 反覆印 `[v5.9] Adv near-zero (std=0.00e+00), adding small noise.`
- 所有 group 內 16 條公式的 reward (Spearman IC) 差異極小 → baseline group_mean 後分母趨近 0
- Gradient 消失，policy 停止學習，最終只收斂到單一因子 (如 ATR)

## 根因
1. **group_size 太小 (16)**：樣本不足以產生 reward 分佈多樣性
2. **entropy_coef 太低 (0.08)**：探索不足，公式分佈過早收斂
3. **diversity_penalty 不夠強 (2.0)**：無法有效懲罰相似公式
4. **Spearman IC 本身在噪聲資料上區分度低**：多數公式 IC ≈ 0.03-0.05，差異在浮點誤差範圍內

## v5.9 權宜之計 (治標不治本)
```python
adv_std = advantages.std().item()
if adv_std < 1e-4:
    noise = torch.randn_like(advantages) * 0.1
    advantages = advantages + noise
```

## 根本修復方案 (v6.5 待驗證)

### 超參數調整
| 參數 | v5.9 | v6.5 建議 | 理由 |
|------|------|-----------|------|
| `group_size` | 16 | **64** | 4x 樣本，reward 分佈更豐富 |
| `entropy_coef` | 0.08 | **0.15** | 加強探索，延緩收斂 |
| `diversity_penalty` | 2.0 | **3.0** | 更強懲罰相似公式 |
| `gumbel_noise_scale` | 1.0 | **1.5** | sampling 更多樣 |
| `train_steps` | 8000 | **15000** | CPU 環境妥協值，給更多步數收斂 |

### 架構層面改進 (未來)
1. **Reward 替代指標**：Spearman IC → Sharpe / Calmar / 自定義風險調整報酬
2. **Baseline 改進**：group_mean → EMA baseline / value network critic
3. **Curriculum learning**：先易後難，漸進增加公式長度

## 驗證指標
- `adv_std` 全程 > 0.1
- `mean_r` 隨 step 上升
- 多 regime 產出不同因子公式
- 22 個因子 (含 TX_INST_NET_OI, MTX_RETAIL_OI, NASDAQ_CLOSE 等) 非零比例 > 50%

## 相關 Kernel
- v6.4: `mhhuang14/twstock-grpo-regime-aware-factor-training-v6-4` (失敗，advantage collapse)
- v6.5: 待推送 (上述超參數修復)