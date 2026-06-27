# GRPO v3.4 NaN Logits 穩定性修復

## 症狀

```
ValueError: Expected parameter logits to satisfy constraint Real(), 
but found invalid values: tensor([nan, nan, nan, ...])
```

Kaggle kernel v3.3 在 warmup 階段第一次 forward pass 即產生 NaN logits。

## 根因分析

1. **Looped Transformer 數值爆炸**：3 loops × 2 layers + d_model=64，配合 lr=1e-3，梯度/激活值在多層循環中累積膨脹
2. **未正規化特徵加劇**：ABSORPTION mean=14639（原始值量級）進入 embedding 層，放大數值爆炸
3. **無 NaN 保護**：logits 直接送入 `Categorical(logits=...)`，遇到 NaN 立即崩潰
4. **無梯度縮放**：未使用 GradScaler，FP16 混合精度下梯度不穩定

## v3.4 修復方案（6 層防護）

### 1. _safe_logits 函數（模組級別）

```python
def _safe_logits(logits):
    if torch.isnan(logits).any() or torch.isinf(logits).any():
        logits = torch.nan_to_num(logits, nan=0.0, posinf=1e6, neginf=-1e6)
    logits = torch.clamp(logits, -88, 88)
    return logits
```

所有 Categorical 調用處都包裹（5 處：warmup、guided_generate、fallback、entropy、dist 構建）。

### 2. 降低學習率 + 減少 Loops

```python
lr: 1e-3 → 3e-4
num_loops: 3 → 2
```

### 3. GradScaler

```python
scaler = torch.amp.GradScaler('cuda')
# Training loop:
scaler.scale(loss).backward()
scaler.unscale_(optimizer)
torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
scaler.step(optimizer)
scaler.update()
```

### 4. Weight Decay

```python
optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-2)
```

### 5. Advantages NaN 保護 + Clamp

```python
advantages = torch.where(torch.isnan(advantages), torch.zeros_like(advantages), advantages)
advantages = torch.clamp(advantages, -10, 10)
```

### 6. Loss / 參數 NaN Guard

```python
# Loss NaN → skip step
if torch.isnan(loss) or torch.isinf(loss):
    optimizer.zero_grad()
    continue

# 參數 NaN → reinitialize model
for p in model.parameters():
    if torch.isnan(p).any():
        model = build_looped_transformer(config)
        optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-2)
        break
```

## 本地驗證

zscore 正規化邏輯本地測試通過：
- Raw ABSORPTION: mean=13170.6, std=10689.3
- Zscore ABSORPTION: mean=0.0077, std=0.9714

證明 Kaggle log 的 mean=14639 是欄位流程問題（pitfall #29/#42），NaN logits 則是模型數值穩定性問題（獨立但互相加劇）。

## 教訓

1. **任何 Categorical 分佈構建前必須經過 _safe_logits** — 不只是 warmup，所有路徑都需要
2. **Looped Transformer 的 loops 參數是數值穩定性的關鍵變數** — loops=3 在 lr=1e-3 下不穩定，loops=2 + lr=3e-4 更安全
3. **NaN 可能獨立於特徵正規化問題** — 即使特徵正確，模型本身也可能爆 NaN
4. **patch() 工具的縮排損壞在此修復過程中反覆出現** — 每次修復都需要 write_file helper 腳本
5. **autopep8 無法修復結構性縮排損壞** — 只能用行號精確定位的 Python 修復腳本
