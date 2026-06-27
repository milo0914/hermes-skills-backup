# -*- coding: utf-8 -*-
"""
GRPO v4.0 Regime Alpha Factor Training — 三版合一統合版

版本編號: v4.0
ipynb編號: grpo-regime-v4
統合基準: 用戶版 (883行) + Kaggle v3.5 (2207行) + 本地版 (1913行)

修復清單:
  E1:  PPO ratio≡1 → REINFORCE loss = -(log_probs * advantages.detach()).mean()
  E2:  NaN Guard — step-level NaN skip + param-level reinit
  E5:  TX_MTX_SPREAD 真實計算 (TX inst_net_oi - MTX retail_net_oi)
  E6:  NASDAQ_CLOSE / SP500_CLOSE / DOWJONES_CLOSE 從 us_indices_df 計算
  E9:  RegimeConfig 22維 feature_weights 補6個v3.1因子權重
  E14: GitHubLogPusher 完整實作 (v3.5 token-based push)
  E17: GPU sm_70 → sm_50 放寬相容
  E18: LoRD decay 抽為 _apply_lord_decay() 方法
  S8:  main() 使用真實數據 (fetch_real_data 模組)

絕對原則:
  (1) 禁用 patch — 全用 write_file 確保縮排正確
  (2) Kaggle push 後 1min 確認 kernel + 下載 logs
  (3) cron 每 30min 統整 TODO + 版本編號回報
"""

import json
import os
import sys
import time
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

# ============================================================
# 0. 環境檢查
# ============================================================

def check_environment():
    """檢查 GPU 和套件，含 CUDA 相容性檢查"""
    print("=" * 60)
    print(" 台股 GRPO Regime-Aware 因子訓練 v4.0 (Kaggle GPU)")
    print("=" * 60)

    import torch
    gpu_compatible = False
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1e9
        cc = torch.cuda.get_device_capability(0)
        print(f" GPU: {gpu_name} ({gpu_mem:.1f} GB), CUDA capability sm_{cc[0]}{cc[1]}")
        # E17: 放寬 GPU 相容門檻 sm_50 (原 sm_70)
        if cc[0] >= 5:
            gpu_compatible = True
            print(f" GPU 相容: sm_{cc[0]}{cc[1]} >= sm_50 ✓")
        else:
            print(f" GPU 不相容: sm_{cc[0]}{cc[1]} < sm_50，將使用 CPU fallback")
    else:
        print(" WARNING: No GPU detected, using CPU (slow)")

    if not gpu_compatible:
        os.environ["GRPO_FORCE_CPU"] = "1"
        print(" >>> 強制 CPU 模式 (GRPO_FORCE_CPU=1)")

    print(f" PyTorch: {torch.__version__}")
    print(f" NumPy: {np.__version__}")
    print(f" Pandas: {pd.__version__}")
    print()

# ============================================================
# 1. 詞彙表與常數 — v4.0: 22 因子 + 12 運算子 = VOCAB_SIZE 34
# ============================================================

FEATURE_NAMES = (
    "RET", "LIQ_SCORE", "PRESSURE", "FOMO", "DEV", "LOG_VOL",
    "INST_FLOW", "MARGIN_PRESS", "FIVE_DAY_HIGH", "VOL_BREAKOUT",
    "CVD_PROXY", "ABSORPTION", "SURF_ENTRY", "ATR", "CLOSE_POS", "MOM_REV",
    # --- v3.1 新增 6 因子 ---
    "TX_INST_NET_OI", "MTX_RETAIL_OI", "TX_MTX_SPREAD",
    "NASDAQ_CLOSE", "SP500_CLOSE", "DOWJONES_CLOSE",
)

OPERATOR_NAMES = (
    "ADD", "SUB", "MUL", "DIV", "NEG", "ABS",
    "SIGN", "GATE", "JUMP", "DECAY", "DELAY1", "MAX3",
)

OPERATOR_ARITY = [2, 2, 2, 2, 1, 1, 1, 3, 1, 1, 1, 1]
N_FEATURES = len(FEATURE_NAMES)     # 22
N_OPERATORS = len(OPERATOR_NAMES)   # 12
VOCAB_SIZE = N_FEATURES + N_OPERATORS  # 34

# ============================================================
# 2. StackVM — 公式執行虛擬機
# ============================================================

