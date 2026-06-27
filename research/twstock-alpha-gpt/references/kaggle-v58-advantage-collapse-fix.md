# Kaggle V5.8 Advantage Collapse Guard 修復

## 版本資訊
- Slug: `mhhuang14/grpo-regime-aware-factor-training-v5-8`
- 基於: v5.7 source (min-max advantage + REINFORCE)
- 狀態: **CANCEL_ACKNOWLEDGED**
- GPU: 指定 T4 但實際分配到不相容 GPU → CPU fallback

## v5.8 三處修復

### 1. Advantage Collapse Guard
偵測 advantage std ≈ 0 時注入隨機擾動：
```python
if adv_std < 1e-6:
    advantages = np.random.uniform(-1, 1, size=G)
    print(f"[v5.8] Advantage collapse detected (std={adv_std:.2e}), injecting random exploration")
```

### 2. Entropy Coef 提升
- v5.7: entropy_coef=0.01
- v5.8: entropy_coef=0.05 (5 倍增幅)

### 3. Batch Entropy
使用實際生成 logits 計算 entropy（非 dummy zeros input）：
```python
# 收集生成過程中的 logits
_all_logits.append(logits)
# 迴圈結束後計算 batch entropy
self._last_logits = torch.cat(_all_logits, dim=0)
entropy = torch.distributions.Categorical(logits=self._last_logits[:, -1, :]).entropy().mean()
loss -= entropy_coef * entropy
```

## 實測結果（v5.8 logs）

### 核心問題：仍跑 CPU
```
[GRPOConfig] CUDA 不相容，使用 CPU: G=4, batch=16, steps=3000
```
T4 GPU 指定無效，Kaggle 分配到不相容 GPU → fallback CPU。

### 只有 1 個 regime 訓練
```
[Multi-Regime] 分群結果:
mid_cap_tech: [2882]
```
4 檔股票中只有 2882 被歸到 mid_cap_tech，其他 3 regime 完全沒出現。

### Advantage Collapse 反覆觸發
```
step 0: loss=2.1393 mean_r=-0.250 best_r=0.003
step 500: loss=-0.0047 mean_r=1.100 best_r=1.100
[v5.8] Advantage collapse detected (std=0.00e+00), injecting random exploration
[v5.8] Advantage collapse detected (std=0.00e+00), injecting random exploration
... (反覆觸發數十次)
```

### 根因分析

1. **CPU G=4 太小**：4 個候選公式中，模型快速坍縮到同一個公式，所有 reward 完全相同 → std=0 → advantage=0
2. **隨機擾動只是暫時緩解**：注入隨機 advantage 後模型會短暫探索，但很快又坍縮回同一公式
3. **Entropy bonus 量級不足**：即使 coef=0.05，在 loss=-0.0047 的量級下，entropy 的影響仍然有限
4. **Regime 分類問題**：合成數據只有 4 檔，但只歸類出 mid_cap_tech 1 個 regime

## 待解決問題 (v5.9 方向)

### 方案 A: 確保取得 T4 GPU
- Kaggle Web UI 手動選擇 T4（最可靠）
- 或 `--accelerator nvidia-tesla-t4` 參數（不保證）
- T4 (sm_75) 通過 `cc[0] >= 7` 檢查

### 方案 B: CPU 模式根本修復
1. **G=16（最小）**：增大 group_size，減少坍縮機率
2. **Logits 噪聲注入**：在 softmax 前對 logits 加 Gumbel noise，而非事後對 advantages 注入
3. **Temperature scheduling**：起始 high temperature (探索) → 逐步降溫 (利用)
4. **Diversity penalty**：同一 group 內公式相似度 > 0.9 → 懲罰
5. **Elite 保留 + 其餘重新生成**：保留 top-1 公式，其餘 G-1 個重新生成

### 方案 C: 簡化架構
1. 去掉 Looped Transformer（CPU 太慢），改用更小的 MLP
2. 直接優化 factor weights（不做 StackVM 公式生成）
3. 先用 rule-based 驗證 pipeline，再逐步加入 GRPO

## 歷史版本對照

| 版本 | 修復內容 | 結果 | 根因 |
|------|---------|------|------|
| v5.5 | PPO (未合入 REINFORCE) | COMPLETE 但 loss=0 | PPO ratio≡1 + adv mean=0 |
| v5.6 | REINFORCE + zero-mean adv | CANCELLED | adv mean=0 → loss≈0 |
| v5.7 | min-max adv + sm_50 GPU | CANCELLED | P100 sm_60 不相容 → CPU → 坍縮 |
| v5.8 | adv collapse guard + entropy 0.05 | CANCEL_ACKNOWLEDGED | CPU G=4 坍縮持續觸發 |

## 結論

v5.8 的 advantage collapse guard 是治標不治本。隨機擾動注入可以打破死循環，但模型會立即重新坍縮。根本解決方案是：
1. **取得 T4 GPU** — G=16 + CUDA 運算速度足夠支撐有效探索
2. 或 **CPU 模式下根本改變生成策略** — 從純 autoregressive 改為 diverse sampling
