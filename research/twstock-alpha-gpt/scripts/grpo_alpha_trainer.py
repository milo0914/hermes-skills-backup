"""
台股 AI Dig Money — GRPO 因子訓練框架

基於 DeepSeek-R1 的 GRPO (Group Relative Policy Optimization) 改寫 AlphaGPT 的 REINFORCE 訓練。

關鍵差異 vs 原始 REINFORCE：
1. 用 Group Relative Reward 替代 critic baseline — 更穩定
2. 每步生成 G 個公式候選並比較 — 天然的策略搜索
3. 過擬合懲罰嵌入獎勵函數 — 直接約束模型

架構：
    AlphaGPT Transformer → 生成 G 個公式 token 序列
    → StackVM 執行每個公式 → 回測評分
    → 過擬合懲罰 → GRPO 獎勵
    → 策略梯度更新

與 anti_overfit.py 的整合：
    - OverfitPenalty 計算 IC gap / turnover 懲罰
    - FactorStabilityChecker 驗證生成因子的穩定性
    - WalkForwardValidator 用於最終策略選擇
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


# ============================================================
# 1. GRPO 訓練配置
# ============================================================

@dataclass
class GRPOConfig:
    """GRPO 訓練配置"""
    # Group size: 每步生成幾個候選公式
    group_size: int = 4  # G=4 for CPU, G=8 for GPU

    # 模型參數 (繼承 AlphaGPT)
    d_model: int = 64
    nhead: int = 4
    num_layers: int = 2
    dim_feedforward: int = 128
    num_loops: int = 3
    vocab_size: int = 28  # 16 factors + 12 operators
    max_formula_len: int = 15

    # 訓練參數
    batch_size: int = 16  # CPU default
    train_steps: int = 1000
    lr: float = 1e-3
    entropy_coef: float = 0.01  # 鼓勵探索

    # GRPO 特有
    reward_clip: float = 5.0  # clip reward to [-5, 5]
    advantage_clip: float = 3.0  # clip advantage

    # 過擬合防護
    use_overfit_penalty: bool = True
    ic_gap_threshold: float = 0.05
    ic_gap_weight: float = 2.0
    turnover_weight: float = 0.5
    turnover_max: float = 0.3

    # LoRD 正則化
    use_lord: bool = True
    lord_decay: float = 1e-3

    # 設備
    device: str = "cpu"

    @classmethod
    def auto_detect(cls) -> "GRPOConfig":
        """自動偵測 GPU 並調整參數"""
        config = cls()
        try:
            import torch
            if torch.cuda.is_available():
                config.device = "cuda"
                config.group_size = 8
                config.batch_size = 128
                config.train_steps = 20000
                print(f"[GRPO Auto] GPU: {torch.cuda.get_device_name(0)}")
            else:
                config.device = "cpu"
                config.group_size = 4
                config.batch_size = 16
                config.train_steps = 1000
                print("[GRPO Auto] CPU mode")
        except ImportError:
            print("[GRPO Auto] PyTorch not installed, CPU mode")
        return config


# ============================================================
# 2. 公式詞彙表 (與 ai_dig_money_core.py 對齊)
# ============================================================

FEATURE_NAMES = (
    "RET", "LIQ_SCORE", "PRESSURE", "FOMO", "DEV", "LOG_VOL",
    "INST_FLOW", "MARGIN_PRESS", "FIVE_DAY_HIGH", "VOL_BREAKOUT",
    "CVD_PROXY", "ABSORPTION", "SURF_ENTRY", "ATR", "CLOSE_POS", "MOM_REV",
)

OPERATOR_NAMES = (
    "ADD", "SUB", "MUL", "DIV", "NEG", "ABS",
    "SIGN", "GATE", "JUMP", "DECAY", "DELAY1", "MAX3",
)

OPERATOR_ARITY = [2, 2, 2, 2, 1, 1, 1, 3, 1, 1, 1, 1]

VOCAB_SIZE = len(FEATURE_NAMES) + len(OPERATOR_NAMES)  # 28


# ============================================================
# 3. StackVM (公式執行虛擬機)
# ============================================================

class StackVM:
    """
    堆疊虛擬機 — 執行公式 token 序列

    遇到特徵 token → push 特徵值
    遇到算子 token → pop 參數，計算，push 結果
    執行失敗（堆疊不足）→ 返回 None
    """

    def execute(self, tokens: List[int], feat_tensor: np.ndarray) -> Optional[np.ndarray]:
        """
        執行公式

        Args:
            tokens: token 序列 (e.g. [0, 1, 16, 3, 18])
            feat_tensor: 特徵矩陣 (n_features, n_samples)

        Returns:
            因子信號 (n_samples,) 或 None（無效公式）
        """
        n_features = len(FEATURE_NAMES)
        stack = []

        for t in tokens:
            if t < n_features:
                # Push feature
                stack.append(feat_tensor[t].copy())
            else:
                op_idx = t - n_features
                if op_idx >= len(OPERATOR_NAMES):
                    return None

                arity = OPERATOR_ARITY[op_idx]
                if len(stack) < arity:
                    return None

                if arity == 1:
                    a = stack.pop()
                    stack.append(self._apply_unary(op_idx, a))
                elif arity == 2:
                    b = stack.pop()
                    a = stack.pop()
                    stack.append(self._apply_binary(op_idx, a, b))
                elif arity == 3:
                    c = stack.pop()
                    b = stack.pop()
                    a = stack.pop()
                    stack.append(self._apply_ternary(op_idx, a, b, c))

        return stack[0] if len(stack) == 1 else None

    @staticmethod
    def _apply_unary(op_idx: int, a: np.ndarray) -> np.ndarray:
        ops = {
            4: lambda x: -x,                    # NEG
            5: lambda x: np.abs(x),             # ABS
            6: lambda x: np.sign(x),            # SIGN
            8: lambda x: np.where(              # JUMP: zscore > 3
                np.abs((x - np.mean(x)) / (np.std(x) + 1e-6)) > 3,
                np.sign(x), 0),
            9: lambda x: 0.8 * x + 0.6 * np.roll(x, 1),  # DECAY
            10: lambda x: np.roll(x, 1),         # DELAY1
            11: lambda x: np.maximum(            # MAX3
                np.maximum(x, np.roll(x, 1)), np.roll(x, 2)),
        }
        return ops.get(op_idx, lambda x: x)(a)

    @staticmethod
    def _apply_binary(op_idx: int, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        ops = {
            0: lambda x, y: x + y,               # ADD
            1: lambda x, y: x - y,               # SUB
            2: lambda x, y: x * y,               # MUL
            3: lambda x, y: x / (y + 1e-6),     # DIV
        }
        return ops.get(op_idx, lambda x, y: x)(a, b)

    @staticmethod
    def _apply_ternary(op_idx: int, a: np.ndarray, b: np.ndarray,
                       c: np.ndarray) -> np.ndarray:
        # GATE: if c > 0 then a else b
        if op_idx == 7:
            return np.where(c > 0, a, b)
        return a


# ============================================================
# 4. GRPO 獎勵計算
# ============================================================

class GRPORewardCalculator:
    """GRPO 獎勵計算 — 含過擬合懲罰"""

    def __init__(self, config: GRPOConfig = None, backtest_fn=None):
        self.config = config or GRPOConfig()
        self.backtest_fn = backtest_fn or self._default_backtest
        self.vm = StackVM()

    def _default_backtest(self, signal: np.ndarray,
                          returns: np.ndarray) -> float:
        """預設回測：IC (Spearman 相關) 作為獎勵"""
        if signal is None or len(signal) != len(returns):
            return -5.0
        valid = np.isfinite(signal) & np.isfinite(returns)
        if valid.sum() < 10:
            return -5.0
        ic = pd.Series(signal[valid]).corr(
            pd.Series(returns[valid]), method="spearman"
        )
        if np.isnan(ic):
            return -5.0
        return ic * 10  # 放大 IC 到合理獎勵範圍

    def compute_group_rewards(self, group_tokens: List[List[int]],
                              feat_tensor: np.ndarray,
                              returns: np.ndarray,
                              train_ic: float = 0.0,
                              val_ic: float = 0.0,
                              daily_turnover: float = 0.0) -> Dict:
        """
        計算 GRPO Group Rewards

        Args:
            group_tokens: G 個公式 token 序列
            feat_tensor: 特徵矩陣
            returns: 前向報酬
            train_ic/val_ic: 用於過擬合懲罰
            daily_turnover: 換手率

        Returns:
            {rewards, advantages, valid_mask, overfit_info}
        """
        G = len(group_tokens)
        rewards = []

        for tokens in group_tokens:
            signal = self.vm.execute(tokens, feat_tensor)

            if signal is None:
                rewards.append(-5.0)  # 無效公式
                continue

            if np.std(signal) < 1e-4:
                rewards.append(-2.0)  # 常數公式
                continue

            base_reward = self.backtest_fn(signal, returns)

            # 過擬合懲罰
            if self.config.use_overfit_penalty:
                ic_gap = max(0, train_ic - val_ic - self.config.ic_gap_threshold)
                ic_penalty = self.config.ic_gap_weight * ic_gap
                turnover_penalty = self.config.turnover_weight * \
                    max(0, daily_turnover - self.config.turnover_max)
                base_reward -= (ic_penalty + turnover_penalty)

            # Clip reward
            rewards.append(np.clip(base_reward,
                                   -self.config.reward_clip,
                                   self.config.reward_clip))

        rewards = np.array(rewards)
        valid_mask = rewards > -5.0

        # Group Relative Advantage: (r - mean) / (std + eps)
        if valid_mask.sum() > 1:
            group_mean = rewards[valid_mask].mean()
            group_std = rewards[valid_mask].std() + 1e-6
            advantages = (rewards - group_mean) / group_std
        else:
            advantages = np.zeros(G)

        # Clip advantages
        advantages = np.clip(advantages,
                             -self.config.advantage_clip,
                             self.config.advantage_clip)

        overfit_info = {
            "train_ic": train_ic,
            "val_ic": val_ic,
            "ic_gap": train_ic - val_ic,
            "is_overfit": (train_ic - val_ic) > 0.1,
        }

        return {
            "rewards": rewards,
            "advantages": advantages,
            "valid_mask": valid_mask,
            "overfit_info": overfit_info,
            "group_mean_reward": rewards[valid_mask].mean() if valid_mask.sum() > 0 else 0.0,
            "best_idx": int(np.argmax(rewards)) if len(rewards) > 0 else 0,
        }


# ============================================================
# 5. GRPO 訓練器 (PyTorch Optional)
# ============================================================

class GRPOAlphaTrainer:
    """
    GRPO 因子訓練器

    依賴 PyTorch（可選）。若無 PyTorch，可使用 numpy 模式進行
    簡化的策略搜索（無梯度，僅隨機搜索 + GRPO 評分）。

    訓練流程：
    1. 準備特徵矩陣 + 前向報酬
    2. 生成 G 個公式候選
    3. StackVM 執行 + 回測
    4. GRPO Group Reward + 過擬合懲罰
    5. 策略梯度更新（或隨機搜索選優）
    6. 驗證集 IC 檢查
    7. 保留 best_strategy
    """

    def __init__(self, config: GRPOConfig = None):
        self.config = config or GRPOConfig.auto_detect()
        self.vm = StackVM()
        self.reward_calc = GRPORewardCalculator(self.config)
        self.model = None
        self.optimizer = None
        self.best_formula = None
        self.best_reward = -float("inf")
        self.history = []

    def _try_init_torch(self):
        """嘗試初始化 PyTorch 模型"""
        try:
            import torch
            import torch.nn as nn

            class LoopedTransformer(nn.Module):
                def __init__(self, cfg):
                    super().__init__()
                    self.tok_emb = nn.Embedding(cfg.vocab_size, cfg.d_model)
                    self.pos_emb = nn.Embedding(cfg.max_formula_len, cfg.d_model)
                    encoder_layer = nn.TransformerEncoderLayer(
                        d_model=cfg.d_model,
                        nhead=cfg.nhead,
                        dim_feedforward=cfg.dim_feedforward,
                        batch_first=True,
                    )
                    self.encoder = nn.TransformerEncoder(
                        encoder_layer, num_layers=cfg.num_layers
                    )
                    self.head_alpha = nn.Linear(cfg.d_model, cfg.vocab_size)
                    self.head_critic = nn.Linear(cfg.d_model, 1)
                    self.num_loops = cfg.num_loops

                def forward(self, x):
                    B, T = x.shape
                    pos = torch.arange(T, device=x.device).unsqueeze(0)
                    h = self.tok_emb(x) + self.pos_emb(pos)
                    for _ in range(self.num_loops):
                        h = self.encoder(h)
                    logits = self.head_alpha(h)
                    value = self.head_critic(h.mean(dim=1))
                    return logits, value.squeeze(-1)

            self.model = LoopedTransformer(self.config).to(self.config.device)
            self.optimizer = torch.optim.Adam(
                self.model.parameters(), lr=self.config.lr
            )
            return True
        except ImportError:
            return False

    def train_numpy(self, feat_tensor: np.ndarray, returns: np.ndarray,
                    val_feat: np.ndarray = None, val_returns: np.ndarray = None,
                    n_iterations: int = 100) -> dict:
        """
        Numpy 模式訓練（無 PyTorch）

        使用隨機搜索 + GRPO 評分：
        1. 每輪隨機生成 G 個公式
        2. GRPO 評分
        3. 保留最佳公式
        4. 基於最佳公式做變異搜索
        """
        print(f"[GRPO Numpy] 開始訓練, iterations={n_iterations}, "
              f"G={self.config.group_size}")

        best_formula = None
        best_reward = -float("inf")
        history = []

        for iteration in range(n_iterations):
            # 生成 G 個候選公式
            group_tokens = self._generate_group(
                self.config.group_size, best_formula
            )

            # 計算 train/val IC
            train_ic = self._compute_ic(group_tokens, feat_tensor, returns)
            val_ic = self._compute_ic(group_tokens, val_feat, val_returns) \
                if val_feat is not None else 0.0

            # GRPO Group Reward
            result = self.reward_calc.compute_group_rewards(
                group_tokens, feat_tensor, returns,
                train_ic=train_ic, val_ic=val_ic,
            )

            # 追蹤最佳
            best_idx = result["best_idx"]
            if result["rewards"][best_idx] > best_reward:
                best_reward = result["rewards"][best_idx]
                best_formula = group_tokens[best_idx]

            history.append({
                "iteration": iteration,
                "group_mean": result["group_mean_reward"],
                "best_reward": result["rewards"][best_idx],
                "valid_ratio": result["valid_mask"].mean(),
                "overfit": result["overfit_info"]["is_overfit"],
            })

            if iteration % 20 == 0:
                print(f"  iter {iteration}: mean={result['group_mean_reward']:.3f} "
                      f"best={result['rewards'][best_idx]:.3f} "
                      f"valid={result['valid_mask'].mean():.1%} "
                      f"overfit={result['overfit_info']['is_overfit']}")

        self.best_formula = best_formula
        self.best_reward = best_reward
        self.history = history

        return {
            "best_formula": best_formula,
            "best_reward": best_reward,
            "n_iterations": n_iterations,
            "history": history,
        }

    def train_torch(self, feat_tensor: np.ndarray, returns: np.ndarray,
                    val_feat: np.ndarray = None,
                    val_returns: np.ndarray = None) -> dict:
        """
        PyTorch 模式訓練（完整 GRPO 策略梯度）

        需要 PyTorch 環境。在 Kaggle GPU 上執行。
        """
        if not self._try_init_torch():
            print("[GRPO] PyTorch 不可用，降級為 numpy 模式")
            return self.train_numpy(feat_tensor, returns,
                                    val_feat, val_returns)

        import torch
        import torch.nn.functional as F

        print(f"[GRPO Torch] 開始訓練, steps={self.config.train_steps}, "
              f"G={self.config.group_size}, device={self.config.device}")

        feat_t = torch.tensor(feat_tensor, dtype=torch.float32,
                              device=self.config.device)
        ret_t = torch.tensor(returns, dtype=torch.float32,
                             device=self.config.device)

        best_formula = None
        best_reward = -float("inf")
        history = []

        for step in range(self.config.train_steps):
            self.model.train()
            all_log_probs = []
            all_tokens = []

            # 生成 G 個公式
            for g in range(self.config.group_size):
                inp = torch.zeros(1, 1, dtype=torch.long,
                                  device=self.config.device)
                token_list = []
                log_probs = []

                for _ in range(self.config.max_formula_len):
                    logits, _ = self.model(inp)
                    dist = torch.distributions.Categorical(
                        logits=logits[:, -1, :]
                    )
                    action = dist.sample()
                    log_probs.append(dist.log_prob(action))
                    token_list.append(action.item())
                    inp = torch.cat([inp, action.unsqueeze(0).unsqueeze(0)],
                                    dim=1)

                all_tokens.append(token_list)
                all_log_probs.append(torch.stack(log_probs).sum())

            # GRPO Group Reward
            train_ic = self._compute_ic(all_tokens, feat_tensor, returns)
            val_ic = self._compute_ic(all_tokens, val_feat, val_returns) \
                if val_feat is not None else 0.0

            result = self.reward_calc.compute_group_rewards(
                all_tokens, feat_tensor, returns,
                train_ic=train_ic, val_ic=val_ic,
            )

            advantages = torch.tensor(
                result["advantages"], dtype=torch.float32,
                device=self.config.device
            )

            # GRPO loss: -sum(log_prob * advantage) / G
            log_probs_tensor = torch.stack(all_log_probs)
            loss = -(log_probs_tensor * advantages).mean()

            # Entropy bonus
            entropy = -sum(
                torch.distributions.Categorical(
                    logits=self.model(
                        torch.tensor([t], dtype=torch.long,
                                     device=self.config.device)
                    )[0][:, -1, :]
                ).entropy().item()
                for t in all_tokens[0] if len(t) > 0
            ) / max(len(all_tokens[0]), 1)
            loss -= self.config.entropy_coef * entropy

            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            self.optimizer.step()

            # LoRD regularization
            if self.config.use_lord:
                self._apply_lord_decay()

            # Track best
            best_idx = result["best_idx"]
            if result["rewards"][best_idx] > best_reward:
                best_reward = result["rewards"][best_idx]
                best_formula = all_tokens[best_idx]

            if step % 100 == 0:
                print(f"  step {step}: loss={loss.item():.4f} "
                      f"mean_r={result['group_mean_reward']:.3f} "
                      f"best_r={result['rewards'][best_idx]:.3f}")

            history.append({
                "step": step,
                "loss": loss.item(),
                "group_mean": result["group_mean_reward"],
                "best_reward": result["rewards"][best_idx],
                "overfit": result["overfit_info"]["is_overfit"],
            })

        self.best_formula = best_formula
        self.best_reward = best_reward
        self.history = history

        return {
            "best_formula": best_formula,
            "best_reward": best_reward,
            "history": history,
        }

    def _generate_group(self, G: int, seed_formula: List[int] = None,
                        feature_mask: np.ndarray = None,
                        operator_mask: np.ndarray = None,
                        feature_weights: np.ndarray = None,
                        ) -> List[List[int]]:
        """
        生成 G 個候選公式

        [v3] 支援 regime-aware 生成：
        - feature_mask: 遮罩不被選的特徵 (bool array[16])
        - operator_mask: 遮罩不被選的算子 (bool array[12])
        - feature_weights: 特徵採樣權重 (float array[16])
        """
        n_features = len(FEATURE_NAMES)
        group = []

        for g in range(G):
            if seed_formula is not None and g > 0 and np.random.random() < 0.5:
                # 變異搜索：基於最佳公式做小幅修改
                formula = self._mutate(seed_formula,
                                       feature_mask=feature_mask,
                                       operator_mask=operator_mask,
                                       feature_weights=feature_weights)
            else:
                # 隨機生成 (regime-aware)
                length = np.random.randint(3, self.config.max_formula_len)
                formula = self._random_formula(length,
                                               feature_mask=feature_mask,
                                               operator_mask=operator_mask,
                                               feature_weights=feature_weights)
            group.append(formula)
        return group

    def _random_formula(self, length: int,
                        feature_mask: np.ndarray = None,
                        operator_mask: np.ndarray = None,
                        feature_weights: np.ndarray = None) -> List[int]:
        """[v3] Regime-aware 隨機公式生成"""
        n_features = len(FEATURE_NAMES)

        # 建構可選 token 範圍
        if feature_mask is not None and operator_mask is not None:
            active_features = [i for i in range(n_features) if feature_mask[i]]
            active_ops = [n_features + i for i in range(len(OPERATOR_NAMES))
                          if operator_mask[i]]
            token_pool = active_features + active_ops
        else:
            token_pool = list(range(self.config.vocab_size))

        if len(token_pool) == 0:
            # Fallback: 全部 vocab
            token_pool = list(range(self.config.vocab_size))

        # 特徵加權採樣
        if feature_weights is not None and len(feature_weights) == n_features:
            # 對特徵 token 賦予權重
            weights = np.ones(self.config.vocab_size, dtype=np.float64)
            for i in range(n_features):
                if feature_mask is not None and not feature_mask[i]:
                    weights[i] = 0.0  # 被遮罩的特徵不採樣
                else:
                    weights[i] = max(feature_weights[i], 0.01)  # 最小權重

            # 非特徵 token (算子) 用均勻權重
            for i in range(n_features, self.config.vocab_size):
                op_idx = i - n_features
                if operator_mask is not None and op_idx < len(operator_mask):
                    if not operator_mask[op_idx]:
                        weights[i] = 0.0
                    else:
                        weights[i] = 1.0
                else:
                    weights[i] = 1.0

            # 確保至少有一個可選 token
            if weights.sum() < 1e-6:
                weights = np.ones(self.config.vocab_size, dtype=np.float64)

            weights /= weights.sum()

            formula = list(np.random.choice(
                self.config.vocab_size, size=length, p=weights
            ))
        else:
            # 無加權：從 token_pool 均勻採樣
            formula = [token_pool[np.random.randint(len(token_pool))]
                       for _ in range(length)]

        return formula

    def _mutate(self, formula: List[int],
                feature_mask: np.ndarray = None,
                operator_mask: np.ndarray = None,
                feature_weights: np.ndarray = None) -> List[int]:
        """[v3] Regime-aware 公式變異"""
        mutated = formula.copy()
        n_features = len(FEATURE_NAMES)
        n_mutations = max(1, len(mutated) // 3)

        for _ in range(n_mutations):
            if np.random.random() < 0.5 and len(mutated) > 1:
                # 替換一個 token (regime-aware)
                idx = np.random.randint(len(mutated))
                new_formula = self._random_formula(
                    1, feature_mask, operator_mask, feature_weights
                )
                mutated[idx] = new_formula[0]
            else:
                # 插入或刪除
                if np.random.random() < 0.5:
                    idx = np.random.randint(len(mutated))
                    new_token = self._random_formula(
                        1, feature_mask, operator_mask, feature_weights
                    )
                    mutated.insert(idx, new_token[0])
                elif len(mutated) > 2:
                    idx = np.random.randint(len(mutated))
                    mutated.pop(idx)
        return mutated

    def _compute_ic(self, group_tokens: List[List[int]],
                    feat_tensor: np.ndarray = None,
                    returns: np.ndarray = None) -> float:
        """計算 group 中最佳公式的 IC"""
        if feat_tensor is None or returns is None:
            return 0.0

        best_ic = 0.0
        for tokens in group_tokens:
            signal = self.vm.execute(tokens, feat_tensor)
            if signal is None or np.std(signal) < 1e-4:
                continue
            valid = np.isfinite(signal) & np.isfinite(returns)
            if valid.sum() < 10:
                continue
            ic = pd.Series(signal[valid]).corr(
                pd.Series(returns[valid]), method="spearman"
            )
            if not np.isnan(ic) and abs(ic) > abs(best_ic):
                best_ic = ic
        return best_ic

    def _apply_lord_decay(self):
        """LoRD 正則化：衰減權重的低秩方向"""
        try:
            import torch
            with torch.no_grad():
                for name, param in self.model.named_parameters():
                    if "weight" in name and param.dim() >= 2:
                        # 簡化版 LoRD: 小幅衰減奇異值
                        U, S, V = torch.svd_lowrank(param, q=min(4, min(param.shape)))
                        low_rank = U @ torch.diag(S) @ V.T
                        param.data -= self.config.lord_decay * low_rank
        except Exception:
            pass  # LoRD 是可選的，失敗不影響訓練

    def save_best(self, path: str = "best_strategy.json"):
        """儲存最佳公式"""
        import json
        if self.best_formula is not None:
            with open(path, "w") as f:
                json.dump(self.best_formula, f)
            print(f"[GRPO] 最佳公式已儲存至 {path}")

            # 反編譯
            from ai_dig_money_core import FormulaDecoder
            formula_str = FormulaDecoder.decode(self.best_formula)
            print(f"[GRPO] 公式: {formula_str}")
            print(f"[GRPO] 獎勵: {self.best_reward:.4f}")

    # ============================================================
    # [v3] Regime-Aware 訓練
    # ============================================================

    def train_regime_numpy(self, feat_tensor: np.ndarray,
                           returns: np.ndarray,
                           regime_plan: dict = None,
                           val_feat: np.ndarray = None,
                           val_returns: np.ndarray = None,
                           n_iterations: int = 100) -> dict:
        """
        [v3] Regime-aware numpy 模式訓練

        根據 StockRegime 訓練計畫，使用特徵權重/遮罩引導 GRPO 搜索

        Args:
            feat_tensor: 特徵矩陣 (n_features, n_samples)
            returns: 前向報酬
            regime_plan: 來自 RegimeTrainingPlan.create_plan()
            val_feat/val_returns: 驗證集
            n_iterations: 訓練迭代數

        Returns:
            {best_formula, best_reward, regime, history, ...}
        """
        # 提取 regime 參數
        feature_mask = None
        operator_mask = None
        feature_weights = None
        regime_name = "unknown"

        if regime_plan:
            feature_mask = regime_plan.get("feature_mask")
            operator_mask = regime_plan.get("operator_mask")
            feature_weights = regime_plan.get("feature_weights")
            regime_name = regime_plan.get("regime", "unknown")
            if hasattr(regime_name, "value"):
                regime_name = regime_name.value

            # 調整 group_size
            gs = regime_plan.get("group_size", self.config.group_size)
            if gs != self.config.group_size:
                print(f"[GRPO Regime] {regime_name}: "
                      f"group_size {self.config.group_size}→{gs}")
                self.config.group_size = gs

        print(f"[GRPO Regime Numpy] regime={regime_name}, "
              f"iterations={n_iterations}, G={self.config.group_size}")

        best_formula = None
        best_reward = -float("inf")
        history = []

        for iteration in range(n_iterations):
            # Regime-aware 生成
            group_tokens = self._generate_group(
                self.config.group_size, best_formula,
                feature_mask=feature_mask,
                operator_mask=operator_mask,
                feature_weights=feature_weights,
            )

            # 計算 IC
            train_ic = self._compute_ic(group_tokens, feat_tensor, returns)
            val_ic = self._compute_ic(group_tokens, val_feat, val_returns) \
                if val_feat is not None else 0.0

            # GRPO Group Reward
            result = self.reward_calc.compute_group_rewards(
                group_tokens, feat_tensor, returns,
                train_ic=train_ic, val_ic=val_ic,
            )

            # 追蹤最佳
            best_idx = result["best_idx"]
            if result["rewards"][best_idx] > best_reward:
                best_reward = result["rewards"][best_idx]
                best_formula = group_tokens[best_idx]

            history.append({
                "iteration": iteration,
                "regime": regime_name,
                "group_mean": result["group_mean_reward"],
                "best_reward": result["rewards"][best_idx],
                "valid_ratio": result["valid_mask"].mean(),
                "overfit": result["overfit_info"]["is_overfit"],
            })

            if iteration % 20 == 0:
                print(f" iter {iteration}: mean={result['group_mean_reward']:.3f} "
                      f"best={result['rewards'][best_idx]:.3f} "
                      f"valid={result['valid_mask'].mean():.1%} "
                      f"overfit={result['overfit_info']['is_overfit']}")

        self.best_formula = best_formula
        self.best_reward = best_reward
        self.history = history

        return {
            "best_formula": best_formula,
            "best_reward": best_reward,
            "regime": regime_name,
            "n_iterations": n_iterations,
            "history": history,
        }

    def train_multi_regime(self, stock_data_map: Dict[str, dict],
                           n_iterations_per_regime: int = 50) -> Dict[str, dict]:
        """
        [v3] 多 regime 分群訓練

        對每個 regime 分別訓練因子公式，回傳各 regime 的最佳公式

        Args:
            stock_data_map: {stock_id: {feat, returns, regime_plan, ...}}
            n_iterations_per_regime: 每個 regime 的訓練迭代數

        Returns:
            {stock_id: {best_formula, best_reward, regime, ...}}
        """
        from stock_regime import RegimeTrainingPlan, StockRegime

        results = {}

        # 按 regime 分群
        regime_groups: Dict[str, List[str]] = {}
        for stock_id, data in stock_data_map.items():
            regime_plan = data.get("regime_plan", {})
            regime = regime_plan.get("regime", StockRegime.MID_CAP_TECH)
            regime_key = regime.value if hasattr(regime, "value") else str(regime)
            if regime_key not in regime_groups:
                regime_groups[regime_key] = []
            regime_groups[regime_key].append(stock_id)

        print(f"[GRPO Multi-Regime] 分群結果:")
        for regime_key, stocks in regime_groups.items():
            print(f"  {regime_key}: {stocks}")

        # 逐 regime 訓練
        for regime_key, stocks in regime_groups.items():
            print(f"\n[GRPO Multi-Regime] 訓練 regime={regime_key} "
                  f"({len(stocks)} 檔)")

            # 合併同 regime 的數據
            all_feat = []
            all_returns = []
            regime_plan = None

            for stock_id in stocks:
                data = stock_data_map[stock_id]
                feat = data.get("feat")
                ret = data.get("returns")
                if feat is not None and ret is not None:
                    all_feat.append(feat)
                    all_returns.append(ret)
                if regime_plan is None:
                    regime_plan = data.get("regime_plan")

            if not all_feat:
                print(f"  [SKIP] 無有效數據")
                continue

            # 沿 sample 維度拼接
            combined_feat = np.concatenate(all_feat, axis=1)
            combined_returns = np.concatenate(all_returns, axis=0)

            # 訓練
            result = self.train_regime_numpy(
                combined_feat, combined_returns,
                regime_plan=regime_plan,
                n_iterations=n_iterations_per_regime,
            )

            # 將最佳公式分配給該 regime 下的所有股票
            for stock_id in stocks:
                results[stock_id] = {
                    "best_formula": result["best_formula"],
                    "best_reward": result["best_reward"],
                    "regime": regime_key,
                    "n_iterations": result["n_iterations"],
                }

        return results


# ============================================================
# 使用範例
# ============================================================

def demo():
    """示範 GRPO 訓練"""
    print("=" * 50)
    print("GRPO 因子訓練框架 — 示範")
    print("=" * 50)

    config = GRPOConfig.auto_detect()

    # 生成模擬特徵矩陣
    np.random.seed(42)
    n_samples = 500
    n_features = 16
    feat_tensor = np.random.randn(n_features, n_samples).astype(np.float32)
    returns = np.random.randn(n_samples).astype(np.float32) * 0.02

    # Numpy 模式訓練
    trainer = GRPOAlphaTrainer(config)
    result = trainer.train_numpy(feat_tensor, returns, n_iterations=50)

    print(f"\n[結果] 最佳公式: {result['best_formula']}")
    print(f"[結果] 最佳獎勵: {result['best_reward']:.4f}")
    print(f"[結果] 訓練步數: {result['n_iterations']}")

    # 過擬合懲罰範例
    reward_calc = GRPORewardCalculator(config)
    group_tokens = [
        [0, 1, 16, 3, 18],  # (RET + LIQ_SCORE) * FOMO
        [0, 24, 10, 19],     # JUMP(RET) / CVD_PROXY
        [2, 22, 25],         # DECAY(SIGN(PRESSURE))
    ]

    result = reward_calc.compute_group_rewards(
        group_tokens, feat_tensor, returns,
        train_ic=0.15, val_ic=0.08,
    )
    print(f"\n[GRPO 評分範例]")
    print(f"  Rewards: {result['rewards']}")
    print(f"  Advantages: {result['advantages']}")
    print(f"  Best idx: {result['best_idx']}")
    print(f"  Overfit: {result['overfit_info']['is_overfit']}")

    print("\n[OK] GRPO 訓練框架就緒")


if __name__ == "__main__":
    demo()