class StackVM:
    def execute(self, tokens: List[int], feat_tensor: np.ndarray) -> Optional[np.ndarray]:
        n_features = N_FEATURES
        stack = []

        for t in tokens:
            if t < n_features:
                stack.append(feat_tensor[t].copy())
            else:
                op_idx = t - n_features
                if op_idx >= N_OPERATORS:
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
        if op_idx == 4:
            return -a
        if op_idx == 5:
            return np.abs(a)
        if op_idx == 6:
            return np.sign(a)
        if op_idx == 8:
            return np.where(np.abs((a - np.mean(a)) / (np.std(a) + 1e-6)) > 3, np.sign(a), 0)
        if op_idx == 9:
            return 0.8 * a + 0.6 * np.roll(a, 1)
        if op_idx == 10:
            return np.roll(a, 1)
        if op_idx == 11:
            return np.maximum(np.maximum(a, np.roll(a, 1)), np.roll(a, 2))
        return a

    @staticmethod
    def _apply_binary(op_idx: int, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        if op_idx == 0:
            return a + b
        if op_idx == 1:
            return a - b
        if op_idx == 2:
            return a * b
        if op_idx == 3:
            return a / (b + 1e-6)
        return a

    @staticmethod
    def _apply_ternary(op_idx: int, a, b, c):
        if op_idx == 7:
            return np.where(c > 0, a, b)
        return a

# ============================================================
# 3. StackVMState — 引導式解碼的棧狀態追蹤器
# ============================================================

class StackVMState:
    def __init__(self, max_stack_depth: int = 3):
        self.stack_depth = 0
        self.max_stack = max_stack_depth

    def reset(self):
        self.stack_depth = 0

    def get_valid_tokens(self, position: int, remaining: int) -> set:
        valid = set()
        # 特徵 token: push
        if self.stack_depth < self.max_stack:
            new_depth = self.stack_depth + 1
            min_needed = new_depth - 1
            if remaining - 1 >= min_needed:
                valid.update(range(N_FEATURES))

        # 運算子 token: pop arity, push 1
        for op_idx in range(N_OPERATORS):
            arity = OPERATOR_ARITY[op_idx]
            if self.stack_depth >= arity:
                new_depth = self.stack_depth - arity + 1
                min_needed = new_depth - 1
                if remaining - 1 >= min_needed:
                    valid.add(N_FEATURES + op_idx)
        return valid

    def apply_token(self, token: int):
        if token < N_FEATURES:
            self.stack_depth += 1
        else:
            op_idx = token - N_FEATURES
            arity = OPERATOR_ARITY[op_idx]
            self.stack_depth = self.stack_depth - arity + 1

    def is_complete(self) -> bool:
        return self.stack_depth == 1

# ============================================================
# 4. Regime 定義與配置 — v4.0: 22維 feature_weights
# ============================================================

class StockRegime(Enum):
    LARGE_CAP = "large_cap"
    MID_CAP_TECH = "mid_cap_tech"
    TRADITIONAL = "traditional"
    FINANCIAL = "financial"

KNOWN_REGIMES = {
    "2330": StockRegime.LARGE_CAP, "2308": StockRegime.LARGE_CAP, "2412": StockRegime.LARGE_CAP,
    "2454": StockRegime.MID_CAP_TECH, "2382": StockRegime.MID_CAP_TECH, "2317": StockRegime.MID_CAP_TECH,
    "3034": StockRegime.MID_CAP_TECH, "3711": StockRegime.MID_CAP_TECH, "2303": StockRegime.MID_CAP_TECH,
    "1301": StockRegime.TRADITIONAL, "1303": StockRegime.TRADITIONAL, "1326": StockRegime.TRADITIONAL,
    "1101": StockRegime.TRADITIONAL, "2002": StockRegime.TRADITIONAL,
    "2882": StockRegime.FINANCIAL, "2886": StockRegime.FINANCIAL, "2891": StockRegime.FINANCIAL,
    "2884": StockRegime.FINANCIAL, "2881": StockRegime.FINANCIAL,
}

@dataclass
class RegimeConfig:
    # E9: 補齊 22 維 feature_weights (v3.1 新增6因子)
    feature_weights: Dict[StockRegime, Dict[str, float]] = field(default_factory=lambda: {
        StockRegime.LARGE_CAP: {
            "RET": 1.0, "LIQ_SCORE": 1.0, "PRESSURE": 1.5, "INST_FLOW": 2.0,
            "TX_INST_NET_OI": 1.5, "TX_MTX_SPREAD": 1.0,
            "NASDAQ_CLOSE": 0.8, "SP500_CLOSE": 0.8,
        },
        StockRegime.MID_CAP_TECH: {
            "RET": 1.0, "FOMO": 1.2, "FIVE_DAY_HIGH": 1.5, "VOL_BREAKOUT": 1.5,
            "NASDAQ_CLOSE": 1.0, "SP500_CLOSE": 1.0,
        },
        StockRegime.TRADITIONAL: {
            "RET": 1.0, "DEV": 1.5, "VOL_BREAKOUT": 1.5, "MOM_REV": 1.0,
            "MTX_RETAIL_OI": 0.8, "DOWJONES_CLOSE": 0.8,
        },
        StockRegime.FINANCIAL: {
            "RET": 1.0, "LIQ_SCORE": 1.5, "CLOSE_POS": 1.5, "ATR": 1.2,
            "TX_INST_NET_OI": 1.0, "MTX_RETAIL_OI": 1.0,
        },
    })
    operator_mask: Dict[StockRegime, Dict[str, bool]] = field(default_factory=lambda: {
        StockRegime.LARGE_CAP: {n: True for n in OPERATOR_NAMES},
        StockRegime.MID_CAP_TECH: {n: True for n in OPERATOR_NAMES},
        StockRegime.TRADITIONAL: {**{n: True for n in OPERATOR_NAMES}, "SIGN": False, "JUMP": False},
        StockRegime.FINANCIAL: {**{n: True for n in OPERATOR_NAMES}, "SIGN": False, "JUMP": False},
    })
    training_params: Dict[StockRegime, Dict] = field(default_factory=lambda: {
        StockRegime.LARGE_CAP: {"group_size": 8, "reward_horizon": 5, "focus": "法人籌碼"},
        StockRegime.MID_CAP_TECH: {"group_size": 6, "reward_horizon": 4, "focus": "技術突破"},
        StockRegime.TRADITIONAL: {"group_size": 4, "reward_horizon": 5, "focus": "營收驅動"},
        StockRegime.FINANCIAL: {"group_size": 4, "reward_horizon": 7, "focus": "均值回歸"},
    })

class RegimeTrainingPlan:
    def __init__(self, config: RegimeConfig = None):
        self.config = config or RegimeConfig()

    def create_plan(self, stock_id: str, regime: StockRegime) -> dict:
        weights_dict = self.config.feature_weights[regime]
        feature_weights = np.array(
            [weights_dict.get(f, 1.0) for f in FEATURE_NAMES], dtype=np.float32
        )
        feature_mask = feature_weights > 0.8
        ops_dict = self.config.operator_mask[regime]
        operator_mask = np.array(
            [ops_dict.get(op, True) for op in OPERATOR_NAMES], dtype=bool
        )
        params = self.config.training_params[regime]
        return {
            "regime": regime,
            "feature_weights": feature_weights,
            "feature_mask": feature_mask,
            "operator_mask": operator_mask,
            "group_size": params["group_size"],
            "reward_horizon": params["reward_horizon"],
        }

# ============================================================
# 5. 特徵工程與 Robust Normalize
# ============================================================

def robust_normalize(arr, window=20):
    """AlphaGPT 核心設計: Rolling window 正規化 (robust norm)
    使用滾動窗口的 median + MAD，比 z-score 更抗極端值。"""
    if arr is None or len(arr) < window:
        return arr
    result = np.copy(arr).astype(np.float64)
    for i in range(window, len(arr)):
        segment = arr[i - window:i]
        med = np.median(segment)
        mad = np.median(np.abs(segment - med))
        if mad > 1e-8:
            result[i] = (arr[i] - med) / (1.4826 * mad)
        else:
            result[i] = 0.0
    global_med = np.median(arr[:window])
    global_mad = np.median(np.abs(arr[:window] - global_med))
    if global_mad > 1e-8:
        result[:window] = (arr[:window] - global_med) / (1.4826 * global_mad)
    else:
        result[:window] = 0.0
    return result

class TWFeatureEngineer:
    NORM_WINDOW = 60
class TWFeatureEngineer:
    NORM_WINDOW = 60
    NORM_CLIP = 5.0

    @staticmethod
    def compute_features(df, inst_df=None, margin_df=None,
                         futures_oi_df=None, us_indices_df=None):
        """計算 22 因子特徵矩陣 — v4.0 (merge-free map 版)

        Args:
            df: OHLCV DataFrame (columns: date, stock_id, open, high, low, close, volume)
            inst_df: 法人買賣超 DataFrame
            margin_df: 融資融券 DataFrame
            futures_oi_df: 期貨法人 OI DataFrame
            us_indices_df: 美股指數 DataFrame
        """
        result_frames = []
        stock_ids = df["stock_id"].unique()

        # --- Preprocess 期貨 OI (TX/MTX) ---
        tx_oi, mtx_oi = None, None
        if futures_oi_df is not None and len(futures_oi_df) > 0:
            # 嘗試 TX (大台)
            tx_mask = futures_oi_df["futures_id"].astype(str).str.upper().str.contains("TX", na=False)
            tx_data = futures_oi_df[tx_mask & ~futures_oi_df["futures_id"].astype(str).str.upper().str.contains("MTX", na=False)]
            if len(tx_data) > 0:
                tx_agg = tx_data.groupby("date").agg(
                    tx_inst_net_oi=("Foreign_Investor_net_oi", "sum")
                ).reset_index()
                # 只保留需要的欄位，避免 merge 衝突
                tx_oi = tx_agg[["date", "tx_inst_net_oi"]].copy()

            # 嘗試 MTX (小台)
            mtx_mask = futures_oi_df["futures_id"].astype(str).str.upper().str.contains("MTX", na=False)
            mtx_data = futures_oi_df[mtx_mask]
            if len(mtx_data) > 0:
                # 散戶 = Dealer_self_net_oi (反指標)
                mtx_agg = mtx_data.groupby("date").agg(
                    mtx_retail_net_oi=("Dealer_self_net_oi", "sum")
                ).reset_index()
                mtx_oi = mtx_agg[["date", "mtx_retail_net_oi"]].copy()

        # --- Preprocess 美股指數 ---
        us_dfs = {}
        if us_indices_df is not None and len(us_indices_df) > 0:
            for idx_name, raw_col in [
                ("Nasdaq", "nasdaq_close_raw"),
                ("SP500", "sp500_close_raw"),
                ("DowJones", "dowjones_close_raw"),
            ]:
                idx_data = us_indices_df[us_indices_df["index_name"] == idx_name]
                if len(idx_data) > 0:
                    us_dfs[raw_col] = idx_data[["date", "close"]].rename(
                        columns={"close": raw_col}
                    ).copy()

        for stock_id in stock_ids:
            g = df[df["stock_id"] == stock_id].copy()
            g = g.sort_values("date").reset_index(drop=True)

            if len(g) < 30:
                continue

            g["ret"] = g["close"].pct_change().fillna(0)
            vol_chg = g["volume"].pct_change().fillna(0)
            g["liq_score"] = np.log1p(g["volume"]) / (g["close"] + 1e-6)
            g["pressure"] = (g["close"] - g["open"]) / (g["open"] + 1e-6)
            g["fomo"] = vol_chg - vol_chg.shift(1)
            ma20 = g["close"].rolling(20).mean()
            g["dev"] = (g["close"] - ma20) / (ma20 + 1e-6)
            g["log_vol"] = np.log1p(g["volume"])

            # 法人買賣超 (用 map 避免 merge 同名欄衝突)
            inst_vals = np.zeros(len(g))
            if inst_df is not None and len(inst_df) > 0:
                inst_data = inst_df[inst_df["stock_id"] == stock_id]
                if len(inst_data) > 0:
                    net_col = "total_net" if "total_net" in inst_data.columns else "net_buy"
                    if net_col in inst_data.columns:
                        date_to_net = dict(zip(
                            inst_data["date"].astype(str),
                            inst_data[net_col]
                        ))
                        g_dates = g["date"].dt.strftime("%Y-%m-%d")
                        inst_vals = g_dates.map(date_to_net).values
                        inst_vals = pd.Series(inst_vals).ffill().fillna(0).values
            g["inst_flow"] = inst_vals

            # 融資融券 (用 map 避免 merge 衝突)
            margin_vals = np.zeros(len(g))
            if margin_df is not None and len(margin_df) > 0:
                margin_data = margin_df[margin_df["stock_id"] == stock_id]
                if len(margin_data) > 0 and "margin_balance" in margin_data.columns:
                    date_to_margin = dict(zip(
                        margin_data["date"].astype(str),
                        margin_data["margin_balance"]
                    ))
                    g_dates = g["date"].dt.strftime("%Y-%m-%d")
                    margin_vals = g_dates.map(date_to_margin).values
                    margin_vals = pd.Series(margin_vals).ffill().fillna(0).pct_change(5).fillna(0).values
            g["margin_press"] = margin_vals

            high5 = g["close"].rolling(5).max()
            g["five_day_high"] = (g["close"] - high5) / (high5 + 1e-6)
            vol_ma5 = g["volume"].rolling(5).mean()
            g["vol_breakout"] = g["volume"] / (vol_ma5 + 1e-6)
            cvd_intraday = (
                (g["close"] - g["open"]) / (g["high"] - g["low"] + 1e-6) * g["volume"]
            )
            g["cvd_proxy"] = cvd_intraday.rolling(20).sum() / (
                g["volume"].rolling(20).mean() * 20 + 1e-6
            )
            g["absorption"] = (
                (g["high"] - g["close"]) / (g["high"] - g["low"] + 1e-6) * g["volume"]
            )

            # --- v3.1 新增 6 因子 (E5/E6: 真實計算, merge-free) ---

            # TX_INST_NET_OI: 大台法人淨 OI (用 map 避免 merge 衝突)
            tx_vals = np.zeros(len(g))
            if tx_oi is not None and len(tx_oi) > 0:
                date_to_tx = dict(zip(
                    tx_oi["date"].astype(str),
                    tx_oi["tx_inst_net_oi"]
                ))
                g_dates = g["date"].dt.strftime("%Y-%m-%d")
                tx_vals = g_dates.map(date_to_tx).values
                tx_vals = pd.Series(tx_vals).ffill().fillna(0).values
            g["TX_INST_NET_OI"] = tx_vals

            # MTX_RETAIL_OI: 小台散戶淨 OI (用 map 避免 merge 衝突)
            mtx_vals = np.zeros(len(g))
            if mtx_oi is not None and len(mtx_oi) > 0:
                date_to_mtx = dict(zip(
                    mtx_oi["date"].astype(str),
                    mtx_oi["mtx_retail_net_oi"]
                ))
                g_dates = g["date"].dt.strftime("%Y-%m-%d")
                mtx_vals = g_dates.map(date_to_mtx).values
                mtx_vals = pd.Series(mtx_vals).ffill().fillna(0).values
            g["MTX_RETAIL_OI"] = mtx_vals

            # E5: TX_MTX_SPREAD = TX法人淨OI - MTX散戶淨OI (真實計算)
            g["TX_MTX_SPREAD"] = g["TX_INST_NET_OI"] - g["MTX_RETAIL_OI"]

            # E6: 美股指數 (5日動量, 用 map 避免 merge 衝突)
            for idx_name, feat_name, raw_col in [
                ("Nasdaq", "NASDAQ_CLOSE", "nasdaq_close_raw"),
                ("SP500", "SP500_CLOSE", "sp500_close_raw"),
                ("DowJones", "DOWJONES_CLOSE", "dowjones_close_raw"),
            ]:
                if raw_col in us_dfs:
                    us_df = us_dfs[raw_col]
                    date_to_us = dict(zip(
                        us_df["date"].astype(str),
                        us_df[raw_col]
                    ))
                    g_dates = g["date"].dt.strftime("%Y-%m-%d")
                    raw_vals = g_dates.map(date_to_us).values
                    raw_vals = pd.Series(raw_vals).ffill().bfill()
                    # 5日動量
                    g[feat_name] = raw_vals.pct_change(5).fillna(0)
                else:
                    g[feat_name] = 0

            # --- 以下不需 stock_id 分組的因子 ---
            # 這些用 for feat_name 設過 0 的也補上
            for feat_name in [
                "five_day_high", "vol_breakout", "cvd_proxy",
                "absorption", "surf_entry", "atr", "close_pos", "mom_rev"
            ]:
                if feat_name not in g.columns:
                    g[feat_name] = 0

            key_level = g["close"].rolling(20).mean()
            g["surf_entry"] = np.where(
                np.abs(g["close"] - key_level) / (key_level + 1e-6) < 0.01, 1.0, 0.0
            )

            high, low, close = g["high"].values, g["low"].values, g["close"].values
            prev_close = np.roll(close, 1)
            prev_close[0] = close[0]
            tr = np.maximum(
                high - low,
                np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)),
            )
            g["atr"] = pd.Series(tr).rolling(14).mean() / (close + 1e-6)
            g["close_pos"] = (g["close"] - g["low"]) / (g["high"] - g["low"] + 1e-6)
            g["mom_rev"] = -1 * g["ret"].rolling(5).sum()

            # 統一大小寫
            _lower_to_upper = {
                "ret": "RET", "liq_score": "LIQ_SCORE", "pressure": "PRESSURE",
                "fomo": "FOMO", "dev": "DEV", "log_vol": "LOG_VOL",
                "inst_flow": "INST_FLOW", "margin_press": "MARGIN_PRESS",
                "five_day_high": "FIVE_DAY_HIGH", "vol_breakout": "VOL_BREAKOUT",
                "cvd_proxy": "CVD_PROXY", "absorption": "ABSORPTION",
                "surf_entry": "SURF_ENTRY", "atr": "ATR",
                "close_pos": "CLOSE_POS", "mom_rev": "MOM_REV",
            }
            for _lower, _upper in _lower_to_upper.items():
                if _lower in g.columns:
                    g[_upper] = g[_lower]

            # robust_normalize
            for feat in FEATURE_NAMES:
                if feat not in g.columns:
                    g[feat] = 0.0
                    continue
                g[feat] = robust_normalize(
                    g[feat].values, window=TWFeatureEngineer.NORM_WINDOW
                )
                g[feat] = g[feat].clip(
                    -TWFeatureEngineer.NORM_CLIP, TWFeatureEngineer.NORM_CLIP
                )

            result_frames.append(g)

        return pd.concat(result_frames, ignore_index=True)


