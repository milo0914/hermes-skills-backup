# AlphaGPT Core Architecture v3.1 Implementation

Implementation notes for the core design patterns added to `grpo_regime_training_kaggle.py`.

## 1. LoopedTransformer (L749-915)

Built inside `build_looped_transformer(config)` factory function. All sub-classes are local to this function (Kaggle self-contained design).

### Component Hierarchy

```
LoopedTransformer
├── tok_emb: Embedding(vocab_size, d_model)
├── pos_emb: Embedding(max_formula_len, d_model)
├── blocks: ModuleList[LoopedTransformerBlock × num_layers]
│   └── LoopedTransformerBlock
│       ├── norm1: RMSNorm(d_model)
│       ├── attn: QKNormAttention(d_model, nhead)
│       ├── norm2: RMSNorm(d_model)
│       └── ffn: SwiGLU(d_model, dim_feedforward)
├── final_norm: RMSNorm(d_model)
└── mtp_head: MTPHead(d_model, vocab_size)
```

### Forward Pass

```python
# 1. Embed
h = tok_emb(x) + pos_emb(pos)

# 2. Loop (num_loops=3): cycle through blocks repeatedly
for _ in range(num_loops):
    for block in blocks:
        h = block(h, mask)

# 3. Final norm
h = final_norm(h)

# 4. MTPHead: per-position logits + value estimate
logits_per_pos = mtp_head.head_mean(h)  # (B, T, vocab)
value = mtp_head.head_critic(h.mean(dim=1)).squeeze(-1)  # (B,)
```

### Key Design Decisions

- **Pre-norm residual**: `x = x + attn(norm1(x))` — more stable than post-norm
- **MTPHead logits_per_pos**: Uses `head_mean(h)` directly for per-position logits (not the gated fusion). Gated fusion output is used for value estimation only. This allows autoregressive generation to pick next token from any position.
- **Loop count**: 3 loops with 2 layers = equivalent depth of 6-layer transformer, but with only 2 layers of parameters (parameter-efficient)

## 2. RMSNorm

```python
class RMSNorm(nn.Module):
    def forward(self, x):
        rms = sqrt(mean(x^2, dim=-1) + eps)
        return weight * (x / rms)
```

Why not LayerNorm: No centering (subtract mean), only scaling. More stable for small models, no mean-shift issue.

## 3. SwiGLU

```python
class SwiGLU(nn.Module):
    def forward(self, x):
        gate = SiLU(w_gate(x))  # SiLU = Swish = x * sigmoid(x)
        up = w_up(x)
        return dropout(w_down(gate * up))
```

Why not standard FFN: Gated architecture provides richer expressiveness with same parameter budget. Used in LLaMA, PaLM.

## 4. QKNormAttention

```python
class QKNormAttention(nn.Module):
    def forward(self, x):
        q = q_norm(w_q(x))  # RMSNorm on queries
        k = k_norm(w_k(x))  # RMSNorm on keys
        attn = softmax(q @ k.T * scale)
        return w_o(attn @ v)
```

Why: Prevents QK dot product explosion in small models. Without QK-norm, attention logits can grow unbounded, causing training instability.

## 5. Newton-Schulz Low-Rank Decay (LoRD) (L1237-1277)

Replaces SVD-based low-rank regularization.

### Algorithm

```python
# Newton-Schulz iteration: converges to nearest orthogonal matrix Q
# X_{k+1} = 0.5 * X_k * (3I - X_k^T X_k)
X = W / ||W||  # normalize for convergence
for _ in range(3):
    X = 0.5 * X @ (3*I - X.T @ X)
low_rank = W - X * ||W||  # residual = low-rank component
W -= lord_decay * low_rank  # decay low-rank part
```

### Complexity

- SVD: O(n^3) — prohibitive for frequent application
- Newton-Schulz: O(n^2 * k_iter) where k_iter=3 — GPU-friendly matrix multiplies
- Applied every 10 steps, lord_decay=1e-3

## 6. StableRankMonitor (L1280-1336)

```python
stable_rank(W) = ||W||_F^2 / ||W||_2^2
```

- Frobenius norm: exact via `(W**2).sum()`
- Spectral norm: approximated via power iteration (10 steps) — avoids SVD
- Reports avg/min/max stable rank across all weight matrices
- Checked every 500 steps
- Low stable rank (< 2) indicates parameter degeneracy → increase lord_decay

## 7. robust_normalize (L1339-1370)

Rolling window normalization using median + MAD instead of mean + std.

```python
for each window of 20 days:
    med = median(segment)
    mad = median(|segment - med|)
    normalized[i] = (x[i] - med) / (1.4826 * mad)
```

- 1.4826 factor: makes MAD ≈ std for Gaussian data
- More robust to outliers than z-score (a single extreme value won't shift median/MAD much)
- First `window` periods use global statistics as fallback
- Used in feature engineering to handle non-stationary financial time series

## 8. GRPO Training Loop (L940-1136)

### Group-Relative Advantage

```python
# Within each group of G formulas:
advantages = (rewards - rewards.mean()) / (rewards.std() + 1e-8)
```

### Clipped Importance Sampling

```python
ratio = torch.exp(log_probs - old_log_probs)
clipped_ratio = torch.clamp(ratio, 1 - clip_eps, 1 + clip_eps)
surrogate = torch.min(ratio * advantages, clipped_ratio * advantages)
grpo_loss = -surrogate.mean()
```

### Full Training Step

1. Sample batch → get features tensor (B, T, F)
2. Autoregressive generation: for each position, model outputs logits → sample token → append
3. StackVM executes generated formulas → get alpha signals
4. Compute rewards (IC + fitness + overfit penalty)
5. Group-relative advantage normalization
6. Forward pass to get log_probs for each token
7. Clipped GRPO loss
8. Backprop + Adam step
9. Every 10 steps: apply LoRD decay
10. Every 500 steps: StableRankMonitor check
11. Every N steps: walk-forward validation check

## Patch Tool Indentation Warning

When using the `patch` tool to replace multi-line blocks (>30 lines) in Python files, indentation can silently corrupt (4-space → 1-space). This happened twice during implementation.

**Mitigation**: 
1. After any large patch, immediately run `py_compile.compile(file, doraise=True)`
2. If corrupted, use a Python script to read the file, find the damaged region by line number, and rewrite it with correct indentation
3. Consider using `skill_manage action=write_file` for a complete replacement script rather than incremental patches for methods >50 lines
