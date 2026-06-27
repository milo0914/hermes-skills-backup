# AlphaGPT 核心架構（原始程式碼分析）

來源：https://github.com/imbue-bit/AlphaGPT

## 架構總覽

```
data_pipeline/ → model_core/ → strategy_manager/ → execution/
   (數據管線)      (因子挖掘)      (策略管理)        (交易執行)
```

## model_core/ 核心模組

### 1. vocab.py - 公式詞彙表

```python
FEATURE_NAMES = ("RET", "LIQ_SCORE", "PRESSURE", "FOMO", "DEV", "LOG_VOL")
# 6 個特徵 + 12 個算子 = 18 個 token
# token_id 0-5 = 特徵，6-17 = 算子
```

### 2. ops.py - 算子定義

```python
OPS_CONFIG = [
    ('ADD', lambda x, y: x + y, 2),        # 二元
    ('SUB', lambda x, y: x - y, 2),        # 二元
    ('MUL', lambda x, y: x * y, 2),        # 二元
    ('DIV', lambda x, y: x/(y+1e-6), 2),   # 二元
    ('NEG', lambda x: -x, 1),              # 一元
    ('ABS', torch.abs, 1),                 # 一元
    ('SIGN', torch.sign, 1),               # 一元
    ('GATE', _op_gate, 3),                 # 三元：condition>0選x否則y
    ('JUMP', _op_jump, 1),                 # 一元：zscore>3極端跳變
    ('DECAY', _op_decay, 1),               # 一元：t+0.8*lag1+0.6*lag2
    ('DELAY1', lambda x: _ts_delay(x,1), 1), # 一元：滯後1期
    ('MAX3', max3_fn, 1),                  # 一元：近3期最大值
]
```

### 3. vm.py - StackVM 堆疊虛擬機

```python
class StackVM:
    def execute(self, formula_tokens, feat_tensor):
        # 堆疊執行：遇到特徵push，遇到算子pop運算再push
        # 輸入：formula_tokens=[0, 8, 1, 9, 4]
        # 解讀：push RET, push LIQ_SCORE, ADD, push FOMO, MUL
        # 結果：RET + LIQ_SCORE) * FOMO → 因子信號 tensor
        # 失敗返回 None
```

### 4. factors.py - 特徵工程

```python
class FeatureEngineer:
    # 6 維基礎因子（使用 robust_norm 正規化）
    @staticmethod
    def compute_features(raw_dict):
        ret = log(close / close_lag1)
        liq_score = liquidity / (fdv + 1e-6)
        pressure = tanh(3 * (close - open) / (high - low))
        fomo = vol_chg - vol_chg_lag1
        dev = (close - ma20) / ma20
        log_vol = log1p(volume)

class AdvancedFactorEngineer:
    # 12 維擴展因子（額外增加）
    vol_cluster, momentum_rev, rel_strength, hl_range, close_pos, vol_trend

class MemeIndicators:
    # 原始指標計算邏輯
    liquidity_health(), buy_sell_imbalance(), fomo_acceleration(),
    pump_deviation(), volatility_clustering(), momentum_reversal(),
    relative_strength()
```

### 5. alphagpt.py - Transformer 模型

```python
class AlphaGPT(nn.Module):
    # 小型 Looped Transformer
    d_model=64, nhead=4, num_layers=2, dim_feedforward=128, num_loops=3
    # Token Embedding + Positional Embedding
    # LoopedTransformer (循環處理，每層內部迭代3次)
    # RMSNorm (非 LayerNorm)
    # SwiGLU (非標準 FFN)
    # QKNorm (Query-Key 正規化)
    # MTPHead (多任務池化輸出)
    # head_critic (價值估計)

class NewtonSchulzLowRankDecay:
    # LoRD 正則化：Newton-Schulz 疊代計算低秩方向
    # 針對 qk_norm, attention 參數
    # 比 SVD 更高效

class StableRankMonitor:
    # 監控參數的穩定秩 (stable rank)
    # 用於判斷模型是否過擬合
```