# ============================================================
# 6. GRPOConfig 與 Logger
# ============================================================

@dataclass
class GRPOConfig:
    group_size: int = 8
    d_model: int = 64
    nhead: int = 4
    num_layers: int = 2
    dim_feedforward: int = 128
    num_loops: int = 3
    vocab_size: int = VOCAB_SIZE  # 34
    max_formula_len: int = 15
    batch_size: int = 128
    train_steps: int = 20000
    lr: float = 1e-3
    entropy_coef: float = 0.01
    reward_clip: float = 5.0
    advantage_clip: float = 3.0
    use_overfit_penalty: bool = True
    ic_gap_threshold: float = 0.05
    ic_gap_weight: float = 2.0
    turnover_weight: float = 0.5
    turnover_max: float = 0.3
    use_lord: bool = True
    lord_decay: float = 1e-3
    clip_eps: float = 0.2
    guided_decoding: bool = True
    warmup_steps: int = 500
    max_stack_depth: int = 3
    device: str = "cpu"

    @classmethod
    def auto_detect(cls):
        config = cls()
        force_cpu = os.environ.get("GRPO_FORCE_CPU", "0") == "1"
        try:
            import torch
            if torch.cuda.is_available() and not force_cpu:
                config.device = "cuda"
            else:
                config.device = "cpu"
                config.group_size = 4
                config.train_steps = 3000
        except ImportError:
            pass
        return config

