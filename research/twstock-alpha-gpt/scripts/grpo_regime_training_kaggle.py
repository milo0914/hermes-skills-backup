"""
台股 AI Dig Money — GRPO Regime-Aware Alpha Factor Training (Kaggle GPU)

自含完整訓練邏輯，無需外部 skill 檔案。
在 Kaggle GPU T4 上執行 GRPO 策略梯度訓練，按 4 種股性分群，
挖掘各 regime 的最佳因子公式。

v3.3 — 修復3大梯度bug + alpha信號注入 + GitHub即時監控
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
    print("  台股 GRPO Regime-Aware 因子訓練 (Kaggle GPU)")
    print("=" * 60)

    import torch
    gpu_compatible = False
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1e9
        cc = torch.cuda.get_device_capability(0)
        print(f"  GPU: {gpu_name} ({gpu_mem:.1f} GB), CUDA capability sm_{cc[0]}{cc[1]}")
        # Check CUDA capability compatibility (PyTorch 2.10+ needs sm_70+)
        if cc[0] >= 7:
            gpu_compatible = True
            print(f"  GPU 相容: sm_{cc[0]}{cc[1]} >= sm_70 ✓")
        else:
            print(f"  GPU 不相容: sm_{cc[0]}{cc[1]} < sm_70，將使用 CPU fallback")
    else:
        print("  WARNING: No GPU detected, using CPU (slow)")

    if not gpu_compatible:
        os.environ["GRPO_FORCE_CPU"] = "1"
        print("  >>> 強制 CPU 模式 (GRPO_FORCE_CPU=1)")

    print(f"  PyTorch: {torch.__version__}")
    print(f"  NumPy: {np.__version__}")
    print(f"  Pandas: {pd.__version__}")
    print()


# ============================================================
# 1. 詞彙表與常數
# ============================================================

FEATURE_NAMES = (
    "RET", "LIQ_SCORE", "PRESSURE", "FOMO", "DEV", "LOG_VOL",
    "INST_FLOW", "MARGIN_PRESS", "FIVE_DAY_HIGH", "VOL_BREAKOUT",
    "CVD_PROXY", "ABSORPTION", "SURF_ENTRY", "ATR", "CLOSE_POS", "MOM_REV",
    # --- v3.1: 期貨 + 美股因子 ---
    "TX_INST_NET_OI",   # 大台三大法人淨未平倉量 (zscore)
    "MTX_RETAIL_OI",    # 小台散戶淨未平倉量 (zscore)
    "TX_MTX_SPREAD",    # 大台-小台法人OI差 (zscore)
    "NASDAQ_CLOSE",     # 美股 Nasdaq 收盤 (zscore)
    "SP500_CLOSE",      # 美股 S&P500 收盤 (zscore)
    "DOWJONES_CLOSE",   # 美股道瓊收盤 (zscore)
)

OPERATOR_NAMES = (
    "ADD", "SUB", "MUL", "DIV", "NEG", "ABS",
    "SIGN", "GATE", "JUMP", "DECAY", "DELAY1", "MAX3",
)

OPERATOR_ARITY = [2, 2, 2, 2, 1, 1, 1, 3, 1, 1, 1, 1]
N_FEATURES = len(FEATURE_NAMES)  # 22
N_OPERATORS = len(OPERATOR_NAMES)  # 12
VOCAB_SIZE = N_FEATURES + N_OPERATORS  # 34


# ============================================================
# 2. StackVM — 公式執行虛擬機
# ============================================================

class StackVM:
    """堆疊虛擬機 — 執行公式 token 序列"""

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
        if op_idx == 4:   return -a
        if op_idx == 5:   return np.abs(a)
        if op_idx == 6:   return np.sign(a)
        if op_idx == 8:   return np.where(np.abs((a - np.mean(a)) / (np.std(a) + 1e-6)) > 3, np.sign(a), 0)
        if op_idx == 9:   return 0.8 * a + 0.6 * np.roll(a, 1)
        if op_idx == 10:  return np.roll(a, 1)
        if op_idx == 11:  return np.maximum(np.maximum(a, np.roll(a, 1)), np.roll(a, 2))
        return a

    @staticmethod
    def _apply_binary(op_idx: int, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        if op_idx == 0: return a + b
        if op_idx == 1: return a - b
        if op_idx == 2: return a * b
        if op_idx == 3: return a / (b + 1e-6)
        return a

    @staticmethod
    def _apply_ternary(op_idx: int, a, b, c):
        if op_idx == 7: return np.where(c > 0, a, b)
        return a



# ============================================================
# 2.5 StackVMState — 引導式解碼的棧狀態追蹤器
# ============================================================

class StackVMState:
    """追蹤 StackVM 棧狀態，推導當前位置可用的合法 token
    
    核心邏輯：根據棧深度和剩餘位置，計算哪些 token 可以讓
    公式最終合法（stack_depth=1）。
    
    規則：
    - 特徵 token (t < N_FEATURES): push → stack_depth += 1
    - 運算子 token (t >= N_FEATURES): pop arity, push 1 → stack_depth -= (arity-1)
    - 棧深度不能超過 max_stack_depth
    - 最終 stack_depth 必須為 1
    """
    
    def __init__(self, max_stack_depth: int = 3):
        self.stack_depth = 0
        self.max_stack = max_stack_depth
    
    def reset(self):
        self.stack_depth = 0
    
    def get_valid_tokens(self, position: int, remaining: int) -> set:
        """根據當前棧狀態和剩餘位置，推導合法 token"""
        valid = set()
        
        # 特徵 token: push
        if self.stack_depth < self.max_stack:
            # 檢查推入後能否在剩餘位置內降到 depth=1
            new_depth = self.stack_depth + 1
            # 最快降法：每個二元運算子淨消耗1
            min_needed = new_depth - 1
            if remaining > 0:  # 至少還有當前這步
                valid.update(range(N_FEATURES))
        
        # 運算子 token: pop arity, push 1
        for op_idx in range(N_OPERATORS):
            arity = OPERATOR_ARITY[op_idx]
            if self.stack_depth >= arity:
                new_depth = self.stack_depth - arity + 1
                # 檢查剩餘位置能否讓 new_depth 降到 1
                min_needed = new_depth - 1
                if remaining - 1 >= min_needed:
                    valid.add(N_FEATURES + op_idx)
        
        return valid
    
    def apply_token(self, token: int):
        """更新棧狀態"""
        if token < N_FEATURES:
            self.stack_depth += 1
        else:
            op_idx = token - N_FEATURES
            arity = OPERATOR_ARITY[op_idx]
            self.stack_depth = self.stack_depth - arity + 1
    
    def is_complete(self) -> bool:
        """公式是否完整（stack_depth=1）"""
        return self.stack_depth == 1
    
    def must_end(self, remaining: int) -> bool:
        """是否必須結束（只剩特徵推入的空間不足以消減到1）"""
        if self.stack_depth == 1:
            return True
        # 如果繼續推入特徵，剩餘位置無法消減到1
        max_possible_push = min(self.max_stack - self.stack_depth, remaining)
        worst_depth = self.stack_depth + max_possible_push
        min_reduce = remaining - max_possible_push  # 可用於運算子的位置
        if worst_depth - min_reduce > 1:
            return True
        return False




# ============================================================
# 2.5 StackVMState — 引導式解碼的棧狀態追蹤器 (v3.1 修復)
class StockRegime(Enum):
    LARGE_CAP = "large_cap"
    MID_CAP_TECH = "mid_cap_tech"
    TRADITIONAL = "traditional"
    FINANCIAL = "financial"

KNOWN_REGIMES = {
    "2330": StockRegime.LARGE_CAP,
    "2308": StockRegime.LARGE_CAP,
    "2412": StockRegime.LARGE_CAP,
    "2311": StockRegime.LARGE_CAP,
    "2454": StockRegime.MID_CAP_TECH,
    "2382": StockRegime.MID_CAP_TECH,
    "3008": StockRegime.MID_CAP_TECH,
    "3034": StockRegime.MID_CAP_TECH,
    "3711": StockRegime.MID_CAP_TECH,
    "2303": StockRegime.MID_CAP_TECH,
    "1301": StockRegime.TRADITIONAL,
    "1303": StockRegime.TRADITIONAL,
    "1326": StockRegime.TRADITIONAL,
    "1101": StockRegime.TRADITIONAL,
    "2002": StockRegime.TRADITIONAL,
    "2882": StockRegime.FINANCIAL,
    "2886": StockRegime.FINANCIAL,
    "2891": StockRegime.FINANCIAL,
    "2884": StockRegime.FINANCIAL,
    "2881": StockRegime.FINANCIAL,
}


# ============================================================
# 4. RegimeConfig — 各 regime 訓練配置
# ============================================================

@dataclass
class RegimeConfig:
    feature_weights: Dict[StockRegime, Dict[str, float]] = field(default_factory=lambda: {
        StockRegime.LARGE_CAP: {
            "RET": 1.0, "LIQ_SCORE": 1.0, "PRESSURE": 1.5,
            "FOMO": 0.3, "DEV": 1.2, "LOG_VOL": 1.0,
            "INST_FLOW": 2.0, "MARGIN_PRESS": 0.5,
            "FIVE_DAY_HIGH": 1.0, "VOL_BREAKOUT": 1.0,
            "CVD_PROXY": 1.0, "ABSORPTION": 0.5,
            "SURF_ENTRY": 0.3, "ATR": 1.0,
            "CLOSE_POS": 1.0, "MOM_REV": 0.5,
            # v3.1 新增期貨OI+美股因子 [2026-06-11]
            "TX_INST_NET_OI": 1.5, "MTX_RETAIL_OI": 0.8,
            "TX_MTX_SPREAD": 0.5, "NASDAQ_CLOSE": 1.5,
            "SP500_CLOSE": 1.3, "DOWJONES_CLOSE": 1.0,
        },
        StockRegime.MID_CAP_TECH: {
            "RET": 1.0, "LIQ_SCORE": 1.0, "PRESSURE": 1.0,
            "FOMO": 1.2, "DEV": 1.0, "LOG_VOL": 1.0,
            "INST_FLOW": 0.8, "MARGIN_PRESS": 1.0,
            "FIVE_DAY_HIGH": 1.5, "VOL_BREAKOUT": 1.5,
            "CVD_PROXY": 1.5, "ABSORPTION": 1.0,
            "SURF_ENTRY": 1.2, "ATR": 1.0,
            "CLOSE_POS": 1.0, "MOM_REV": 1.2,
            # v3.1 新增期貨OI+美股因子 [2026-06-11]
            "TX_INST_NET_OI": 1.2, "MTX_RETAIL_OI": 1.5,
            "TX_MTX_SPREAD": 1.3, "NASDAQ_CLOSE": 1.2,
            "SP500_CLOSE": 1.0, "DOWJONES_CLOSE": 0.8,
        },
        StockRegime.TRADITIONAL: {
            "RET": 1.0, "LIQ_SCORE": 1.0, "PRESSURE": 0.8,
            "FOMO": 0.5, "DEV": 1.5, "LOG_VOL": 1.0,
            "INST_FLOW": 1.0, "MARGIN_PRESS": 0.8,
            "FIVE_DAY_HIGH": 1.2, "VOL_BREAKOUT": 1.5,
            "CVD_PROXY": 0.5, "ABSORPTION": 0.3,
            "SURF_ENTRY": 0.3, "ATR": 1.0,
            "CLOSE_POS": 1.0, "MOM_REV": 1.0,
            # v3.1 新增期貨OI+美股因子 [2026-06-11]
            "TX_INST_NET_OI": 0.8, "MTX_RETAIL_OI": 0.5,
            "TX_MTX_SPREAD": 0.3, "NASDAQ_CLOSE": 0.8,
            "SP500_CLOSE": 0.8, "DOWJONES_CLOSE": 1.0,
        },
        StockRegime.FINANCIAL: {
            "RET": 1.0, "LIQ_SCORE": 1.5, "PRESSURE": 0.8,
            "FOMO": 0.3, "DEV": 1.5, "LOG_VOL": 1.0,
            "INST_FLOW": 1.0, "MARGIN_PRESS": 0.5,
            "FIVE_DAY_HIGH": 0.8, "VOL_BREAKOUT": 0.8,
            "CVD_PROXY": 0.5, "ABSORPTION": 0.3,
            "SURF_ENTRY": 0.3, "ATR": 1.2,
            "CLOSE_POS": 1.5, "MOM_REV": 0.5,
            # v3.1 新增期貨OI+美股因子 [2026-06-11]
            "TX_INST_NET_OI": 0.3, "MTX_RETAIL_OI": 0.3,
            "TX_MTX_SPREAD": 0.3, "NASDAQ_CLOSE": 0.5,
            "SP500_CLOSE": 0.5, "DOWJONES_CLOSE": 0.8,
        },
    })

    operator_mask: Dict[StockRegime, Dict[str, bool]] = field(default_factory=lambda: {
        StockRegime.LARGE_CAP: {n: True for n in OPERATOR_NAMES},
        StockRegime.MID_CAP_TECH: {n: True for n in OPERATOR_NAMES},
        StockRegime.TRADITIONAL: {**{n: True for n in OPERATOR_NAMES}, "SIGN": False, "JUMP": False},
        StockRegime.FINANCIAL: {**{n: True for n in OPERATOR_NAMES}, "SIGN": False, "JUMP": False},
    })

    training_params: Dict[StockRegime, Dict] = field(default_factory=lambda: {
        StockRegime.LARGE_CAP: {"group_size": 8, "target_holding_days": 5, "reward_horizon": 5,
                                "focus": "法人籌碼+買賣壓力，抑制散戶指標"},
        StockRegime.MID_CAP_TECH: {"group_size": 6, "target_holding_days": 4, "reward_horizon": 4,
                                   "focus": "技術突破+量價確認，五日高點/CVD/放量為核心"},
        StockRegime.TRADITIONAL: {"group_size": 4, "target_holding_days": 5, "reward_horizon": 5,
                                  "focus": "營收驅動+放量結構，抑制CVD/吸收等高頻指標"},
        StockRegime.FINANCIAL: {"group_size": 4, "target_holding_days": 7, "reward_horizon": 7,
                                "focus": "均值回歸+位置指標，長持倉窗口"},
    })


# ============================================================
# 5. RegimeTrainingPlan
# ============================================================

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
            "stock_id": stock_id,
            "regime": regime,
            "feature_weights": feature_weights,
            "feature_mask": feature_mask,
            "operator_mask": operator_mask,
            "group_size": params["group_size"],
            "target_holding_days": params["target_holding_days"],
            "reward_horizon": params["reward_horizon"],
            "focus_description": params["focus"],
        }


# ============================================================
# 6. 特徵工程 (TWFeatureEngineer — 自含版)
# ============================================================

class TWFeatureEngineer:
    """台股 16 維因子工程"""

    NORM_WINDOW = 60
    NORM_CLIP = 5.0

    @staticmethod
    def compute_features(df: pd.DataFrame, inst_df: pd.DataFrame = None,
                         margin_df: pd.DataFrame = None,
                         futures_oi_df: pd.DataFrame = None,
                         us_indices_df: pd.DataFrame = None) -> pd.DataFrame:
        result_frames = []

        # --- Pre-process auxiliary DataFrames (once, outside loop) ---
        # 期貨 OI: TX / MTX 分別 pivot，避免迴圈內重複處理
        tx_oi = None
        mtx_oi = None
        if futures_oi_df is not None and len(futures_oi_df) > 0:
            foi = futures_oi_df.copy()
            foi["date"] = pd.to_datetime(foi["date"])
            tx_oi = foi[foi["futures_id"] == "TX"][["date", "inst_net_oi", "retail_net_oi"]].copy()
            tx_oi = tx_oi.rename(columns={"inst_net_oi": "tx_inst_net_oi",
                                          "retail_net_oi": "tx_retail_net_oi"})
            mtx_oi = foi[foi["futures_id"] == "MTX"][["date", "inst_net_oi", "retail_net_oi"]].copy()
            mtx_oi = mtx_oi.rename(columns={"inst_net_oi": "mtx_inst_net_oi",
                                            "retail_net_oi": "mtx_retail_net_oi"})

        # 美股指數: 逐指數 pivot
        us_dfs = {}
        if us_indices_df is not None and len(us_indices_df) > 0:
            us = us_indices_df.copy()
            us["date"] = pd.to_datetime(us["date"])
            for idx_name, feat_name in [("Nasdaq", "nasdaq_close_raw"),
                                        ("SP500", "sp500_close_raw"),
                                        ("DowJones", "dowjones_close_raw")]:
                idx_data = us[us["index_name"] == idx_name][["date", "close"]].copy()
                idx_data = idx_data.rename(columns={"close": feat_name})
                us_dfs[feat_name] = idx_data

        # 期貨 spread 預計算
        foi_spread = None
        if tx_oi is not None and mtx_oi is not None:
            tx_s = tx_oi[["date", "tx_inst_net_oi"]].copy()
            mtx_s = mtx_oi[["date", "mtx_inst_net_oi"]].copy()
            foi_spread = tx_s.merge(mtx_s, on="date", how="outer").sort_values("date")
            foi_spread["tx_mtx_spread_raw"] = (
                foi_spread["tx_inst_net_oi"].ffill().fillna(0)
                - foi_spread["mtx_inst_net_oi"].ffill().fillna(0)
            )
            foi_spread = foi_spread[["date", "tx_mtx_spread_raw"]]

        for stock_id, group in df.groupby("stock_id"):
            # 關鍵修復 v3.2: reset_index(drop=True) 消除 groupby multi-index
            # 避免後續 reset_index() 時 level_0 衝突
            g = group.sort_values("date").copy().reset_index(drop=True)
            g["date"] = pd.to_datetime(g["date"])

            # --- 原始 6 因子 ---
            g["ret"] = np.log(g["close"] / g["close"].shift(1))
            g["liq_score"] = g["volume"] / (g["volume"].rolling(20).mean() + 1e-6)
            g["pressure"] = np.tanh(
                3.0 * (g["close"] - g["open"]) / (g["high"] - g["low"] + 1e-6)
            )
            vol_chg = g["volume"].pct_change()
            g["fomo"] = vol_chg - vol_chg.shift(1)
            ma20 = g["close"].rolling(20).mean()
            g["dev"] = (g["close"] - ma20) / (ma20 + 1e-6)
            g["log_vol"] = np.log1p(g["volume"])

            # --- Marcus + Wenty 10 因子 ---
            # 三大法人 — 使用 merge 取代 set_index/reindex (v3.2 fix)
            if inst_df is not None and len(inst_df) > 0:
                inst_data = inst_df[inst_df["stock_id"] == stock_id].copy()
                if len(inst_data) > 0:
                    inst_data["date"] = pd.to_datetime(inst_data["date"])
                    inst_data = inst_data.sort_values("date")
                    net_col = "total_net" if "total_net" in inst_data.columns else "foreign_net"
                    if net_col not in inst_data.columns:
                        net_col = "net_buy"
                    if net_col in inst_data.columns:
                        inst_merge = inst_data[["date", net_col]].copy()
                        inst_merge = inst_merge.rename(columns={net_col: "inst_flow"})
                        g = g.merge(inst_merge, on="date", how="left")
                        g["inst_flow"] = g["inst_flow"].ffill().fillna(0)
                    else:
                        g["inst_flow"] = 0
                else:
                    g["inst_flow"] = 0
            else:
                g["inst_flow"] = 0

            # 融資壓力 — 使用 merge (v3.2 fix)
            if margin_df is not None and len(margin_df) > 0:
                margin_data = margin_df[margin_df["stock_id"] == stock_id].copy()
                if len(margin_data) > 0:
                    margin_data["date"] = pd.to_datetime(margin_data["date"])
                    margin_data = margin_data.sort_values("date")
                    if "margin_balance" in margin_data.columns:
                        margin_merge = margin_data[["date", "margin_balance"]].copy()
                        g = g.merge(margin_merge, on="date", how="left")
                        g["margin_balance"] = g["margin_balance"].ffill()
                        g["margin_press"] = g["margin_balance"].pct_change(5).fillna(0)
                        g = g.drop(columns=["margin_balance"])
                    elif "margin_buy" in margin_data.columns:
                        margin_merge = margin_data[["date", "margin_buy"]].copy()
                        g = g.merge(margin_merge, on="date", how="left")
                        g["margin_buy"] = g["margin_buy"].ffill().fillna(0)
                        g["margin_press"] = g["margin_buy"].rolling(5).mean().fillna(0)
                        g = g.drop(columns=["margin_buy"])
                    else:
                        g["margin_press"] = 0
                else:
                    g["margin_press"] = 0
            else:
                g["margin_press"] = 0

            # 五日高點突破
            high5 = g["close"].rolling(5).max()
            g["five_day_high"] = (g["close"] - high5) / (high5 + 1e-6)

            # 放量結構突破
            vol_ma5 = g["volume"].rolling(5).mean()
            g["vol_breakout"] = g["volume"] / (vol_ma5 + 1e-6)

            # CVD 代理
            cvd_intraday = (g["close"] - g["open"]) / (g["high"] - g["low"] + 1e-6) * g["volume"]
            g["cvd_proxy"] = cvd_intraday.rolling(20).sum() / (g["volume"].rolling(20).mean() * 20 + 1e-6)

            # 吸收現象
            g["absorption"] = (g["high"] - g["close"]) / (g["high"] - g["low"] + 1e-6) * g["volume"]

            # --- v3.1: 期貨法人未平倉因子 ---
            # 使用 merge 取代 set_index/reindex (v3.2 fix)
            # 市場級別訊號，broadcast 到所有個股
            if tx_oi is not None:
                g = g.merge(tx_oi[["date", "tx_inst_net_oi"]], on="date", how="left")
                g["tx_inst_net_oi_raw"] = g["tx_inst_net_oi"].ffill().fillna(0)
                g = g.drop(columns=["tx_inst_net_oi"])
            else:
                g["tx_inst_net_oi_raw"] = 0

            if mtx_oi is not None:
                g = g.merge(mtx_oi[["date", "mtx_retail_net_oi"]], on="date", how="left")
                g["mtx_retail_oi_raw"] = g["mtx_retail_net_oi"].ffill().fillna(0)
                g = g.drop(columns=["mtx_retail_net_oi"])
            else:
                g["mtx_retail_oi_raw"] = 0

            # 大台-小台法人OI差
            if foi_spread is not None:
                g = g.merge(foi_spread, on="date", how="left")
                g["tx_mtx_spread_raw"] = g["tx_mtx_spread_raw"].ffill().fillna(0)
            else:
                g["tx_mtx_spread_raw"] = 0

            # --- v3.1: 美股指數因子 ---
            # 使用 merge 取代 set_index/reindex (v3.2 fix)
            # v6.0 修復: ffill 限制 2 天，超過標記為 NaN (stale data 保護)
            if us_dfs:
                for feat_name, us_df in us_dfs.items():
                    if feat_name in g.columns:
                        continue
                    g = g.merge(us_df, on="date", how="left")
                    # 記錄原始數據有效性
                    col_name = feat_name.replace("_raw", "")
                    valid_col = f"{col_name}_valid"
                    g[valid_col] = g[feat_name].notna().astype(int)
                    # ffill，但限制連續填充天數 <= 2
                    g[feat_name] = g[feat_name].ffill(limit=2)
                    # 超過 2 天仍為空的，標記為 NaN（之後 fillna(0)）
                # 確保三個因子都存在
                for feat_name in ["nasdaq_close_raw", "sp500_close_raw", "dowjones_close_raw"]:
                    if feat_name not in g.columns:
                        g[feat_name] = 0
            else:
                g["nasdaq_close_raw"] = 0
                g["sp500_close_raw"] = 0
                g["dowjones_close_raw"] = 0

            # 衝浪手切入
            key_level = g["close"].rolling(20).mean()
            g["surf_entry"] = np.where(
                np.abs(g["close"] - key_level) / (key_level + 1e-6) < 0.01, 1.0, 0.0
            )

            # ATR
            high, low, close = g["high"].values, g["low"].values, g["close"].values
            prev_close = np.roll(close, 1)
            prev_close[0] = close[0]
            tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
            atr14 = pd.Series(tr).rolling(14).mean()
            g["atr"] = atr14 / (close + 1e-6)

            # 收盤位置
            g["close_pos"] = (g["close"] - g["low"]) / (g["high"] - g["low"] + 1e-6)

            # 動量反轉
            g["mom_rev"] = -1 * g["ret"].rolling(5).sum()

            # --- v3.1: Raw → FEATURE_NAMES 映射 ---
            raw_to_feat = {
                "tx_inst_net_oi_raw": "TX_INST_NET_OI",
                "mtx_retail_oi_raw": "MTX_RETAIL_OI",
                "tx_mtx_spread_raw": "TX_MTX_SPREAD",
                "nasdaq_close_raw": "NASDAQ_CLOSE",
                "sp500_close_raw": "SP500_CLOSE",
                "dowjones_close_raw": "DOWJONES_CLOSE",
            }
            for raw_name, feat_name in raw_to_feat.items():
                if raw_name in g.columns and feat_name not in g.columns:
                    g[feat_name] = g[raw_name]
                    g = g.drop(columns=[raw_name])
                elif raw_name not in g.columns and feat_name not in g.columns:
                    g[feat_name] = 0

            # --- 原始小寫欄位 → 大寫 FEATURE_NAMES 映射 (v3.2 修復) ---
            _lower_to_upper = {
                "ret": "RET", "liq_score": "LIQ_SCORE", "pressure": "PRESSURE",
                "fomo": "FOMO", "dev": "DEV", "log_vol": "LOG_VOL",
                "inst_flow": "INST_FLOW", "margin_press": "MARGIN_PRESS",
                "five_day_high": "FIVE_DAY_HIGH", "vol_breakout": "VOL_BREAKOUT",
                "cvd_proxy": "CVD_PROXY", "absorption": "ABSORPTION",
                "surf_entry": "SURF_ENTRY", "atr": "ATR", "close_pos": "CLOSE_POS",
                "mom_rev": "MOM_REV",
            }
            for _lower, _upper in _lower_to_upper.items():
                if _lower in g.columns and _upper not in g.columns:
                    g[_upper] = g[_lower]
                    g = g.drop(columns=[_lower])
                elif _lower in g.columns and _upper in g.columns:
                    g[_upper] = g[_lower]
                    g = g.drop(columns=[_lower])

            # --- Rolling Zscore 正規化 ---
            all_feat = FEATURE_NAMES
            for feat in all_feat:
                if feat not in g.columns:
                    g[feat] = 0
                    continue
                col = g[feat].astype(float)
                roll_mean = col.rolling(TWFeatureEngineer.NORM_WINDOW, min_periods=10).mean()
                roll_std = col.rolling(TWFeatureEngineer.NORM_WINDOW, min_periods=10).std()
                exp_mean = col.expanding(min_periods=10).mean()
                exp_std = col.expanding(min_periods=10).std()
                mask = roll_mean.isna()
                roll_mean = roll_mean.fillna(exp_mean)
                roll_std = roll_std.fillna(exp_std)
                roll_std = roll_std.replace(0, 1)
                zscore = (col - roll_mean) / roll_std
                g[feat] = zscore.clip(-TWFeatureEngineer.NORM_CLIP, TWFeatureEngineer.NORM_CLIP)

            # v6.0: 對所有 22 因子進行最終 fillna(0)，處理 ffill 限制後的 NaN
            for feat in FEATURE_NAMES:
                if feat in g.columns:
                    g[feat] = g[feat].fillna(0)

            # 只保留 date + stock_id + 22 個大寫特徵 (v3.3 fix)
        keep_cols = ["date", "stock_id", "close"] + list(FEATURE_NAMES)
        result_frames.append(g[keep_cols])

        result = pd.concat(result_frames, ignore_index=True)
        return result


# ============================================================
# 7. 合成數據生成器
# ============================================================

def generate_synthetic_data(n_days: int = 500, seed: int = 42):
    """生成 4 檔代表性標的的合成日 K 數據 + 期貨 OI + 美股指數

    Returns:
        (ohlcv_df, inst_df, margin_df, futures_oi_df, us_indices_df)
    """
    np.random.seed(seed)
    dates = pd.bdate_range(end="2025-12-31", periods=n_days)

    configs = {
        "2330": {"price": 800, "vol": 60000, "atr_pct": 0.020, "name": "台積電"},
        "2454": {"price": 1200, "vol": 15000, "atr_pct": 0.030, "name": "聯發科"},
        "1301": {"price": 100, "vol": 8000, "atr_pct": 0.022, "name": "台塑"},
        "2882": {"price": 60, "vol": 30000, "atr_pct": 0.018, "name": "國泰金"},
    }

    # === 0. Alpha signal injection (v3.3) ===
    # Inject learnable alpha signals so features have predictive power over returns
    # This fixes the "no learnable signal" root cause of zero convergence
    alpha_config = {
        "2330": {"features": ["RET", "INST_FLOW", "TX_INST_NET_OI", "NASDAQ_CLOSE"],
                 "weights": [0.3, 0.25, 0.2, 0.15], "scale": 0.005},
        "2454": {"features": ["RET", "VOL_BREAKOUT", "FIVE_DAY_HIGH", "NASDAQ_CLOSE"],
                 "weights": [0.3, 0.2, 0.2, 0.2], "scale": 0.006},
        "1301": {"features": ["MOM_REV", "MARGIN_PRESS", "TX_MTX_SPREAD", "SP500_CLOSE"],
                 "weights": [0.25, 0.25, 0.25, 0.15], "scale": 0.004},
        "2882": {"features": ["PRESSURE", "CLOSE_POS", "TX_INST_NET_OI", "DOWJONES_CLOSE"],
                 "weights": [0.3, 0.2, 0.2, 0.2], "scale": 0.003},
    }
    # Pre-generate correlated alpha factor signals
    alpha_signals = {}
    for sid in configs:
        ac = alpha_config[sid]
        n = len(dates)
        alpha_mat = np.zeros((len(ac["features"]), n))
        for fi in range(len(ac["features"])):
            raw = np.random.normal(0, 1, n)
            for t in range(1, n):
                raw[t] = 0.7 * raw[t-1] + 0.3 * raw[t]
            alpha_mat[fi] = raw / (np.std(raw) + 1e-6)
        alpha_signals[sid] = alpha_mat

    # === 1. OHLCV ===
    records = []
    for sid, cfg in configs.items():
        price = cfg["price"]
        trend = 0.0003 if sid in ("2330", "2454") else 0.0
        ac = alpha_config[sid]
        weights = ac["weights"]
        scale = ac["scale"]
        amat = alpha_signals[sid]
        for di, d in enumerate(dates):
            # v3.3: inject alpha signal into returns
            alpha_component = sum(weights[fi] * amat[fi, di] for fi in range(len(weights)))
            noise = np.random.normal(0, cfg["atr_pct"] * 0.3)
            ret = trend + scale * alpha_component + noise
            price *= (1 + ret)
            h = price * (1 + abs(np.random.normal(0, cfg["atr_pct"] * 0.5)))
            l = price * (1 - abs(np.random.normal(0, cfg["atr_pct"] * 0.5)))
            o = price * (1 + np.random.normal(0, 0.003))
            records.append({
                "date": d, "stock_id": sid,
                "open": o, "high": h, "low": l, "close": price,
                "volume": int(cfg["vol"] * (1 + np.random.normal(0, 0.3))),
            })

    ohlcv_df = pd.DataFrame(records)
    print(f"  合成 OHLCV: {len(ohlcv_df)} 筆, {ohlcv_df['stock_id'].nunique()} 檔, {n_days} 天")

    # === 2. 期貨三大法人 OI (合成) ===
    foi_records = []
    for fid, base_oi in [("TX", 50000), ("MTX", 30000)]:
        oi_level = base_oi
        for d in dates:
            # 法人淨 OI: 隨機波動，帶微趨勢
            oi_change = np.random.normal(0, base_oi * 0.05)
            oi_level = oi_level * 0.98 + oi_change  # mean-reverting
            # 散戶 = -法人 (零和)
            inst_net = int(oi_level)
            retail_net = -inst_net
            # 分法人
            foreign_frac = np.random.uniform(0.5, 0.7)
            trust_frac = np.random.uniform(0.1, 0.25)
            dealer_frac = 1.0 - foreign_frac - trust_frac

            foi_records.append({
                "date": d, "futures_id": fid,
                "foreign_long_oi": int(abs(inst_net) * foreign_frac * 0.6),
                "foreign_short_oi": int(abs(inst_net) * foreign_frac * 0.4),
                "trust_long_oi": int(abs(inst_net) * trust_frac * 0.55),
                "trust_short_oi": int(abs(inst_net) * trust_frac * 0.45),
                "dealer_long_oi": int(abs(inst_net) * dealer_frac * 0.5),
                "dealer_short_oi": int(abs(inst_net) * dealer_frac * 0.5),
                "inst_net_oi": inst_net,
                "retail_net_oi": retail_net,
                "retail_long_oi": abs(retail_net) if retail_net > 0 else 0,
                "retail_short_oi": abs(retail_net) if retail_net < 0 else 0,
            })

    futures_oi_df = pd.DataFrame(foi_records)
    print(f"  合成 期貨OI: {len(futures_oi_df)} 筆 (TX+MTX)")

    # === 3. 美股三大指數 (合成) ===
    us_records = []
    idx_configs = {
        "Nasdaq": {"price": 18000, "vol_pct": 0.015},
        "SP500":  {"price": 5500,  "vol_pct": 0.010},
        "DowJones": {"price": 42000, "vol_pct": 0.008},
    }
    for idx_name, icfg in idx_configs.items():
        price = icfg["price"]
        for d in dates:
            ret = np.random.normal(0.0002, icfg["vol_pct"])
            price *= (1 + ret)
            us_records.append({
                "date": d, "index_name": idx_name,
                "open": price * (1 + np.random.normal(0, 0.002)),
                "high": price * (1 + abs(np.random.normal(0, icfg["vol_pct"] * 0.5))),
                "low": price * (1 - abs(np.random.normal(0, icfg["vol_pct"] * 0.5))),
                "close": price,
                "volume": int(1e9 * (1 + np.random.normal(0, 0.2))),
            })

    us_indices_df = pd.DataFrame(us_records)
    print(f"  合成 美股指數: {len(us_indices_df)} 筆 (3 指數)")

    # === 4. 三大法人買賣超 (合成) ===
    inst_records = []
    for sid in configs:
        inst_level = 0
        for d in dates:
            inst_level = inst_level * 0.95 + np.random.normal(0, 500)
            inst_records.append({
                "date": d, "stock_id": sid,
                "foreign_net": int(inst_level * 0.6),
                "trust_net": int(inst_level * 0.2),
                "dealer_net": int(inst_level * 0.2),
                "total_net": int(inst_level),
            })
    inst_df = pd.DataFrame(inst_records)
    print(f" 合成 三大法人: {len(inst_df)} 筆")
 
    # === 5. 融資融券 (合成) ===
    margin_records = []
    for sid in configs:
        margin_level = 50000 if sid in ("2330", "2454") else 20000
        for d in dates:
            margin_level = margin_level * 0.99 + np.random.normal(0, margin_level * 0.02)
            margin_records.append({
                "date": d, "stock_id": sid,
                "margin_balance": int(margin_level),
                "margin_buy": int(abs(margin_level * 0.05 * np.random.normal())),
                "short_balance": int(margin_level * 0.3),
            })
    margin_df = pd.DataFrame(margin_records)
    print(f" 合成 融資融券: {len(margin_df)} 筆")

    return ohlcv_df, inst_df, margin_df, futures_oi_df, us_indices_df


# ============================================================
# 8. GRPOConfig
# ============================================================

@dataclass
class GRPOConfig:
    group_size: int = 8
    d_model: int = 64
    nhead: int = 4
    num_layers: int = 2
    dim_feedforward: int = 128
    num_loops: int = 2
    vocab_size: int = 34
    max_formula_len: int = 15

    batch_size: int = 128
    train_steps: int = 20000
    lr: float = 3e-4
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

    clip_eps: float = 0.2  # GRPO clipped importance sampling epsilon

    # --- 引導式解碼 (v3.1 修復零收斂) ---
    guided_decoding: bool = True
    warmup_steps: int = 500
    max_stack_depth: int = 3
    device: str = "cpu"

    @classmethod
    def auto_detect(cls) -> "GRPOConfig":
        config = cls()
        force_cpu = os.environ.get("GRPO_FORCE_CPU", "0") == "1"
        try:
            import torch
            if torch.cuda.is_available() and not force_cpu:
                config.device = "cuda"
                config.group_size = 8
                config.batch_size = 128
                config.train_steps = 20000
            else:
                config.device = "cpu"
                config.group_size = 4
                config.batch_size = 16
                config.train_steps = 3000
                if force_cpu:
                    print(f"  [GRPOConfig] CUDA 不相容，使用 CPU: G=4, batch=16, steps=3000")
        except ImportError:
            pass
        return config


# ============================================================
# 8.5 GitHub 即時監控 — 訓練日誌推送
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
            # Test auth
            req = urllib.request.Request(
                f"https://api.github.com/repos/{repo}",
                headers={"Authorization": f"token {token}",
                         "User-Agent": "AlphaGPT-Kaggle"}
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        print(f"  [GitHubLog] Auth OK, repo={repo}")
                    else:
                        self.enabled = False
            except Exception as e:
                print(f"  [GitHubLog] Auth FAILED: {e}")
                self.enabled = False
        else:
            print(f"  [GitHubLog] Disabled (no GITHUB_TOKEN)")
    
    def _get_session(self):
        """Lazy init HTTP session"""
        if self._session is None:
            import urllib.request
            self._session = urllib.request
        return self._session
    
    def _push_file(self, path: str, content: str, sha: str = None):
        """Push or update a file on GitHub via API"""
        if not self.enabled:
            return False
        
        import urllib.request
        import urllib.error
        import base64
        import json
        
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
            url, data=json.dumps(data).encode(), headers=headers, method="PUT"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                return result.get("content", {}).get("sha")
        except urllib.error.HTTPError as e:
            if e.code == 409 and not sha:
                # 409 Conflict = file exists, need SHA for update
                try:
                    body = e.read().decode()
                    # Get current SHA
                    get_req = urllib.request.Request(
                        url, headers={"Authorization": f"token {self.token}",
                                      "User-Agent": "AlphaGPT-Kaggle"}
                    )
                    with urllib.request.urlopen(get_req, timeout=10) as get_resp:
                        file_info = json.loads(get_resp.read().decode())
                        current_sha = file_info.get("sha")
                        if current_sha:
                            return self._push_file(path, content, sha=current_sha)
                except Exception:
                    pass
            return False
        except Exception as e:
            print(f"  [GitHubLog] Push error: {e}")
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
            **metrics
        }
        
        # Push as a single-line JSON append to logs/training_log.jsonl
        log_line = _json.dumps(log_entry, ensure_ascii=False) + "\n"
        
        # For simplicity, push the latest metrics as a small file
        # rather than trying to append (GitHub API doesn't support append)
        metrics_path = f"kaggle-logs/{regime}/latest_metrics.json"
        self._push_file(metrics_path, _json.dumps(log_entry, indent=2, ensure_ascii=False))
        
        # Also push a summary line file
        summary_line = (f"{log_entry['timestamp']} | {regime} | step={step} | "
                        f"loss={metrics.get('loss', 0):.4f} | "
                        f"mean_r={metrics.get('mean_reward', 0):.3f} | "
                        f"best_r={metrics.get('best_reward', 0):.3f} | "
                        f"clip_ratio={metrics.get('clip_ratio', 0):.1%}\n")
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
        self._push_file(final_path, _json.dumps(final_data, indent=2, ensure_ascii=False))
        
        # Push history as well
        history = result.get("history", [])
        hist_serializable = []
        for entry in history:
            h = {}
            for k, v in entry.items():
                h[k] = float(v) if isinstance(v, (np.integer, np.floating)) else v
            hist_serializable.append(h)
        
        hist_path = f"kaggle-logs/{regime}/training_history.json"
        self._push_file(hist_path, _json.dumps(hist_serializable, indent=2))
        
        print(f"  [GitHubLog] Final result pushed for {regime}")



# ============================================================
# 9. GRPO 獎勵計算
# ============================================================

class GRPORewardCalculator:
    def __init__(self, config: GRPOConfig = None):
        self.config = config or GRPOConfig()
        self.vm = StackVM()

    @staticmethod
    def _spearman_corr(x: np.ndarray, y: np.ndarray) -> float:
        """不依賴 scipy 的 Spearman 相關計算"""
        try:
            from scipy.stats import spearmanr
            r, _ = spearmanr(x, y)
            return r if not np.isnan(r) else 0.0
        except ImportError:
            # Fallback: rank correlation via numpy
            rx = np.argsort(np.argsort(x)).astype(float)
            ry = np.argsort(np.argsort(y)).astype(float)
            rx = (rx - rx.mean()) / (rx.std() + 1e-8)
            ry = (ry - ry.mean()) / (ry.std() + 1e-8)
            return float(np.mean(rx * ry))

    def _default_backtest(self, signal: np.ndarray, returns: np.ndarray) -> float:
        if signal is None or len(signal) != len(returns):
            return -5.0
        valid = np.isfinite(signal) & np.isfinite(returns)
        if valid.sum() < 10:
            return -5.0
        ic = self._spearman_corr(signal[valid], returns[valid])
        if np.isnan(ic):
            return -5.0
        return ic * 10

    def compute_group_rewards(self, group_tokens, feat_tensor, returns,
                              train_ic=0.0, val_ic=0.0, daily_turnover=0.0):
        G = len(group_tokens)
        rewards = []

        for tokens in group_tokens:
            signal = self.vm.execute(tokens, feat_tensor)
            if signal is None:
                rewards.append(-5.0)
                continue
            if np.std(signal) < 1e-4:
                rewards.append(-2.0)
                continue

            base_reward = self._default_backtest(signal, returns)

            # v5.6 P3 FIX: Length bonus for compound formulas
            # Encourages multi-factor expressions instead of single features
            n_tokens = len(tokens)
            if n_tokens >= 3:
                length_bonus = min(0.3, (n_tokens - 2) * 0.1)
                base_reward += length_bonus

            # v5.6 P3 FIX: Length bonus for compound formulas
            n_tokens = len(tokens)
            if n_tokens >= 3:
                length_bonus = min(0.3, (n_tokens - 2) * 0.1)  # up to +0.3 for 5+ tokens
                base_reward += length_bonus

            if self.config.use_overfit_penalty:
                ic_gap = max(0, train_ic - val_ic - self.config.ic_gap_threshold)
                ic_penalty = self.config.ic_gap_weight * ic_gap
                turnover_penalty = self.config.turnover_weight * max(0, daily_turnover - self.config.turnover_max)
                base_reward -= (ic_penalty + turnover_penalty)

            rewards.append(np.clip(base_reward, -self.config.reward_clip, self.config.reward_clip))

        rewards = np.array(rewards)
        valid_mask = rewards > -5.0

        if valid_mask.sum() > 1:
            group_mean = rewards[valid_mask].mean()
            group_std = rewards[valid_mask].std() + 1e-6
            advantages = (rewards - group_mean) / group_std
        elif valid_mask.sum() == 1:
            # 只有1個有效，給正優勢
            advantages = np.where(valid_mask, 1.0, -1.0).astype(float)
        else:
            # 全部無效 (v3.1 修復): 給予負優勢推動模型遠離無效公式
            # 不再返回全零 advantages（那是造成 loss=0 的根因）
            advantages = -np.ones(G)

        advantages = np.clip(advantages, -self.config.advantage_clip, self.config.advantage_clip)

        return {
            "rewards": rewards,
            "advantages": advantages,
            "valid_mask": valid_mask,
            "overfit_info": {"train_ic": train_ic, "val_ic": val_ic,
                             "ic_gap": train_ic - val_ic,
                             "is_overfit": (train_ic - val_ic) > 0.1},
            "group_mean_reward": rewards[valid_mask].mean() if valid_mask.sum() > 0 else 0.0,
            "best_idx": int(np.argmax(rewards)) if len(rewards) > 0 else 0,
        }


# ============================================================
# 10. LoopedTransformer (PyTorch) — AlphaGPT 核心設計
# ============================================================
# 核心特點:
#   - RMSNorm (非 LayerNorm) — 更穩定、計算量更低
#   - SwiGLU (非標準 FFN) — 門控線性單元，表達力更強
#   - QKNorm (Query-Key 正規化) — 防止 attention 溫度爆炸
#   - MTPHead (多任務池化輸出) — 多種池化策略合併
#   - Looped Transformer — 循環處理，小模型深層表達
#   - NewtonSchulzLowRankDecay (LoRD) — 低秩正則化
#   - StableRankMonitor — 監控參數穩定秩


# ============================================================
# 7.5 NaN 安全函數 (v3.4)
# ============================================================

def _safe_logits(logits, eps=1e-8):
    """Numerical safety for logits: replace NaN/Inf, ensure finite range.
    
    AlphaGPT v3.4 fix: prevents Categorical distribution crash
    when model forward pass produces NaN due to:
    - Looped Transformer value explosion
    - Gradient overflow between steps
    - RMSNorm division by near-zero
    """
    import torch
    logits = torch.where(torch.isnan(logits), torch.zeros_like(logits), logits)
    logits = torch.where(torch.isinf(logits), torch.sign(logits) * 20.0, logits)
    logits = torch.clamp(logits, -20.0, 20.0)
    return logits



import torch
import torch.nn as nn
import torch.nn.functional as F

class RMSNorm(nn.Module):
    """Root Mean Square Layer Normalization — 比 LayerNorm 更穩定高效"""
    def __init__(self, d_model, eps=1e-6):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(d_model))
        self.eps = eps

    def forward(self, x):
        rms = torch.sqrt(torch.mean(x ** 2, dim=-1, keepdim=True) + self.eps)
        return self.weight * (x / rms)





class SwiGLU(nn.Module):
    """Swish-Gated Linear Unit — 門控 FFN，表達力優於標準 FFN
        FFN_SwiGLU(x) = (W1 x + b1) * sigmoid(W1 x + b1) * (W2 x + b2)
        簡化: gate * up → down
        """
    def __init__(self, d_model, dim_feedforward, dropout=0.1):
        super().__init__()
        self.w_gate = nn.Linear(d_model, dim_feedforward, bias=False)
        self.w_up = nn.Linear(d_model, dim_feedforward, bias=False)
        self.w_down = nn.Linear(dim_feedforward, d_model, bias=False)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        gate = F.silu(self.w_gate(x))   # SiLU = Swish
        up = self.w_up(x)
        return self.dropout(self.w_down(gate * up))



class QKNormAttention(nn.Module):
    """Query-Key Normalized Multi-Head Attention
    防止 QK 點積爆炸，穩定訓練
    """
    def __init__(self, d_model, nhead, dropout=0.1):
        super().__init__()
        assert d_model % nhead == 0
        self.d_k = d_model // nhead
        self.nhead = nhead
        self.w_q = nn.Linear(d_model, d_model, bias=False)
        self.w_k = nn.Linear(d_model, d_model, bias=False)
        self.w_v = nn.Linear(d_model, d_model, bias=False)
        self.w_o = nn.Linear(d_model, d_model, bias=False)
        # QK Norm 可學習縮放
        self.q_norm = RMSNorm(self.d_k)
        self.k_norm = RMSNorm(self.d_k)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, mask=None):
        B, T, D = x.shape
        q = self.w_q(x).view(B, T, self.nhead, self.d_k).transpose(1, 2)
        k = self.w_k(x).view(B, T, self.nhead, self.d_k).transpose(1, 2)
        v = self.w_v(x).view(B, T, self.nhead, self.d_k).transpose(1, 2)

        # QK Normalization — 核心設計
        q = self.q_norm(q)
        k = self.k_norm(k)

        # Scaled dot-product (scale by sqrt(d_k) / nhead 比例)
        scale = self.d_k ** -0.5
        attn = torch.matmul(q, k.transpose(-2, -1)) * scale
        if mask is not None:
            attn = attn.masked_fill(mask == 0, float('-inf'))
        attn = F.softmax(attn, dim=-1)
        attn = self.dropout(attn)

        out = torch.matmul(attn, v)
        out = out.transpose(1, 2).contiguous().view(B, T, D)
        return self.w_o(out)



class MTPHead(nn.Module):
    """Multi-Task Pooling Head — 多種池化策略合併
    AlphaGPT 使用 mean + max + first-token 池化，
    合併後輸出 logits + value
    """
    def __init__(self, d_model, vocab_size, dropout=0.1):
        super().__init__()
        self.head_mean = nn.Linear(d_model, vocab_size)
        self.head_max = nn.Linear(d_model, vocab_size)
        self.head_first = nn.Linear(d_model, vocab_size)
        self.gate = nn.Linear(d_model * 3, 3, bias=False)
        self.head_critic = nn.Linear(d_model, 1)
        self.dropout = nn.Dropout(dropout)

    def forward(self, h):
        # h: (B, T, D)
        pool_mean = h.mean(dim=1)     # (B, D)
        pool_max = h.max(dim=1).values  # (B, D)
        pool_first = h[:, 0, :]       # (B, D)

        logits_mean = self.head_mean(pool_mean)
        logits_max = self.head_max(pool_max)
        logits_first = self.head_first(pool_first)

        # 可學習門控融合
        combined = torch.cat([pool_mean, pool_max, pool_first], dim=-1)
        weights = F.softmax(self.gate(combined), dim=-1)  # (B, 3)

        logits = (weights[:, 0:1] * logits_mean +
                  weights[:, 1:2] * logits_max +
                  weights[:, 2:3] * logits_first)
        value = self.head_critic(pool_mean).squeeze(-1)
        return logits, value



class LoopedTransformerBlock(nn.Module):
    """單層 Looped Transformer Block
    = RMSNorm + QKNormAttention + RMSNorm + SwiGLU + Residual
    """
    def __init__(self, d_model, nhead, dim_feedforward, dropout=0.1):
        super().__init__()
        self.norm1 = RMSNorm(d_model)
        self.attn = QKNormAttention(d_model, nhead, dropout)
        self.norm2 = RMSNorm(d_model)
        self.ffn = SwiGLU(d_model, dim_feedforward, dropout)

    def forward(self, x, mask=None):
        # Pre-norm residual (AlphaGPT 風格)
        x = x + self.attn(self.norm1(x), mask)
        x = x + self.ffn(self.norm2(x))
        return x



class LoopedTransformer(nn.Module):
    """AlphaGPT Looped Transformer — 循環處理，小模型深層表達

    核心設計:
    1. Token Embedding + Positional Embedding
    2. LoopedTransformerBlock × num_layers, 循環 num_loops 次
    3. MTPHead 多任務池化輸出
    4. head_critic 價值估計 (GRPO 不需要，保留相容)
    """
    def __init__(self, cfg):
        super().__init__()
        self.tok_emb = nn.Embedding(cfg.vocab_size, cfg.d_model)
        self.pos_emb = nn.Embedding(cfg.max_formula_len, cfg.d_model)
        self.blocks = nn.ModuleList([
            LoopedTransformerBlock(cfg.d_model, cfg.nhead,
                                   cfg.dim_feedforward)
            for _ in range(cfg.num_layers)
        ])
        self.final_norm = RMSNorm(cfg.d_model)
        self.mtp_head = MTPHead(cfg.d_model, cfg.vocab_size)
        self.num_loops = cfg.num_loops

    def forward(self, x, mask=None):
        B, T = x.shape
        pos = torch.arange(T, device=x.device).unsqueeze(0)
        h = self.tok_emb(x) + self.pos_emb(pos)

        # Looped: 循環通過 blocks
        for _ in range(self.num_loops):
            for block in self.blocks:
                h = block(h, mask)

        h = self.final_norm(h)

        # MTPHead: 逐位置 logits + 價值估計
        logits, value = self.mtp_head(h)
        # MTPHead 返回 (B, vocab) + (B,)
        # 為自回歸生成兼容，擴展為 (B, T, vocab) — 每個位置用同一組 logits
        # 但更精確的做法是使用 per-position 投影
        logits_per_pos = self.mtp_head.head_mean(h)  # (B, T, vocab)
        return logits_per_pos, value


def build_looped_transformer(config: GRPOConfig):
    # --- AlphaGPT 核心元件 (v3.4: NaN stability fix) ---

    model = LoopedTransformer(config).to(config.device)
    return model


# ============================================================
# 11. GRPOAlphaTrainer (GPU 版本)
# ============================================================

class GRPOAlphaTrainer:
    def __init__(self, config: GRPOConfig = None, gh_pusher: 'GitHubLogPusher' = None):
        self.config = config or GRPOConfig.auto_detect()
        self.vm = StackVM()
        self.reward_calc = GRPORewardCalculator(self.config)
        self.model = None
        self.optimizer = None
        self.best_formula = None
        self.best_reward = -float("inf")
        self.history = []
        self.gh_pusher = gh_pusher  # v3.3: GitHub real-time log pusher

    def init_torch(self):
        import torch
        self.model = build_looped_transformer(self.config)
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.config.lr,
                weight_decay=1e-5)  # v3.4: L2 reg
        print(f" [Torch] Model params: {sum(p.numel() for p in self.model.parameters()):,}")
        self.scaler = torch.amp.GradScaler('cuda', enabled=(self.config.device == 'cuda'))
        print(f"  [Torch] GradScaler enabled={self.config.device == 'cuda'}")
        return True

    def train_torch_regime(self, feat_tensor: np.ndarray, returns: np.ndarray,
                           regime_plan: dict = None,
                           val_feat: np.ndarray = None, val_returns: np.ndarray = None) -> dict:
        """PyTorch GRPO 訓練 (regime-aware)

        AlphaGPT 核心設計:
        1. 自回歸生成公式 token 序列 (autoregressive decoding)
        2. StackVM 執行每條公式 → 信號
        3. GRPO Group Relative Advantage: A_i = (R_i - mean(R_group)) / std(R_group)
        4. Clipped Importance Sampling: ratio = π_new / π_old, clip(ratio, 1-ε, 1+ε)
        5. 過擬合懲罰嵌入 reward
        6. LoRD 正則化 (Newton-Schulz)
        7. StableRank 監控
        """
        import torch
        import torch.nn.functional as F

        if self.model is None:
            self.init_torch()

        # 提取 regime 參數
        feature_mask = regime_plan.get("feature_mask") if regime_plan else None
        operator_mask = regime_plan.get("operator_mask") if regime_plan else None
        feature_weights = regime_plan.get("feature_weights") if regime_plan else None
        regime_name = "unknown"
        if regime_plan and "regime" in regime_plan:
            r = regime_plan["regime"]
            regime_name = r.value if hasattr(r, "value") else str(r)

        # 調整 group_size
        if regime_plan and "group_size" in regime_plan:
            self.config.group_size = regime_plan["group_size"]

        # GRPO clip epsilon
        clip_eps = getattr(self.config, "clip_eps", 0.2)

        print(f"\n[GRPO Torch] regime={regime_name}, "
              f"steps={self.config.train_steps}, G={self.config.group_size}, "
              f"clip_eps={clip_eps}, device={self.config.device}")

        feat_t = torch.tensor(feat_tensor, dtype=torch.float32, device=self.config.device)
        ret_t = torch.tensor(returns, dtype=torch.float32, device=self.config.device)

        best_formula = None
        best_reward = -float("inf")
        history = []
        start_time = time.time()
        rank_monitor = StableRankMonitor()

        self._old_log_probs = None  # v5.6: Init for off-policy ratio
        for step in range(self.config.train_steps):
            self.model.train()
            all_log_probs = [] # 新策略 log_probs
            all_tokens = []

            # --- v3.1: 引導式解碼 + Warmup ---
            is_warmup = step < self.config.warmup_steps

            for g in range(self.config.group_size):
                # Warmup: 前半用恆等公式（單特徵），確保有正 reward
                if is_warmup and g < self.config.group_size // 2:
                    if feature_weights is not None:
                        sorted_feats = np.argsort(-np.array(feature_weights))
                        feat_idx = int(sorted_feats[g % N_FEATURES])
                    else:
                        feat_idx = g % N_FEATURES
                    token_list = [feat_idx]
                    # v3.3 FIX: warmup still needs model forward for grad_fn
                    warmup_inp = torch.tensor([[feat_idx]], dtype=torch.long,
                                              device=self.config.device)
                    warmup_logits, _ = self.model(warmup_inp)
                    warmup_dist = torch.distributions.Categorical(
                        logits=_safe_logits(warmup_logits[:, -1, :].squeeze(0)))
                    warmup_action = torch.tensor(feat_idx, device=self.config.device)
                    log_prob = warmup_dist.log_prob(warmup_action)
                    all_tokens.append(token_list)
                    all_log_probs.append(log_prob)
                    continue

                # --- 引導式生成 (guided decoding) ---
                vm_state = StackVMState(max_stack_depth=self.config.max_stack_depth)
                inp = torch.zeros(1, 1, dtype=torch.long, device=self.config.device)
                token_list = []
                log_probs = []

                for t_pos in range(self.config.max_formula_len):
                    remaining = self.config.max_formula_len - t_pos

                    # 棧完成且至少1個token → 提前結束
                    if vm_state.is_complete() and len(token_list) >= 1:
                        break

                    # 推導合法 token
                    if self.config.guided_decoding:
                        valid_tokens = vm_state.get_valid_tokens(t_pos, remaining)
                        if not valid_tokens:
                            break  # 無合法 token，提前結束
                    else:
                        valid_tokens = None

                    logits, _ = self.model(inp)
                    logits_last = logits[:, -1, :].squeeze(0).clone()

                    # 引導式 mask: 非法 token 設 -1e9
                    if valid_tokens is not None:
                        guided_mask = torch.full((VOCAB_SIZE,), -1e9,
                                                 device=self.config.device)
                        for t in valid_tokens:
                            guided_mask[t] = 0.0
                        logits_last = logits_last + guided_mask

                    # Apply regime mask
                    if feature_mask is not None and operator_mask is not None:
                        mask = np.ones(VOCAB_SIZE, dtype=np.float32) * -1e9
                        for i in range(N_FEATURES):
                            if feature_mask[i]:
                                mask[i] = 0.0
                        for i in range(N_OPERATORS):
                            if operator_mask[i]:
                                mask[N_FEATURES + i] = 0.0
                        mask_t = torch.tensor(mask, device=self.config.device)
                        logits_last = logits_last + mask_t

                    # 特徵加權
                    if feature_weights is not None:
                        fw = torch.tensor(feature_weights, device=self.config.device)
                        fw_logits = torch.zeros(VOCAB_SIZE, device=self.config.device)
                        fw_logits[:N_FEATURES] = torch.log(fw + 0.01)
                        logits_last = logits_last + fw_logits * 0.5

                    # Warmup: 第一個 token 必須是特徵
                    if is_warmup and vm_state.stack_depth == 0:
                        for i in range(N_FEATURES, VOCAB_SIZE):
                            logits_last[i] = -1e9

                    dist = torch.distributions.Categorical(logits=_safe_logits(logits_last))
                    action = dist.sample()
                    log_probs.append(dist.log_prob(action))
                    token_list.append(action.item())

                    vm_state.apply_token(action.item())
                    inp = torch.cat([inp, action.view(1, 1)], dim=1)

                # 公式不完整 → fallback 恆等公式
                if not vm_state.is_complete() or len(token_list) < 1:
                    if feature_weights is not None:
                        feat_idx = int(np.argmax(feature_weights))
                    else:
                        feat_idx = 0
                    token_list = [feat_idx]
                    # v3.3 FIX: fallback also needs model forward for log_prob
                    fb_inp = torch.tensor([[feat_idx]], dtype=torch.long,
                                          device=self.config.device)
                    fb_logits, _ = self.model(fb_inp)
                    fb_dist = torch.distributions.Categorical(
                        logits=_safe_logits(fb_logits[:, -1, :].squeeze(0)))
                    fb_action = torch.tensor(feat_idx, device=self.config.device)
                    log_probs = [fb_dist.log_prob(fb_action)]

                all_tokens.append(token_list)
                all_log_probs.append(torch.stack(log_probs).sum())

            # --- GRPO Group Relative Reward ---
            train_ic = self._compute_ic(all_tokens, feat_tensor, returns)
            val_ic = self._compute_ic(all_tokens, val_feat, val_returns) if val_feat is not None else 0.0

            result = self.reward_calc.compute_group_rewards(
                all_tokens, feat_tensor, returns,
                train_ic=train_ic, val_ic=val_ic,
            )

            advantages = torch.tensor(
                result["advantages"], dtype=torch.float32, device=self.config.device
            )
            # v3.4: Replace NaN advantages with 0 (neutral)
            advantages = torch.where(torch.isnan(advantages), torch.zeros_like(advantages), advantages)
            advantages = torch.clamp(advantages, -5.0, 5.0)

            # --- GRPO Clipped Importance Sampling Loss ---
            # ratio = exp(log π_new - log π_old)
            # FIX: warmup/fallback paths append a raw Categorical.log_prob scalar (shape []),
            # while guided-decoding path appends torch.stack(log_probs).sum() (shape [1]).
            # .squeeze() on shape [1] → shape [], but on shape [] it stays [].
            # After squeeze, entries are still inconsistent: some [] vs some with leftover dim.
            # Force all entries to flat 0-d scalars via reshape(()).
            all_log_probs = [lp.reshape(()) for lp in all_log_probs]
            log_probs_tensor = torch.stack(all_log_probs)

            # v5.6 FIX: Correct GRPO off-policy importance sampling
            # ratio = pi_new / pi_old = exp(log_pi_new - log_pi_old)
            # Old bug: ratio = exp(log_pi - log_pi.detach()) = 1.0 -> loss = 0
            # CRITICAL: ratio MUST have grad_fn (through log_probs_tensor)
            # so that loss.backward() works. Never use detached tensors for ratio.
            if hasattr(self, '_old_log_probs') and self._old_log_probs is not None                     and len(self._old_log_probs) == len(log_probs_tensor):
                old_lp = torch.tensor(self._old_log_probs, dtype=torch.float32,
                                       device=self.config.device)
                ratio = torch.exp(log_probs_tensor - old_lp)
            else:
                # First step or shape mismatch: use zeros as old_log_probs
                # This gives ratio = exp(log_pi - 0) = exp(log_pi), which
                # is NOT 1.0 but still has grad_fn through log_probs_tensor
                ratio = torch.exp(log_probs_tensor)

# Clipped surrogate: L = -min(ratio * A, clip(ratio, 1-ε, 1+ε) * A)
            clipped_ratio = torch.clamp(ratio, 1.0 - clip_eps, 1.0 + clip_eps)
            surr1 = ratio * advantages
            surr2 = clipped_ratio * advantages
            loss = -torch.min(surr1, surr2).mean()

            # Entropy bonus
            try:
                with torch.no_grad():
                    dummy_inp = torch.zeros(1, 1, dtype=torch.long, device=self.config.device)
                    logits_out, _ = self.model(dummy_inp)
                    entropy = torch.distributions.Categorical(logits=_safe_logits(logits_out[:, -1, :])).entropy()
                    loss -= self.config.entropy_coef * entropy
            except Exception:
                pass

            self.optimizer.zero_grad()
            # v3.4: Skip step if loss is NaN/Inf
            if torch.isnan(loss) or torch.isinf(loss):
                print(f"  [NaN GUARD] step {step}: loss is NaN/Inf, skipping")
                continue
            # v3.4: Use GradScaler for stable training
            self.scaler.scale(loss).backward()
            self.scaler.unscale_(self.optimizer)
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            self.scaler.step(self.optimizer)
            self.scaler.update()

            # v3.4: NaN guard — if any param is NaN, reinitialize model
            has_nan = any(p.isnan().any() for p in self.model.parameters())
            if has_nan:
                print(f"  [NaN GUARD] step {step}: NaN in params, reinitializing")
                self.model = build_looped_transformer(self.config).to(self.config.device)
                self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.config.lr,
                    weight_decay=1e-5)
                self.scaler = torch.amp.GradScaler('cuda', enabled=(self.config.device == 'cuda'))
                self._old_log_probs = None
                continue

            # 存儲 old_log_probs 供下一步 off-policy importance sampling
            self._old_log_probs = [lp.item() for lp in log_probs_tensor.detach().cpu()]

            # LoRD (Newton-Schulz)
            if self.config.use_lord and step % 10 == 0:
                self._apply_lord_decay()

            # StableRank 監控
            if step % 500 == 0:
                rank_info = rank_monitor.compute(self.model)

            # Track best
            best_idx = result["best_idx"]
            if result["rewards"][best_idx] > best_reward:
                best_reward = result["rewards"][best_idx]
                best_formula = all_tokens[best_idx]

            if step % 500 == 0:
                elapsed = time.time() - start_time
                rank_str = f" avg_rank={rank_info.get('avg_rank', 0):.1f}" if step % 500 == 0 and 'rank_info' in dir() else ""
                print(f"  step {step:5d}: loss={loss.item():.4f} "
                      f"mean_r={result['group_mean_reward']:.3f} "
                      f"best_r={result['rewards'][best_idx]:.3f} "
                      f"valid={result['valid_mask'].mean():.1%} "
                      f"overfit={result['overfit_info']['is_overfit']} "
                      f"clip_ratio={((ratio > 1+clip_eps) | (ratio < 1-clip_eps)).float().mean():.1%}"
                      f"{rank_str} elapsed={elapsed:.0f}s")
                # v3.3: Push training metrics to GitHub for real-time monitoring
                if self.gh_pusher is not None:
                    try:
                        self.gh_pusher.push_log(regime_name, step, {
                            "loss": loss.item(),
                            "mean_reward": result['group_mean_reward'],
                            "best_reward": result['rewards'][best_idx],
                            "valid_ratio": float(result['valid_mask'].mean()),
                            "clip_ratio": float(((ratio > 1+clip_eps) | (ratio < 1-clip_eps)).float().mean()),
                            "elapsed_seconds": elapsed,
                        })
                    except Exception as e:
                        print(f"  [GitHubLog] push failed: {e}")

            history.append({
                "step": step,
                "regime": regime_name,
                "loss": loss.item(),
                "group_mean": result["group_mean_reward"],
                "best_reward": result["rewards"][best_idx],
                "overfit": result["overfit_info"]["is_overfit"],
            })

        elapsed = time.time() - start_time
        print(f"\n[GRPO Torch] regime={regime_name} 完成: "
              f"best_reward={best_reward:.4f}, steps={self.config.train_steps}, "
              f"elapsed={elapsed:.0f}s")

        return {
            "best_formula": best_formula,
            "best_reward": best_reward,
            "regime": regime_name,
            "n_steps": self.config.train_steps,
            "history": history,
            "elapsed_seconds": elapsed,
        }

    def train_all_regimes(self, stock_data_map: Dict[str, dict]) -> Dict[str, dict]:
        """對所有 regime 分群訓練"""
        results = {}
        regime_groups = defaultdict(list)

        for stock_id, data in stock_data_map.items():
            regime_plan = data.get("regime_plan", {})
            regime = regime_plan.get("regime", StockRegime.MID_CAP_TECH)
            regime_key = regime.value if hasattr(regime, "value") else str(regime)
            regime_groups[regime_key].append(stock_id)

        print(f"\n[Multi-Regime] 分群結果:")
        for rk, stocks in regime_groups.items():
            print(f"  {rk}: {stocks}")

        for regime_key, stocks in regime_groups.items():
            print(f"\n{'='*60}")
            print(f" 訓練 regime={regime_key} ({len(stocks)} 檔)")
            print(f"{'='*60}")

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

            combined_feat = np.concatenate(all_feat, axis=1)
            combined_returns = np.concatenate(all_returns, axis=0)

            # Train/Val split (80/20 time-series)
            n_total = combined_returns.shape[0]
            n_train = int(n_total * 0.8)
            train_feat = combined_feat[:, :n_train]
            train_returns = combined_returns[:n_train]
            val_feat = combined_feat[:, n_train:]
            val_returns = combined_returns[n_train:]

            print(f"  train: {n_train} samples, val: {n_total - n_train} samples")

            # 重置模型
            self.model = None
            self.optimizer = None
            self.init_torch()

            # 訓練
            result = self.train_torch_regime(
                train_feat, train_returns,
                regime_plan=regime_plan,
                val_feat=val_feat, val_returns=val_returns,
            )

            # 驗證集最終 IC
            val_ic = self._compute_ic([result["best_formula"]], val_feat, val_returns)
            train_ic = self._compute_ic([result["best_formula"]], train_feat, train_returns)
            result["final_train_ic"] = train_ic
            result["final_val_ic"] = val_ic
            result["ic_gap"] = train_ic - val_ic

            print(f"  Train IC: {train_ic:.4f}, Val IC: {val_ic:.4f}, Gap: {train_ic-val_ic:.4f}")

            # 分配結果給該 regime 所有股票
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
                "history": result.get("history", []),  # v5.6 P2 FIX
                }

        return results

    def _compute_ic(self, group_tokens, feat_tensor=None, returns=None):
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
            ic = GRPORewardCalculator._spearman_corr(signal[valid], returns[valid])
            if not np.isnan(ic) and abs(ic) > abs(best_ic):
                best_ic = ic
        return best_ic

    def _apply_lord_decay(self):
        """Newton-Schulz Low-Rank Decay (LoRD)
        
        AlphaGPT 核心設計: 不使用 SVD 分解（O(n^3)），而是用 Newton-Schulz 
        迭代近似低秩分量，複雜度 O(n^2 * k_iter)，更適合 GPU。
        
        Newton-Schulz 迭代: X_k+1 = 0.5 * X_k * (3I - X_k^T X_k)
        收斂至最近的正交矩陣，低秩分量 = W - Q (W的投影殘差)
        """
        try:
            import torch
            with torch.no_grad():
                for name, param in self.model.named_parameters():
                    if "weight" in name and param.dim() >= 2:
                        W = param.data.float()
                        # Newton-Schulz: 近似 W 的正交投影
                        # 歸一化 W 以確保收斂
                        norm = W.norm()
                        if norm < 1e-8:
                            continue
                        X = W / norm
                        # 3 步 Newton-Schulz 迭代 (通常足夠收斂)
                        for _ in range(3):
                            X = 0.5 * X @ (3.0 * torch.eye(X.shape[1], device=X.device) - X.T @ X)
                        # 低秩分量 = 原始矩陣 - 正交投影 * 縮放
                        low_rank = W - X * norm
                        # 以小學習率衰減低秩分量
                        param.data -= self.config.lord_decay * low_rank.to(param.dtype)
        except Exception:
            pass


class StableRankMonitor:
    """AlphaGPT 核心設計: 監控參數矩陣的穩定秩 (stable rank)
    
    stable_rank(W) = ||W||_F^2 / ||W||_2^2
    衡量矩陣的有效秩，若穩定秩過低表示參數退化，需調整 LoRD 強度。
    """
    def __init__(self):
        self.history = []
    
    def compute(self, model) -> dict:
        """計算模型所有權重矩陣的穩定秩統計"""
        try:
            import torch
            ranks = []
            with torch.no_grad():
                for name, param in model.named_parameters():
                    if "weight" in name and param.dim() >= 2:
                        W = param.data.float()
                        frobenius_sq = (W ** 2).sum()
                        # 用冪迭代近似 spectral norm (避免 SVD)
                        spectral_norm = self._approx_spectral_norm(W, n_iter=10)
                        if spectral_norm > 1e-8:
                            srank = (frobenius_sq / (spectral_norm ** 2)).item()
                            ranks.append(srank)
            
            if ranks:
                info = {
                    "avg_rank": sum(ranks) / len(ranks),
                    "min_rank": min(ranks),
                    "max_rank": max(ranks),
                    "n_matrices": len(ranks),
                }
                self.history.append(info)
                return info
        except Exception:
            pass
        return {}
    
    @staticmethod
    def _approx_spectral_norm(W, n_iter=10):
        """冪迭代近似 spectral norm (最大奇異值) — O(n^2 * iter)"""
        import torch
        # 隨機起始向量
        v = torch.randn(W.shape[1], device=W.device)
        for _ in range(n_iter):
            u = W @ v
            u_norm = u.norm()
            if u_norm < 1e-8:
                break
            u = u / u_norm
            v = W.T @ u
            v_norm = v.norm()
            if v_norm < 1e-8:
                break
            v = v / v_norm
        return (W @ v).norm()


def robust_normalize(arr, window=20):
    """AlphaGPT 核心設計: Rolling window 正規化 (robust norm)
    
    使用滾動窗口的 median + MAD (Median Absolute Deviation) 正規化，
    比 z-score 更抗極端值。適用於金融序列的非平穩特性。
    
    輸出: median=0, MAD≈1 的穩定序列
    """
    if arr is None or len(arr) < window:
        return arr
    
    result = np.copy(arr).astype(np.float64)
    for i in range(window, len(arr)):
        segment = arr[i-window:i]
        med = np.median(segment)
        mad = np.median(np.abs(segment - med))
        if mad > 1e-8:
            result[i] = (arr[i] - med) / (1.4826 * mad)  # 1.4826 使 MAD ≈ std for normal
        else:
            result[i] = 0.0
    
    # 前window期用全局統計
    global_med = np.median(arr[:window])
    global_mad = np.median(np.abs(arr[:window] - global_med))
    if global_mad > 1e-8:
        result[:window] = (arr[:window] - global_med) / (1.4826 * global_mad)
    else:
        result[:window] = 0.0
    
    return result


# ============================================================
# 12. 公式反編譯器
# ============================================================

def decode_formula(tokens: List[int]) -> str:
    """將 token 序列反編譯為人類可讀公式"""
    if tokens is None:
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
            op_name = OPERATOR_NAMES[op_idx]
            if arity == 1:
                a = stack.pop()
                stack.append(f"{op_name}({a})")
            elif arity == 2:
                b = stack.pop()
                a = stack.pop()
                stack.append(f"({a} {op_name} {b})")
            elif arity == 3:
                c = stack.pop()
                b = stack.pop()
                a = stack.pop()
                stack.append(f"GATE({a},{b}|{c})")

    return stack[0] if len(stack) == 1 else "INVALID"


# ============================================================
# 13. Walk-Forward 簡易驗證
# ============================================================

def walk_forward_validation(feat_tensor, returns, best_formula, n_splits=5):
    """簡易 Walk-Forward 驗證"""
    vm = StackVM()
    n = returns.shape[0]
    fold_size = n // (n_splits + 1)
    ics = []

    for i in range(n_splits):
        train_end = fold_size * (i + 1)
        test_start = train_end
        test_end = min(train_end + fold_size, n)

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
        "ic_tstat": np.mean(ics) / (np.std(ics) + 1e-6) if len(ics) > 1 else 0.0,
        "positive_ratio": sum(1 for ic in ics if ic > 0) / len(ics) if ics else 0.0,
    }


# ============================================================
# 14. 主訓練流程
# ============================================================



def adapt_finmind_data(data_path):
    """v5.0: 將 FinMind 原始數據轉換為 TWFeatureEngineer 期望的格式
    
    FinMind API 格式:
    - inst_data.csv: date, stock_id, buy, sell, name (5 investor types)
    - margin_data.csv: date, stock_id, MarginPurchaseTodayBalance, etc.
    - futures_oi.csv: date, futures_id, contract_date, oi, futures_close, ...
    - us_indices.csv: date, NASDAQ, SP500, DOWJONES, *_MOM5
    
    TWFeatureEngineer 期望格式:
    - inst_df: date, stock_id, foreign_net, trust_net, total_net
    - margin_df: date, stock_id, margin_balance, margin_buy
    - futures_oi_df: date, futures_id, inst_net_oi, retail_net_oi
    - us_indices_df: date, index_name, close
    """
    # 1. twstock_daily.csv → directly compatible
    df = pd.read_csv(os.path.join(data_path, "twstock_daily.csv"))
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])

    # 2. inst_data.csv → pivot by investor type
    inst_df = None
    inst_path = os.path.join(data_path, "inst_data.csv")
    if os.path.exists(inst_path):
        raw = pd.read_csv(inst_path)
        if "date" in raw.columns:
            raw["date"] = pd.to_datetime(raw["date"])
        # Compute net = buy - sell
        if "buy" in raw.columns and "sell" in raw.columns:
            raw["net"] = raw["buy"] - raw["sell"]
        elif "net" not in raw.columns:
            raw["net"] = 0
        # Pivot: one row per (date, stock_id)
        if "name" in raw.columns:
            pivot = raw.pivot_table(
                index=["date", "stock_id"], columns="name",
                values="net", aggfunc="sum"
            ).reset_index()
            name_map = {
                "Foreign_Investor": "foreign_net",
                "Foreign_Dealer_Self": "foreign_dealer_net",
                "Investment_Trust": "trust_net",
                "Dealer_self": "dealer_self_net",
                "Dealer_Hedging": "dealer_hedging_net",
            }
            pivot.columns = [name_map.get(c, c) for c in pivot.columns]
        else:
            pivot = raw  # Already in expected format
        # Compute total_net
        inst_cols = [c for c in ["foreign_net", "trust_net", "dealer_self_net"]
                     if c in pivot.columns]
        if inst_cols:
            pivot["total_net"] = pivot[inst_cols].sum(axis=1)
        else:
            pivot["total_net"] = 0
        if "foreign_net" not in pivot.columns and "total_net" in pivot.columns:
            pivot["foreign_net"] = pivot["total_net"]
        inst_df = pivot

    # 3. margin_data.csv → map FinMind columns
    margin_df = None
    margin_path = os.path.join(data_path, "margin_data.csv")
    if os.path.exists(margin_path):
        raw = pd.read_csv(margin_path)
        if "date" in raw.columns:
            raw["date"] = pd.to_datetime(raw["date"])
        # Map FinMind column names
        if "MarginPurchaseTodayBalance" in raw.columns:
            raw["margin_balance"] = raw["MarginPurchaseTodayBalance"]
        if "MarginPurchaseBuy" in raw.columns:
            raw["margin_buy"] = raw["MarginPurchaseBuy"]
        if "ShortSaleTodayBalance" in raw.columns:
            raw["short_balance"] = raw["ShortSaleTodayBalance"]
        margin_df = raw

    # 4. futures_oi.csv → v6.0: 真實法人OI (FinMind TaiwanFuturesInstitutionalInvestors)
    # 格式 A: 真實法人OI (date, futures_id, inst_net_oi, retail_net_oi)
    # 格式 B: 舊格式 (date, futures_id, oi, mtx_oi, ...) → 60/40 近似
    futures_oi_df = None
    foi_path = os.path.join(data_path, "futures_oi.csv")
    if os.path.exists(foi_path):
        raw = pd.read_csv(foi_path)
        if "date" in raw.columns:
            raw["date"] = pd.to_datetime(raw["date"])
        # 格式 A: 已有 inst_net_oi 欄位 → 直接使用 (v6.0 真實法人OI)
        if "inst_net_oi" in raw.columns and "futures_id" in raw.columns:
            futures_oi_df = raw[["date", "futures_id", "inst_net_oi"]].copy()
            if "retail_net_oi" in raw.columns:
                futures_oi_df["retail_net_oi"] = raw["retail_net_oi"]
            else:
                futures_oi_df["retail_net_oi"] = -raw["inst_net_oi"]
            futures_oi_df = futures_oi_df.sort_values(["date", "futures_id"]).reset_index(drop=True)
            print(f"   [v6.0] 使用真實法人OI: {len(futures_oi_df)} rows")
        # 格式 B: 舊格式 (只有 total oi) → 60/40 近似
        elif "oi" in raw.columns and len(raw) > 0:
            near_month = raw.loc[raw.groupby(["date"])["oi"].idxmax()]
            near_month = near_month[["date", "oi"]].copy()
            near_month = near_month.rename(columns={"oi": "total_oi"})
            near_month["inst_net_oi"] = near_month["total_oi"] * 0.6
            near_month["retail_net_oi"] = near_month["total_oi"] * 0.4
            near_month["futures_id"] = "TX"
            if "mtx_oi" in raw.columns:
                mtx_near = raw.loc[raw.groupby(["date"])["mtx_oi"].idxmax()]
                mtx_rows = mtx_near[["date", "mtx_oi"]].copy()
                mtx_rows = mtx_rows.rename(columns={"mtx_oi": "total_oi"})
                mtx_rows["inst_net_oi"] = mtx_rows["total_oi"] * 0.6
                mtx_rows["retail_net_oi"] = mtx_rows["total_oi"] * 0.4
                mtx_rows["futures_id"] = "MTX"
                futures_oi_df = pd.concat([near_month, mtx_rows], ignore_index=True)
            else:
                futures_oi_df = near_month
            futures_oi_df = futures_oi_df.sort_values(["date", "futures_id"]).reset_index(drop=True)
            print(f"   [v5.0 fallback] 使用60/40近似法人OI: {len(futures_oi_df)} rows")

    # 5. us_indices.csv → convert wide format to long format
    us_indices_df = None
    us_path = os.path.join(data_path, "us_indices.csv")
    if os.path.exists(us_path):
        raw = pd.read_csv(us_path)
        if "date" in raw.columns:
            raw["date"] = pd.to_datetime(raw["date"])
        # Check if already in long format (has index_name column)
        if "index_name" in raw.columns:
            us_indices_df = raw
        else:
            # Wide format: date, NASDAQ, SP500, DOWJONES
            # Convert to long format: date, index_name, close
            records = []
            for idx_name, col in [("Nasdaq", "NASDAQ"), ("SP500", "SP500"),
                                   ("DowJones", "DOWJONES")]:
                if col in raw.columns:
                    for _, row in raw.iterrows():
                        if pd.notna(row.get(col)):
                            records.append({
                                "date": row["date"],
                                "index_name": idx_name,
                                "close": row[col],
                                "mom5": row.get(f"{col}_MOM5", 0),
                            })
            if records:
                us_indices_df = pd.DataFrame(records)

    return df, inst_df, margin_df, futures_oi_df, us_indices_df

def main():
    check_environment()

    # --- 步驟 1: 載入/生成數據 ---
    print("\n--- 步驟 1: 數據準備 ---")
    # Auto-detect dataset path (Kaggle mounts at /kaggle/input/datasets/{owner}/{slug}/)
    data_path = None
    kaggle_input = "/kaggle/input"
    if os.path.isdir(kaggle_input):
        # Recursive search: Kaggle may nest datasets under /kaggle/input/datasets/owner/slug/
        for dirpath, dirnames, filenames in os.walk(kaggle_input):
            if "twstock_daily.csv" in filenames:
                data_path = dirpath
                print(f" [Debug] Found twstock_daily.csv at: {dirpath}")
                break
        if data_path is None:
            # Fallback: try known paths (old Kaggle format)
            for fallback_path in [
                os.path.join(kaggle_input, "twstock-grpo-training-data"),
                os.path.join(kaggle_input, "datasets", "mhhuang14", "twstock-grpo-training-data"),
            ]:
                if os.path.isdir(fallback_path) and os.path.exists(os.path.join(fallback_path, "twstock_daily.csv")):
                    data_path = fallback_path
                    break
        print(f" [Debug] /kaggle/input contents: {os.listdir(kaggle_input) if os.path.isdir(kaggle_input) else 'N/A'}")
        print(f" [Debug] data_path resolved: {data_path}")

    if data_path is not None and os.path.exists(data_path):
        print(f" 從 Kaggle Dataset 載入: {data_path} (v5.0 FinMind adapter)")
        df, inst_df, margin_df, futures_oi_df, us_indices_df = adapt_finmind_data(data_path)
        # Data quality report
        print(f"  OHLCV: {len(df)} rows, {df['stock_id'].nunique()} stocks")
        print(f"  Inst: {len(inst_df) if inst_df is not None else 0} rows")
        print(f"  Margin: {len(margin_df) if margin_df is not None else 0} rows")
        print(f"  Futures OI: {len(futures_oi_df) if futures_oi_df is not None else 0} rows")
        print(f"  US Indices: {len(us_indices_df) if us_indices_df is not None else 0} rows")
        if "date" in df.columns and len(df) > 0:
            dates = df["date"]
            dmin, dmax = dates.min(), dates.max()
            span_years = (dmax - dmin).days / 365.25
            print(f"  Date range: {dmin.strftime('%Y-%m-%d')} ~ {dmax.strftime('%Y-%m-%d')} ({span_years:.1f} yr)")
            if span_years < 3.0:
                print(f"  WARNING: 數據期間 {span_years:.1f} 年 < 3年門檻! 結果可能不穩定")
    else:
        print(" 無 Kaggle Dataset，使用合成數據")
        df, inst_df, margin_df, futures_oi_df, us_indices_df = generate_synthetic_data(n_days=500, seed=42)

    print(f" 載入完成: {len(df)} 筆, {df['stock_id'].nunique()} 檔")


    # --- 步驟 2: 特徵工程 ---
    print("\n--- 步驟 2: 特徵工程 ---")
    feat_df = TWFeatureEngineer.compute_features(df, inst_df, margin_df,
                                                   futures_oi_df, us_indices_df)
    print(f" 特徵計算完成: {len(feat_df)} 筆")
    # v5.6 P1 diagnostic: show stock_id distribution in feat_df
    if "stock_id" in feat_df.columns:
        stock_counts = feat_df["stock_id"].value_counts()
        print(f" [P1 DEBUG] feat_df stock_id distribution:")
        for sid, cnt in stock_counts.items():
            print(f"   {sid}: {cnt} rows")
        if feat_df["stock_id"].nunique() < 2:
            print(f" [P1 DEBUG] WARNING: Only {feat_df['stock_id'].nunique()} stock in feat_df!")
            # Try to diagnose: check original df stock_ids
            if "stock_id" in df.columns:
                orig_counts = df["stock_id"].value_counts()
                print(f" [P1 DEBUG] Original df stock_id distribution:")
                for sid, cnt in orig_counts.items():
                    print(f"   {sid}: {cnt} rows")

    # 檢查特徵
    for feat in FEATURE_NAMES:
        if feat in feat_df.columns:
            col = feat_df[feat].replace([np.inf, -np.inf], np.nan).dropna()
        elif feat.lower() in feat_df.columns:
            col = feat_df[feat.lower()].replace([np.inf, -np.inf], np.nan).dropna()
        else:
            print(f" WARNING: {feat} not found in columns")
            continue
        valid = col.replace([np.inf, -np.inf], np.nan).dropna()
        print(f" {feat}: mean={valid.mean():.4f}, std={valid.std():.4f}, "
              f"nan={col.isna().sum()}/{len(col)}")

    # --- 步驟 3: 準備訓練數據 ---
    print("\n--- 步驟 3: 準備訓練張量 ---")
    stock_data_map = {}
    planner = RegimeTrainingPlan()

    for stock_id, group in feat_df.groupby("stock_id"):
        stock_id = str(stock_id)  # v5.6 P1 FIX: Ensure string for KNOWN_REGIMES
        group = group.sort_values("date").dropna(subset=["close"])

        # 偵測 regime
        regime = KNOWN_REGIMES.get(stock_id, StockRegime.MID_CAP_TECH)
        regime_plan = planner.create_plan(stock_id, regime)

        # 提取特徵矩陣 (n_features, n_samples)
        feat_cols = []
        for feat in FEATURE_NAMES:
            # v3.2: 優先使用大寫欄位（zscore 正規化後），fallback 到小寫
            if feat in group.columns:
                feat_cols.append(group[feat].values)
            elif feat.lower() in group.columns:
                feat_cols.append(group[feat.lower()].values)
            else:
                feat_cols.append(np.zeros(len(group)))

        feat_tensor = np.array(feat_cols, dtype=np.float32)
        # v5.6 P1 FIX: Debug NaN rows
        nan_rows = int(np.isnan(feat_tensor).any(axis=0).sum())
        if nan_rows > 0:
            print(f"  WARNING: {stock_id} has {nan_rows}/{feat_tensor.shape[1]} rows with NaN features")
        # v5.6 P1 FIX: Debug NaN rows
        nan_rows = np.isnan(feat_tensor).any(axis=0).sum()
        if nan_rows > 0:
            print(f"  WARNING: {stock_id} has {nan_rows}/{feat_tensor.shape[1]} rows with NaN features")
        # 替換 inf/nan
        feat_tensor = np.nan_to_num(feat_tensor, nan=0.0, posinf=5.0, neginf=-5.0)

        # 前向報酬 (按 regime reward_horizon)
        horizon = regime_plan.get("reward_horizon", 5)
        close = group["close"].values
        fwd_returns = np.zeros(len(close), dtype=np.float32)
        for i in range(len(close) - horizon):
            fwd_returns[i] = (close[i + horizon] - close[i]) / (close[i] + 1e-6)
        fwd_returns[-horizon:] = 0

        stock_data_map[stock_id] = {
            "feat": feat_tensor,
            "returns": fwd_returns,
            "regime_plan": regime_plan,
        }

        print(f"  {stock_id}: regime={regime.value}, "
              f"samples={feat_tensor.shape[1]}, horizon={horizon}d")

    # --- 步驟 4: GRPO Regime-Aware 訓練 ---
    print("\n--- 步驟 4: GRPO 訓練 ---")
    config = GRPOConfig.auto_detect()

    # Kaggle 環境下提高訓練量
    if os.path.exists("/kaggle"):
        config.train_steps = 20000
        config.group_size = 8
        config.batch_size = 128

    # v3.3: Initialize GitHub log pusher for real-time monitoring
    gh_token = os.environ.get("GITHUB_TOKEN", "")
    gh_pusher = GitHubLogPusher(token=gh_token) if gh_token else None
    if gh_pusher and gh_pusher.enabled:
        print(f" [GitHubLog] Real-time monitoring ENABLED -> milo0914/AlphaGPT/kaggle-logs/")
    else:
        print(f" [GitHubLog] Disabled. Set GITHUB_TOKEN Kaggle secret to enable.")

    trainer = GRPOAlphaTrainer(config, gh_pusher=gh_pusher)
    results = trainer.train_all_regimes(stock_data_map)

    # --- 步驟 5: Walk-Forward 驗證 ---
    print("\n--- 步驟 5: Walk-Forward 驗證 ---")
    wf_results = {}
    for stock_id, data in stock_data_map.items():
        if stock_id not in results:
            continue
        best_formula = results[stock_id]["best_formula"]
        feat = data["feat"]
        ret = data["returns"]

        wf = walk_forward_validation(feat, ret, best_formula, n_splits=5)
        wf_results[stock_id] = wf

        print(f"  {stock_id} ({results[stock_id]['regime']}): "
              f"mean_IC={wf['mean_ic']:.4f}, std={wf['std_ic']:.4f}, "
              f"t-stat={wf['ic_tstat']:.2f}, "
              f"positive={wf['positive_ratio']:.1%}")

    # --- 步驟 6: 反編譯公式 ---
    print("\n--- 步驟 6: 公式反編譯 ---")
    for stock_id, res in results.items():
        decoded = res.get("decoded_formula", "N/A")
        print(f"  {stock_id} ({res['regime']}): {decoded}")
        print(f"    reward={res['best_reward']:.4f}, "
              f"train_IC={res.get('train_ic', 0):.4f}, "
              f"val_IC={res.get('val_ic', 0):.4f}, "
              f"IC_gap={res.get('ic_gap', 0):.4f}")

    # --- 步驟 7: 儲存結果 ---
    print("\n--- 步驟 7: 儲存結果 ---")
    output_dir = "/kaggle/working" if os.path.exists("/kaggle") else "/tmp"
    os.makedirs(output_dir, exist_ok=True)

    # best_strategy_per_regime.json
    regime_strategies = {}
    for stock_id, res in results.items():
        regime = res["regime"]
        if regime not in regime_strategies or res["best_reward"] > regime_strategies[regime].get("best_reward", -999):
            regime_strategies[regime] = {
                "regime": regime,
                "best_formula": res["best_formula"],
                "decoded_formula": res["decoded_formula"],
                "best_reward": res["best_reward"],
                "train_ic": res.get("train_ic", 0),
                "val_ic": res.get("val_ic", 0),
                "ic_gap": res.get("ic_gap", 0),
                "n_steps": res.get("n_steps", 0),
            }

    for regime, strat in regime_strategies.items():
        # Convert numpy types for JSON
        strat_copy = {}
        for k, v in strat.items():
            if isinstance(v, (np.integer, np.floating)):
                strat_copy[k] = float(v)
            elif isinstance(v, np.ndarray):
                strat_copy[k] = v.tolist()
            elif isinstance(v, list):
                strat_copy[k] = [int(x) if isinstance(x, (np.integer,)) else float(x) if isinstance(x, (np.floating,)) else x for x in v]
            else:
                strat_copy[k] = v
        regime_strategies[regime] = strat_copy

    strat_path = os.path.join(output_dir, "best_strategy_per_regime.json")
    with open(strat_path, "w") as f:
        json.dump(regime_strategies, f, indent=2, ensure_ascii=False)
    print(f" 儲存: {strat_path}")

    # training_history.json
    all_history = {}
    for stock_id, res in results.items():
        h = []
        # v5.6 P2 FIX: Use history from results dict
        h = res.get("history", [])
        if h:
            h = [{k: float(v) if isinstance(v, (np.integer, np.floating)) else v
                  for k, v in entry.items()} for entry in h]
        all_history[stock_id] = h

    hist_path = os.path.join(output_dir, "training_history.json")
    with open(hist_path, "w") as f:
        json.dump(all_history, f, indent=2)
    print(f" 儲存: {hist_path}")

    # walk_forward_results.json
    wf_path = os.path.join(output_dir, "walk_forward_results.json")
    wf_serializable = {}
    for sid, wf in wf_results.items():
        wf_serializable[sid] = {
            "fold_ics": [float(x) for x in wf["fold_ics"]],
            "mean_ic": float(wf["mean_ic"]),
            "std_ic": float(wf["std_ic"]),
            "ic_tstat": float(wf["ic_tstat"]),
            "positive_ratio": float(wf["positive_ratio"]),
        }
    with open(wf_path, "w") as f:
        json.dump(wf_serializable, f, indent=2)
    print(f" 儲存: {wf_path}")

    # 訓練摘要
    summary_path = os.path.join(output_dir, "training_summary.txt")
    with open(summary_path, "w") as f:
        f.write("=" * 60 + "\n")
        f.write("台股 GRPO Regime-Aware 因子訓練摘要\n")
        f.write("=" * 60 + "\n\n")

        for regime, strat in regime_strategies.items():
            f.write(f"Regime: {regime}\n")
            f.write(f"  Formula: {strat.get('decoded_formula', 'N/A')}\n")
            f.write(f"  Reward: {strat.get('best_reward', 0):.4f}\n")
            f.write(f"  Train IC: {strat.get('train_ic', 0):.4f}\n")
            f.write(f"  Val IC: {strat.get('val_ic', 0):.4f}\n")
            f.write(f"  IC Gap: {strat.get('ic_gap', 0):.4f}\n")
            f.write(f"  Overfit: {'YES' if strat.get('ic_gap', 0) > 0.1 else 'NO'}\n")
            f.write("\n")

        for sid, wf in wf_results.items():
            f.write(f"Walk-Forward {sid}:\n")
            f.write(f"  Mean IC: {wf['mean_ic']:.4f}\n")
            f.write(f"  IC t-stat: {wf['ic_tstat']:.2f}\n")
            f.write(f"  Positive folds: {wf['positive_ratio']:.1%}\n\n")

    print(f" 儲存: {summary_path}")

    # --- 完成 ---
    print("\n" + "=" * 60)
    print(" 訓練完成!")
    print("=" * 60)
    for regime, strat in regime_strategies.items():
        overfit_flag = " [OVERFIT!]" if strat.get("ic_gap", 0) > 0.1 else ""
        print(f"  {regime}: IC={strat.get('val_ic',0):.4f}{overfit_flag}")
        print(f"    → {strat.get('decoded_formula', 'N/A')}")


if __name__ == "__main__":
    main()