### 6. engine.py - 訓練引擎

```python
class AlphaEngine:
    def train(self):
        for step in range(TRAIN_STEPS):
            # 1. 自回歸生成公式 token 序列
            inp = zeros(batch, 1)
            for _ in range(MAX_FORMULA_LEN):
                logits, value, task_probs = model(inp)
                action = Categorical(logits).sample()
                inp = cat([inp, action])

            # 2. StackVM 執行每條公式
            for i in range(batch):
                res = vm.execute(formula, feat_tensor)
                if res is None: reward = -5.0  # 無效公式
                elif res.std() < 1e-4: reward = -2.0  # 常數公式
                else: reward = backtest.evaluate(res)  # 回測評分

            # 3. REINFORCE 策略梯度
            adv = (rewards - mean) / (std + 1e-5)
            loss = -sum(log_probs * adv).mean()
            loss.backward(); optimizer.step()

            # 4. 可選 LoRD 正則化
            if use_lord: lord_opt.step()
```

### 7. backtest.py - 回測評分

```python
class MemeBacktest:
    def evaluate(self, factors, raw_data, target_ret):
        signal = sigmoid(factors)
        position = (signal > 0.85) * is_safe  # 建倉條件
        # 扣除手續費 + 滑點
        # score = cum_ret - 2.0 * big_drawdowns
        # 低活動度懲罰
        final_fitness = median(score)
```

### 8. data_loader.py - 數據載入

```python
class CryptoDataLoader:
    # 從 Postgres/TimescaleDB 載入 OHLCV
    # 轉換為 tensor[batch=代幣數, features, time]
    # 計算 target_ret = log(open_t+2 / open_t+1)
```

## 關鍵設計決策

1. **不預測價格**：生成因子公式而非直接預測
2. **可解釋性**：公式 token 可反編譯為人類可讀表達式
3. **強化學習**：用回測報酬作為獎勵信號
4. **小模型**：d_model=64，2層，適合快速迭代
5. **LoRD 正則化**：防止 attention 過擬合的低秩衰減

---

## v2 架構變更 (2026-06-07)

### 因子正規化修正

原始 AlphaGPT `robust_norm` 使用全局 median/MAD → 前視偏差。

台股版修正為 rolling window (60天) + expanding fallback：
```python
# 舊版 (前視偏差)
median = g[feat].median()
mad = (g[feat] - median).abs().median() + 1e-6

# 新版 (無前視偏差)
rolling_median = g[feat].rolling(60, min_periods=20).median()
rolling_mad = (g[feat] - rolling_median).abs().rolling(60, min_periods=20).median() + 1e-6
```

### GRPO 替代 REINFORCE

基於 DeepSeek-R1 的 GRPO (Group Relative Policy Optimization)：
- 不需要 value network (critic)
- Group relative reward：同 batch 公式互相比較
- Clipped importance sampling：穩定 off-policy 更新
- 過擬合懲罰直接嵌入 reward

```
REINFORCE:  loss = -sum(log_probs * (R - baseline))
GRPO:       loss = -sum(ratio * A_group)  where A_group = (R_i - mean(R_group)) / std(R_group)
```

參見 `scripts/grpo_alpha_trainer.py`

### 過擬合防護五層架構

```
L1: TimeSeriesSplitter (train/val/test)
L2: WalkForwardValidator (rolling/expanding/sliding)
L3: OverfitPenalty (IC gap + turnover + sharpe decay)
L4: FactorStabilityChecker (IC decay / turnover / long-short symmetry)
L5: PurgedKFoldCV (embargo=7d)
```

參見 `scripts/anti_overfit.py`

### 回測修正

| 修正項 | 舊版 | 新版 |
|--------|------|------|
| 持倉出場 | 固定 head(7) | ATR止損 + 移動止損 + 時間止損 |
| 交易成本 | fee+tax (一次) | 買入手續費 + 賣出手續費 + 交易稅 + 雙邊滑點 |
| 夏普年化 | sqrt(252) | sqrt(252/avg_holding_days) |