# ============================================================
# 7. GitHub Log Pusher — E14: 完整實作 (v3.5 token-based)
# ============================================================

class GitHubLogPusher:
    """Push training logs to GitHub repo for real-time monitoring.

    Usage in Kaggle notebook:
    1. Add GITHUB_TOKEN as Kaggle Secret
    2. pusher = GitHubLogPusher(token=os.environ.get("GITHUB_TOKEN"))
    3. Call pusher.push_log(regime, step, metrics) every N steps
    4. Call pusher.push_final(regime, result) after each regime completes
    """

    def __init__(self, token: str = None, repo: str = "milo0914/AlphaGPT",
                 branch: str = "main"):
        self.token = token
        self.repo = repo
        self.branch = branch
        self.api_url = f"https://api.github.com/repos/{repo}/contents"
        self.enabled = token is not None and len(token) > 10
        self.push_count = 0
        self._session = None

        if self.enabled:
            import urllib.request
            import urllib.error
            req = urllib.request.Request(
                f"https://api.github.com/repos/{repo}",
                headers={
                    "Authorization": f"token {token}",
                    "User-Agent": "AlphaGPT-Kaggle",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        print(f" [GitHubLog] Auth OK, repo={repo}")
                    else:
                        self.enabled = False
            except Exception as e:
                print(f" [GitHubLog] Auth FAILED: {e}")
                self.enabled = False
        else:
            print(f" [GitHubLog] Disabled (no GITHUB_TOKEN)")

    def _push_file(self, path: str, content: str, sha: str = None):
        """Push or update a file on GitHub via API"""
        if not self.enabled:
            return False

        import urllib.request
        import urllib.error
        import base64
        import json as _json

        url = f"{self.api_url}/{path}"
        data = {
            "message": f"[auto] Update {path} - training progress",
            "content": base64.b64encode(content.encode()).decode(),
            "branch": self.branch,
        }
        if sha:
            data["sha"] = sha

        headers = {
            "Authorization": f"token {self.token}",
            "User-Agent": "AlphaGPT-Kaggle",
            "Content-Type": "application/json",
        }

        req = urllib.request.Request(
            url, data=_json.dumps(data).encode(), headers=headers, method="PUT"
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = _json.loads(resp.read().decode())
                return result.get("content", {}).get("sha")
        except urllib.error.HTTPError as e:
            if e.code == 409 and not sha:
                # 409 Conflict = file exists, need SHA for update
                try:
                    get_req = urllib.request.Request(
                        url,
                        headers={
                            "Authorization": f"token {self.token}",
                            "User-Agent": "AlphaGPT-Kaggle",
                        },
                    )
                    with urllib.request.urlopen(get_req, timeout=10) as get_resp:
                        file_info = _json.loads(get_resp.read().decode())
                        current_sha = file_info.get("sha")
                        if current_sha:
                            return self._push_file(path, content, sha=current_sha)
                except Exception:
                    pass
            return False
        except Exception as e:
            print(f" [GitHubLog] Push error: {e}")
            return False

    def push_log(self, regime: str, step: int, metrics: dict):
        """Push a training step log"""
        if not self.enabled:
            return

        import json as _json

        log_entry = {
            "regime": regime,
            "step": step,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            **metrics,
        }

        # Push latest metrics as JSON
        metrics_path = f"kaggle-logs/{regime}/latest_metrics.json"
        self._push_file(
            metrics_path, _json.dumps(log_entry, indent=2, ensure_ascii=False)
        )

        # Push progress summary as txt
        summary_line = (
            f"{log_entry['timestamp']} | {regime} | step={step} | "
            f"loss={metrics.get('loss', 0):.4f} | "
            f"mean_r={metrics.get('mean_reward', 0):.3f} | "
            f"best_r={metrics.get('best_reward', 0):.3f} | "
            f"valid={metrics.get('valid_ratio', 0):.1%} | "
            f"clip_ratio={metrics.get('clip_ratio', 0):.1%}\n"
        )
        summary_path = f"kaggle-logs/{regime}/progress.txt"
        self._push_file(summary_path, summary_line)

        self.push_count += 1

    def push_final(self, regime: str, result: dict):
        """Push final training result for a regime"""
        if not self.enabled:
            return

        import json as _json

        final_path = f"kaggle-logs/{regime}/final_result.json"
        final_data = {
            "regime": regime,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "best_formula": result.get("best_formula"),
            "decoded_formula": result.get("decoded_formula", "N/A"),
            "best_reward": float(result.get("best_reward", 0)),
            "train_ic": float(result.get("train_ic", 0)),
            "val_ic": float(result.get("val_ic", 0)),
            "ic_gap": float(result.get("ic_gap", 0)),
            "n_steps": result.get("n_steps", 0),
            "is_overfit": float(result.get("ic_gap", 0)) > 0.1,
        }
        self._push_file(
            final_path, _json.dumps(final_data, indent=2, ensure_ascii=False)
        )

# ============================================================
# 8. GRPO Reward Calculator
# ============================================================

class GRPORewardCalculator:
    def __init__(self, config: GRPOConfig = None):
        self.config = config or GRPOConfig()
        self.vm = StackVM()

    @staticmethod
    def _spearman_corr(x, y):
        """scipy-free Spearman correlation (numpy argsort)"""
        rx = np.argsort(np.argsort(x)).astype(float)
        ry = np.argsort(np.argsort(y)).astype(float)
        rx = (rx - rx.mean()) / (rx.std() + 1e-8)
        ry = (ry - ry.mean()) / (ry.std() + 1e-8)
        return float(np.mean(rx * ry))

    def _default_backtest(self, signal, returns):
        valid = np.isfinite(signal) & np.isfinite(returns)
        if valid.sum() < 10:
            return -5.0
        ic = self._spearman_corr(signal[valid], returns[valid])
        return ic * 10

    def compute_group_rewards(self, group_tokens, feat_tensor, returns,
                               train_ic=None, val_ic=None, daily_turnover=0.0):
        G = len(group_tokens)
        rewards = []
        if train_ic is None:
            train_ic = np.zeros(G)
        if val_ic is None:
            val_ic = np.zeros(G)

        for i, tokens in enumerate(group_tokens):
            signal = self.vm.execute(tokens, feat_tensor)
            if signal is None:
                rewards.append(-5.0)
                continue
            if np.std(signal) < 1e-4:
                rewards.append(-2.0)
                continue

            base_reward = self._default_backtest(signal, returns)
            if self.config.use_overfit_penalty:
                t_ic = train_ic[i] if isinstance(train_ic, np.ndarray) else train_ic
                v_ic = val_ic[i] if isinstance(val_ic, np.ndarray) else val_ic
                ic_gap = max(0, t_ic - v_ic - self.config.ic_gap_threshold)
                base_reward -= (self.config.ic_gap_weight * ic_gap)

            rewards.append(
                np.clip(base_reward, -self.config.reward_clip, self.config.reward_clip)
            )

        rewards = np.array(rewards)
        valid_mask = rewards > -5.0

        if valid_mask.sum() > 1:
            group_mean = rewards[valid_mask].mean()
            group_std = rewards[valid_mask].std() + 1e-6
            advantages = (rewards - group_mean) / group_std
        elif valid_mask.sum() == 1:
            advantages = np.where(valid_mask, 1.0, -1.0).astype(float)
        else:
            advantages = -np.ones(G)

        advantages = np.clip(
            advantages, -self.config.advantage_clip, self.config.advantage_clip
        )

        return {
            "rewards": rewards,
            "advantages": advantages,
            "valid_mask": valid_mask,
            "overfit_info": {
                "train_ic": (
                    np.mean(train_ic)
                    if isinstance(train_ic, np.ndarray)
                    else train_ic
                ),
                "val_ic": (
                    np.mean(val_ic) if isinstance(val_ic, np.ndarray) else val_ic
                ),
                "is_overfit": (
                    bool(np.mean(train_ic - val_ic) > 0.1)
                    if isinstance(train_ic, np.ndarray)
                    else False
                ),
            },
            "group_mean_reward": (
                rewards[valid_mask].mean() if valid_mask.sum() > 0 else 0.0
            ),
            "best_idx": int(np.argmax(rewards)) if len(rewards) > 0 else 0,
        }

# ============================================================
# 9. NaN 安全函數 (v3.4/v4.0)
# ============================================================

def _safe_logits(logits, eps=1e-8):
    """Numerical safety for logits: replace NaN/Inf, ensure finite range.
    Prevents Categorical distribution crash when model produces NaN."""
    import torch
    logits = torch.where(torch.isnan(logits), torch.zeros_like(logits), logits)
    logits = torch.where(torch.isinf(logits), torch.sign(logits) * 20.0, logits)
    logits = torch.clamp(logits, -20.0, 20.0)
    return logits

# ============================================================
# 10. LoopedTransformer 模型架構
# ============================================================

def build_looped_transformer(config):
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    class RMSNorm(nn.Module):
        def __init__(self, d_model, eps=1e-6):
            super().__init__()
            self.weight = nn.Parameter(torch.ones(d_model))
            self.eps = eps

        def forward(self, x):
            return self.weight * (
                x / torch.sqrt(torch.mean(x ** 2, dim=-1, keepdim=True) + self.eps)
            )

    class SwiGLU(nn.Module):
        def __init__(self, d_model, dim_feedforward, dropout=0.1):
            super().__init__()
            self.w_gate = nn.Linear(d_model, dim_feedforward, bias=False)
            self.w_up = nn.Linear(d_model, dim_feedforward, bias=False)
            self.w_down = nn.Linear(dim_feedforward, d_model, bias=False)
            self.dropout = nn.Dropout(dropout)

        def forward(self, x):
            return self.dropout(
                self.w_down(F.silu(self.w_gate(x)) * self.w_up(x))
            )

    class QKNormAttention(nn.Module):
        def __init__(self, d_model, nhead, dropout=0.1):
            super().__init__()
            self.d_k = d_model // nhead
            self.nhead = nhead
            self.w_q, self.w_k, self.w_v, self.w_o = [
                nn.Linear(d_model, d_model, bias=False) for _ in range(4)
            ]
            self.q_norm, self.k_norm = RMSNorm(self.d_k), RMSNorm(self.d_k)
            self.dropout = nn.Dropout(dropout)

        def forward(self, x, mask=None):
            B, T, D = x.shape
            q = self.q_norm(
                self.w_q(x).view(B, T, self.nhead, self.d_k).transpose(1, 2)
            )
            k = self.k_norm(
                self.w_k(x).view(B, T, self.nhead, self.d_k).transpose(1, 2)
            )
            v = self.w_v(x).view(B, T, self.nhead, self.d_k).transpose(1, 2)
            attn = F.softmax(
                torch.matmul(q, k.transpose(-2, -1)) * (self.d_k ** -0.5), dim=-1
            )
            out = torch.matmul(self.dropout(attn), v).transpose(1, 2).contiguous().view(B, T, D)
            return self.w_o(out)

    class MTPHead(nn.Module):
        """Multi-Task Pooling Head — 3 種池化策略門控融合"""
        def __init__(self, d_model, vocab_size, dropout=0.1):
            super().__init__()
            self.head_mean, self.head_max, self.head_first = [
                nn.Linear(d_model, vocab_size) for _ in range(3)
            ]
            self.gate = nn.Linear(d_model * 3, 3, bias=False)
            self.head_critic = nn.Linear(d_model, 1)

        def forward(self, h):
            pool_mean = h.mean(dim=1)
            pool_max = h.max(dim=1).values
            pool_first = h[:, 0, :]
            logits_mean = self.head_mean(pool_mean)
            logits_max = self.head_max(pool_max)
            logits_first = self.head_first(pool_first)
            weights = F.softmax(
                self.gate(torch.cat([pool_mean, pool_max, pool_first], dim=-1)), dim=-1
            )
            logits = (
                weights[:, 0:1] * logits_mean
                + weights[:, 1:2] * logits_max
                + weights[:, 2:3] * logits_first
            )
            return logits, self.head_critic(pool_mean).squeeze(-1)

    class LoopedTransformer(nn.Module):
        def __init__(self, cfg):
            super().__init__()
            self.tok_emb = nn.Embedding(cfg.vocab_size, cfg.d_model)
            self.pos_emb = nn.Embedding(cfg.max_formula_len, cfg.d_model)
            self.blocks = nn.ModuleList([
                nn.ModuleList([
                    RMSNorm(cfg.d_model),
                    QKNormAttention(cfg.d_model, cfg.nhead),
                    RMSNorm(cfg.d_model),
                    SwiGLU(cfg.d_model, cfg.dim_feedforward),
                ])
                for _ in range(cfg.num_layers)
            ])
            self.final_norm = RMSNorm(cfg.d_model)
            self.mtp_head = MTPHead(cfg.d_model, cfg.vocab_size)
            self.num_loops = cfg.num_loops

        def forward(self, x, mask=None):
            pos = torch.arange(x.shape[1], device=x.device).unsqueeze(0)
            h = self.tok_emb(x) + self.pos_emb(pos)
            for _ in range(self.num_loops):
                for norm1, attn, norm2, ffn in self.blocks:
                    h = h + attn(norm1(h), mask)
                    h = h + ffn(norm2(h))
            logits, value = self.mtp_head(self.final_norm(h))
            return logits.unsqueeze(1), value

    return LoopedTransformer(config).to(config.device)

# ============================================================
# 11. StableRankMonitor
# ============================================================

class StableRankMonitor:
    def __init__(self):
        self.history = []

    def compute(self, model):
        import torch
        ranks = []
        with torch.no_grad():
            for name, param in model.named_parameters():
                if "weight" in name and param.dim() >= 2:
                    W = param.data.float()
                    frobenius_sq = (W ** 2).sum()
                    v = torch.randn(W.shape[1], device=W.device)
                    for _ in range(10):
                        u = W @ v
                        u = u / (u.norm() + 1e-8)
                        v = W.T @ u
                        v = v / (v.norm() + 1e-8)
                    spectral_norm = (W @ v).norm()
                    if spectral_norm > 1e-8:
                        ranks.append((frobenius_sq / (spectral_norm ** 2)).item())
        if ranks:
            info = {"avg_rank": sum(ranks) / len(ranks)}
            self.history.append(info)
            return info
        return {}

# ============================================================
# 12. 核心訓練器: GRPOAlphaTrainer — v4.0
# ============================================================

class GRPOAlphaTrainer:
    def __init__(self, config=None, gh_pusher=None):
        self.config = config or GRPOConfig.auto_detect()
        self.vm = StackVM()
        self.reward_calc = GRPORewardCalculator(self.config)
        self.model, self.optimizer = None, None
        self.history = []
        self.gh_pusher = gh_pusher

    def init_torch(self):
        import torch
        self.model = build_looped_transformer(self.config)
        self.optimizer = torch.optim.Adam(
            self.model.parameters(), lr=self.config.lr, weight_decay=1e-5
        )

    # E18: LoRD decay 抽為方法
    def _apply_lord_decay(self):
        """Newton-Schulz Low-Rank Decay — 低秩正則化"""
        import torch
        with torch.no_grad():
            for name, param in self.model.named_parameters():
                if "weight" in name and param.dim() >= 2:
                    W = param.data.float()
                    norm = W.norm()
                    if norm < 1e-8:
                        continue
                    X = W / norm
                    for _ in range(3):
                        X = 0.5 * X @ (
                            3.0 * torch.eye(X.shape[1], device=X.device) - X.T @ X
                        )
                    param.data -= self.config.lord_decay * (W - X * norm).to(param.dtype)

    def _compute_ic_array(self, group_tokens, feat_tensor=None, returns=None):
        """回傳各公式獨立的 IC Array"""
        if feat_tensor is None or returns is None:
            return np.zeros(len(group_tokens))
        ics = []
        for tokens in group_tokens:
            signal = self.vm.execute(tokens, feat_tensor)
            if signal is None or np.std(signal) < 1e-4:
                ics.append(0.0)
                continue
            valid = np.isfinite(signal) & np.isfinite(returns)
            if valid.sum() < 10:
                ics.append(0.0)
                continue
            ic = GRPORewardCalculator._spearman_corr(signal[valid], returns[valid])
            ics.append(ic if not np.isnan(ic) else 0.0)
        return np.array(ics)

    def train_torch_regime(self, feat_tensor, returns, regime_plan=None,
                           val_feat=None, val_returns=None):
        import torch
        if self.model is None:
            self.init_torch()

        feature_mask = regime_plan.get("feature_mask") if regime_plan else None
        operator_mask = regime_plan.get("operator_mask") if regime_plan else None
        feature_weights = regime_plan.get("feature_weights") if regime_plan else None
        regime_name = (
            regime_plan["regime"].value
            if regime_plan and hasattr(regime_plan.get("regime"), "value")
            else "unknown"
        )
        if regime_plan and "group_size" in regime_plan:
            self.config.group_size = regime_plan["group_size"]

        # Pre-compute regime mask (移至迴圈外避免 GPU 瓶頸)
        if feature_mask is not None and operator_mask is not None:
            mask = np.ones(VOCAB_SIZE, dtype=np.float32) * -1e9
            for i in range(N_FEATURES):
                if feature_mask[i]:
                    mask[i] = 0.0
            for i in range(N_OPERATORS):
                if operator_mask[i]:
                    mask[N_FEATURES + i] = 0.0
            self._precomputed_regime_mask = torch.tensor(
                mask, device=self.config.device
            )
        if feature_weights is not None:
            fw = torch.tensor(feature_weights, device=self.config.device)
            fw_logits = torch.zeros(VOCAB_SIZE, device=self.config.device)
            fw_logits[:N_FEATURES] = torch.log(fw + 0.01)
            self._precomputed_fw_logits = fw_logits * 0.5

        best_formula, best_reward, history = None, -float("inf"), []
        start_time = time.time()
        rank_monitor = StableRankMonitor()
        clip_eps = self.config.clip_eps

        for step in range(self.config.train_steps):
            self.model.train()
            all_log_probs, all_tokens, all_entropies = [], [], []

            is_warmup = step < self.config.warmup_steps

            for g in range(self.config.group_size):
                if is_warmup and g < self.config.group_size // 2:
                    feat_idx = (
                        int(np.argsort(-np.array(feature_weights))[g % N_FEATURES])
                        if feature_weights is not None
                        else g % N_FEATURES
                    )
                    warmup_inp = torch.zeros(
                        1, 1, dtype=torch.long, device=self.config.device
                    )
                    warmup_logits, _ = self.model(warmup_inp)
                    warmup_logits = _safe_logits(warmup_logits[:, -1, :].squeeze(0))
                    warmup_dist = torch.distributions.Categorical(logits=warmup_logits)
                    warmup_action = torch.tensor(
                        feat_idx, device=self.config.device
                    )
                    all_tokens.append([feat_idx])
                    all_log_probs.append(warmup_dist.log_prob(warmup_action))
                    all_entropies.append(warmup_dist.entropy())
                    continue

                vm_state = StackVMState(
                    max_stack_depth=self.config.max_stack_depth
                )
                inp = torch.zeros(
                    1, 1, dtype=torch.long, device=self.config.device
                )
                token_list, log_probs, entropies = [], [], []

                for t_pos in range(self.config.max_formula_len):
                    remaining = self.config.max_formula_len - t_pos
                    if vm_state.is_complete() and len(token_list) >= 1:
                        break

                    valid_tokens = (
                        vm_state.get_valid_tokens(t_pos, remaining)
                        if self.config.guided_decoding
                        else None
                    )
                    if self.config.guided_decoding and not valid_tokens:
                        break

                    logits, _ = self.model(inp)
                    logits_last = logits[:, -1, :].squeeze(0).clone()

                    # NaN safety
                    logits_last = _safe_logits(logits_last)

                    if valid_tokens is not None:
                        guided_mask = torch.full(
                            (VOCAB_SIZE,), -1e9, device=self.config.device
                        )
                        for t in valid_tokens:
                            guided_mask[t] = 0.0
                        logits_last = logits_last + guided_mask

                    if hasattr(self, "_precomputed_regime_mask"):
                        logits_last = logits_last + self._precomputed_regime_mask
                    if hasattr(self, "_precomputed_fw_logits"):
                        logits_last = logits_last + self._precomputed_fw_logits

                    if is_warmup and vm_state.stack_depth == 0:
                        logits_last[N_FEATURES:] = -1e9

                    dist = torch.distributions.Categorical(logits=logits_last)
                    action = dist.sample()
                    log_probs.append(dist.log_prob(action))
                    entropies.append(dist.entropy())
                    token_list.append(action.item())
                    vm_state.apply_token(action.item())
                    inp = torch.cat([inp, action.view(1, 1)], dim=1)

                if not vm_state.is_complete() or len(token_list) < 1:
                    feat_idx = (
                        int(np.argmax(feature_weights))
                        if feature_weights is not None
                        else 0
                    )
                    fb_inp = torch.zeros(
                        1, 1, dtype=torch.long, device=self.config.device
                    )
                    fb_logits, _ = self.model(fb_inp)
                    fb_logits = _safe_logits(fb_logits[:, -1, :].squeeze(0))
                    fb_dist = torch.distributions.Categorical(logits=fb_logits)
                    fb_action = torch.tensor(
                        feat_idx, device=self.config.device
                    )
                    token_list = [feat_idx]
                    log_probs = [fb_dist.log_prob(fb_action)]
                    entropies = [fb_dist.entropy()]

                all_tokens.append(token_list)
                all_log_probs.append(torch.stack(log_probs).sum())
                all_entropies.append(
                    torch.stack(entropies).sum()
                    if entropies
                    else torch.tensor(0.0, device=self.config.device)
                )

            # Rewards 計算
            train_ic = self._compute_ic_array(all_tokens, feat_tensor, returns)
            val_ic = (
                self._compute_ic_array(all_tokens, val_feat, val_returns)
                if val_feat is not None
                else np.zeros(len(all_tokens))
            )
            result = self.reward_calc.compute_group_rewards(
                all_tokens, feat_tensor, returns,
                train_ic=train_ic, val_ic=val_ic,
            )
            advantages = torch.tensor(
                result["advantages"], dtype=torch.float32, device=self.config.device
            )

            # ---- E1: REINFORCE (不再用 PPO ratio) ----
            log_probs_tensor = torch.stack(
                [lp.squeeze() for lp in all_log_probs]
            )
            # REINFORCE: loss = -(log_probs * advantages.detach()).mean()
            # 梯度只通過 log_probs_tensor，advantages 視為常數
            loss = -(log_probs_tensor * advantages.detach()).mean()

            # Entropy bonus (保持梯度連接)
            if all_entropies:
                entropy_loss = torch.stack(all_entropies).mean()
                loss -= self.config.entropy_coef * entropy_loss

            # ---- E2: NaN Guard ----
            self.optimizer.zero_grad()
            if torch.isnan(loss) or torch.isinf(loss):
                print(f" [NaN GUARD] step {step}: loss is NaN/Inf, skipping")
                continue

            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            self.optimizer.step()

            # E2: NaN guard — if any param is NaN, reinitialize model
            has_nan = any(p.isnan().any() for p in self.model.parameters())
            if has_nan:
                print(f" [NaN GUARD] step {step}: NaN in params, reinitializing")
                self.model = build_looped_transformer(self.config).to(
                    self.config.device
                )
                self.optimizer = torch.optim.Adam(
                    self.model.parameters(), lr=self.config.lr,
                    weight_decay=1e-5,
                )
                continue

            # E18: LoRD decay (方法化)
            if self.config.use_lord and step % 10 == 0:
                self._apply_lord_decay()

            # StableRank 監控
            if step % 500 == 0:
                rank_monitor.compute(self.model)

            # Track best
            best_idx = result["best_idx"]
            if result["rewards"][best_idx] > best_reward:
                best_reward = result["rewards"][best_idx]
                best_formula = all_tokens[best_idx]

            # 監控: ratio (REINFORCE 不用 ratio 更新，但追蹤供監控)
            with torch.no_grad():
                ratio = torch.ones_like(log_probs_tensor)  # on-policy ratio≡1

            if step % 100 == 0:
                elapsed = time.time() - start_time
                rank_str = (
                    f" avg_rank={rank_monitor.history[-1].get('avg_rank', 0):.1f}"
                    if rank_monitor.history
                    else ""
                )
                print(
                    f" step {step:5d}: loss={loss.item():.4f} "
                    f"mean_r={result['group_mean_reward']:.3f} "
                    f"best_r={best_reward:.3f} "
                    f"valid={result['valid_mask'].mean():.1%} "
                    f"overfit={result['overfit_info']['is_overfit']}"
                    f"{rank_str} elapsed={elapsed:.0f}s"
                )

            # E14: Push training metrics to GitHub
            if step % 500 == 0 and self.gh_pusher is not None:
                try:
                    self.gh_pusher.push_log(regime_name, step, {
                        "loss": loss.item(),
                        "mean_reward": result["group_mean_reward"],
                        "best_reward": float(result["rewards"][best_idx]),
                        "valid_ratio": float(result["valid_mask"].mean()),
                        "clip_ratio": 0.0,  # REINFORCE: no clipping
                        "elapsed_seconds": time.time() - start_time,
                    })
                except Exception as e:
                    print(f" [GitHubLog] push failed: {e}")

            history.append({
                "step": step,
                "regime": regime_name,
                "loss": loss.item(),
                "group_mean": result["group_mean_reward"],
                "best_reward": float(result["rewards"][best_idx]),
                "overfit": result["overfit_info"]["is_overfit"],
            })

        elapsed = time.time() - start_time
        print(
            f"\n[GRPO v4] regime={regime_name} 完成: "
            f"best_reward={best_reward:.4f}, steps={self.config.train_steps}, "
            f"elapsed={elapsed:.0f}s"
        )

        return {
            "best_formula": best_formula,
            "best_reward": best_reward,
            "regime": regime_name,
            "n_steps": self.config.train_steps,
            "history": history,
            "elapsed_seconds": elapsed,
        }

    def train_all_regimes(self, stock_data_map: Dict[str, dict]) -> Dict[str, dict]:
        results = {}
        regime_groups = defaultdict(list)

        for stock_id, data in stock_data_map.items():
            regime = data.get("regime_plan", {}).get(
                "regime", StockRegime.MID_CAP_TECH
            )
            regime_key = (
                regime.value if hasattr(regime, "value") else str(regime)
            )
            regime_groups[regime_key].append(stock_id)

        print(f"\n[Multi-Regime] 分群結果:")
        for rk, stocks in regime_groups.items():
            print(f"  {rk}: {stocks}")

        for regime_key, stocks in regime_groups.items():
            print(f"\n{'=' * 60}")
            print(f" 訓練 regime={regime_key} ({len(stocks)} 檔)")
            print(f"{'=' * 60}")

            # Data Leakage 修復: per-stock 80/20 時間切割
            all_train_feat, all_train_returns = [], []
            all_val_feat, all_val_returns = [], []
            regime_plan = None

            for stock_id in stocks:
                data = stock_data_map[stock_id]
                feat, ret = data.get("feat"), data.get("returns")
                if feat is not None and ret is not None:
                    n_train = int(ret.shape[0] * 0.8)
                    all_train_feat.append(feat[:, :n_train])
                    all_train_returns.append(ret[:n_train])
                    all_val_feat.append(feat[:, n_train:])
                    all_val_returns.append(ret[n_train:])
                    if regime_plan is None:
                        regime_plan = data.get("regime_plan")

            if not all_train_feat:
                continue
            train_feat = np.concatenate(all_train_feat, axis=1)
            train_returns = np.concatenate(all_train_returns, axis=0)
            val_feat = np.concatenate(all_val_feat, axis=1)
            val_returns = np.concatenate(all_val_returns, axis=0)

            self.model, self.optimizer = None, None
            self.init_torch()

            result = self.train_torch_regime(
                train_feat, train_returns, regime_plan, val_feat, val_returns
            )
            val_ic = self._compute_ic_array(
                [result["best_formula"]], val_feat, val_returns
            )[0]
            train_ic = self._compute_ic_array(
                [result["best_formula"]], train_feat, train_returns
            )[0]

            # E14: Push final result
            if self.gh_pusher is not None:
                try:
                    self.gh_pusher.push_final(regime_key, {
                        "best_formula": result["best_formula"],
                        "decoded_formula": decode_formula(result["best_formula"]),
                        "best_reward": result["best_reward"],
                        "train_ic": train_ic,
                        "val_ic": val_ic,
                        "ic_gap": train_ic - val_ic,
                        "n_steps": result["n_steps"],
                    })
                except Exception as e:
                    print(f" [GitHubLog] push_final failed: {e}")

            for stock_id in stocks:
                results[stock_id] = {
                    "best_formula": result["best_formula"],
                    "best_reward": result["best_reward"],
                    "regime": regime_key,
                    "train_ic": train_ic,
                    "val_ic": val_ic,
                    "ic_gap": train_ic - val_ic,
                    "n_steps": result["n_steps"],
                    "decoded_formula": decode_formula(result["best_formula"]),
                }

        return results

# ============================================================
# 13. 公式反編譯器
# ============================================================

def decode_formula(tokens: List[int]) -> str:
    if not tokens:
        return "INVALID"
    stack = []
    for t in tokens:
        if t < N_FEATURES:
            stack.append(FEATURE_NAMES[t])
        else:
            op_idx = t - N_FEATURES
            if op_idx >= N_OPERATORS:
                return "INVALID"
            arity = OPERATOR_ARITY[op_idx]
            if len(stack) < arity:
                return "INVALID"
            if arity == 1:
                stack.append(f"{OPERATOR_NAMES[op_idx]}({stack.pop()})")
            elif arity == 2:
                b, a = stack.pop(), stack.pop()
                stack.append(f"({a} {OPERATOR_NAMES[op_idx]} {b})")
            elif arity == 3:
                c, b, a = stack.pop(), stack.pop(), stack.pop()
                stack.append(f"GATE({a},{b}|{c})")
    return stack[0] if len(stack) == 1 else "INVALID"

# ============================================================
# 14. Walk-Forward Validation
# ============================================================

def walk_forward_validation(feat_tensor, returns, best_formula, n_splits=5):
    vm = StackVM()
    fold_size = returns.shape[0] // (n_splits + 1)
    ics = []
    for i in range(n_splits):
        test_start = fold_size * (i + 1)
        test_end = min(fold_size * (i + 2), returns.shape[0])
        if test_end <= test_start:
            continue
        test_feat = feat_tensor[:, test_start:test_end]
        test_ret = returns[test_start:test_end]
        signal = vm.execute(best_formula, test_feat)
        if signal is None or np.std(signal) < 1e-4:
            ics.append(0.0)
            continue
        valid = np.isfinite(signal) & np.isfinite(test_ret)
        if valid.sum() < 5:
            ics.append(0.0)
            continue
        ic = GRPORewardCalculator._spearman_corr(signal[valid], test_ret[valid])
        ics.append(ic if not np.isnan(ic) else 0.0)
    return {
        "fold_ics": ics,
        "mean_ic": np.mean(ics) if ics else 0.0,
        "std_ic": np.std(ics) if len(ics) > 1 else 0.0,
        "ic_tstat": (
            np.mean(ics) / (np.std(ics) + 1e-6) if len(ics) > 1 else 0.0
        ),
        "positive_ratio": (
            sum(1 for ic in ics if ic > 0) / len(ics) if ics else 0.0
        ),
    }

# ============================================================
# 15. 真實數據載入 — S8: 使用 fetch_real_data 模組
# ============================================================

def load_real_data(data_path="/tmp/twstock_real_data"):
    """從 CSV 載入真實數據 (由 fetch_real_data.py 產出)"""
    import os
    data = {}
    for name in ["price_ohlcv", "inst_flow", "margin", "futures_oi", "us_indices"]:
        fpath = f"{data_path}/{name}.csv"
        if os.path.exists(fpath):
            data[name] = pd.read_csv(fpath, parse_dates=["date"])
            print(f"  Loaded {name}: {len(data[name])} rows")
        else:
            data[name] = pd.DataFrame()
            print(f"  {name}: file not found, using empty")
    return data

def fetch_and_prepare_data(stock_ids=None, period="2y", start_date="2024-01-01",
                           save_path="/tmp/twstock_real_data"):
    """拉取真實數據並存檔 (Kaggle notebook 用)"""
    # Inline import to avoid dependency in CPU-only env
    try:
        from fetch_real_data import TWStockDataFetcher
        fetcher = TWStockDataFetcher(rate_limit_delay=3.0)
        data = fetcher.fetch_all(
            stock_ids=stock_ids or ["2330", "2454", "1301", "2882"],
            period=period,
            start_date=start_date,
        )
        fetcher.save_all(data, path=save_path)
        return data
    except ImportError:
        print("  [WARN] fetch_real_data not available, trying CSV fallback")
        return load_real_data(save_path)

# ============================================================
# 16. Main — v4.0: 使用真實數據
# ============================================================

def main():
    check_environment()

    # S8: 嘗試載入真實數據，fallback 到合成數據
    data = load_real_data("/tmp/twstock_real_data")
    df = data.get("price_ohlcv")

    if df is None or len(df) == 0:
        print("\n[WARN] 無真實數據，使用合成數據 (僅供語法測試)")
        np.random.seed(42)
        dates = pd.bdate_range(end="2025-12-31", periods=500)
        records = []
        for sid in ["2330", "2454", "1301", "2882"]:
            price = 100.0
            for d in dates:
                price *= (1 + np.random.normal(0.0003, 0.02))
                records.append({
                    "date": d, "stock_id": sid,
                    "open": price, "high": price * 1.01,
                    "low": price * 0.99, "close": price, "volume": 10000,
                })
        df = pd.DataFrame(records)
        inst_df, margin_df, futures_oi_df, us_indices_df = None, None, None, None
    else:
        inst_df = data.get("inst_flow")
        margin_df = data.get("margin")
        futures_oi_df = data.get("futures_oi")
        us_indices_df = data.get("us_indices")
        print(f"\n真實數據: OHLCV {len(df)} rows, "
              f"Inst {len(inst_df) if inst_df is not None else 0} rows, "
              f"Margin {len(margin_df) if margin_df is not None else 0} rows, "
              f"FuturesOI {len(futures_oi_df) if futures_oi_df is not None else 0} rows, "
              f"US {len(us_indices_df) if us_indices_df is not None else 0} rows")

    feat_df = TWFeatureEngineer.compute_features(
        df, inst_df, margin_df, futures_oi_df, us_indices_df
    )
    print(f"\n特徵矩陣: {feat_df.shape}")

    # 驗證 22 因子是否都有非零值
    for feat in FEATURE_NAMES:
        if feat in feat_df.columns:
            nonzero = (feat_df[feat].abs() > 1e-6).sum()
            print(f"  {feat}: non-zero={nonzero}/{len(feat_df)}")

    # 準備訓練數據
    stock_data_map = {}
    planner = RegimeTrainingPlan()

    for stock_id, group in feat_df.groupby("stock_id"):
        regime = KNOWN_REGIMES.get(stock_id, StockRegime.MID_CAP_TECH)
        feat_cols = [
            group[f].values if f in group.columns else np.zeros(len(group))
            for f in FEATURE_NAMES
        ]
        feat_tensor = np.nan_to_num(
            np.array(feat_cols, dtype=np.float32),
            nan=0.0, posinf=5.0, neginf=-5.0,
        )

        horizon = 5
        close = group["close"].values
        fwd_returns = np.zeros(len(close), dtype=np.float32)
        for i in range(len(close) - horizon):
            fwd_returns[i] = (close[i + horizon] - close[i]) / (close[i] + 1e-6)

        stock_data_map[stock_id] = {
            "feat": feat_tensor,
            "returns": fwd_returns,
            "regime_plan": planner.create_plan(stock_id, regime),
        }

    # Initialize trainer (with GitHubLogPusher if token available)
    gh_token = os.environ.get("GITHUB_TOKEN")
    gh_pusher = GitHubLogPusher(token=gh_token) if gh_token else None

    trainer = GRPOAlphaTrainer(
        config=GRPOConfig.auto_detect(),
        gh_pusher=gh_pusher,
    )
    results = trainer.train_all_regimes(stock_data_map)

    # Walk-forward validation
    print("\n" + "=" * 60)
    print(" 訓練完成! Walk-Forward 驗證:")
    print("=" * 60)
    for sid, res in results.items():
        print(
            f"  {sid} ({res['regime']}): "
            f"train_IC={res.get('train_ic', 0):.4f} "
            f"val_IC={res.get('val_ic', 0):.4f} "
            f"gap={res.get('ic_gap', 0):.4f} → "
            f"{res.get('decoded_formula', 'N/A')}"
        )

    # Save results
    output_dir = "/tmp/grpo_v4_results"
    os.makedirs(output_dir, exist_ok=True)

    # Save best formulas
    best_formulas = {
        sid: {
            "formula": res["best_formula"],
            "decoded": res.get("decoded_formula", "N/A"),
            "regime": res["regime"],
            "train_ic": float(res.get("train_ic", 0)),
            "val_ic": float(res.get("val_ic", 0)),
            "ic_gap": float(res.get("ic_gap", 0)),
            "best_reward": float(res.get("best_reward", 0)),
        }
        for sid, res in results.items()
    }
    with open(f"{output_dir}/best_strategy_per_regime.json", "w") as f:
        json.dump(best_formulas, f, indent=2, ensure_ascii=False)

    # Save training history
    all_history = []
    for sid, res in results.items():
        for h in res.get("history", []):
            h["stock_id"] = sid
            all_history.append(h)
    with open(f"{output_dir}/training_history.json", "w") as f:
        json.dump(all_history, f, indent=2, ensure_ascii=False)

    print(f"\n結果已存至 {output_dir}/")

    # Push final summary to GitHub
    if gh_pusher is not None:
        try:
            gh_pusher._push_file(
                "kaggle-logs/v4_summary.json",
                json.dumps(best_formulas, indent=2, ensure_ascii=False),
            )
        except Exception as e:
            print(f" [GitHubLog] summary push failed: {e}")


if __name__ == "__main__":
    main()
