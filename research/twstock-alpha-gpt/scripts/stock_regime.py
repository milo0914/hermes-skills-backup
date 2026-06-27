"""
台股 AI Dig Money — Stock Regime 偵測器 (股性分群)

將股票按「股性」分群，讓 GRPO 因子訓練針對不同 regime 使用不同的
特徵權重、算子偏好、持倉窗口。這是方案 A-3 分層遞進式的核心組件。

設計邏輯：
- 不同股性的標的，有效的因子公式本質上不同
- 高市值/法人主導股：inst_flow, pressure 有訊號；fomo, surf_entry 是噪聲
- 中小型/高波動股：margin_press, fomo, mom_rev 有訊號；inst_flow 無意義
- 金融股：dev, close_pos 有訊號；cvd_proxy, absorption 噪聲大
- 傳產周期股：vol_breakout, dev 有訊號；surf_entry 不適用

Pitfalls:
1. [REGIME OVERLAP] 現實中股票不會完美歸入單一 regime，建議用
   soft assignment (機率向量) 而非 hard label，但目前先用 hard label。
2. [MICRO-CAP] 市值 < 50 億的微型股不適用此分群，需另建
   MICRO_CAP regime 或排除。
3. [REGIME DRIFT] 股性會隨時間變化（如台積電從 MID_CAP → LARGE_CAP），
   建議每季重新偵測 regime。
4. [UNCALIBRATED] 所有偵測閾值均未經 walk-forward 驗證。
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from enum import Enum


# ============================================================
# 1. Stock Regime 定義
# ============================================================

class StockRegime(Enum):
    """股票股性分類"""
    LARGE_CAP = "large_cap"       # 高市值/法人主導 (e.g., 2330 台積電)
    MID_CAP_TECH = "mid_cap_tech"  # 中型科技/混合 (e.g., 2454 聯發科)
    TRADITIONAL = "traditional"    # 傳產/週期 (e.g., 1301 台塑)
    FINANCIAL = "financial"        # 金融/低波動 (e.g., 2882 國泰金)


# 已知股票的 regime 對照表
KNOWN_REGIMES: Dict[str, StockRegime] = {
    # 半導體/電子 — 高市值
    "2330": StockRegime.LARGE_CAP,   # 台積電
    "2308": StockRegime.LARGE_CAP,   # 鴻海 (in semicap category)
    "2412": StockRegime.LARGE_CAP,   # 中華電信
    # 半導體/電子 — 中型科技
    "2454": StockRegime.MID_CAP_TECH,  # 聯發科
    "2382": StockRegime.MID_CAP_TECH,  # 廣達
    "2317": StockRegime.MID_CAP_TECH,  # 鴻海
    "3034": StockRegime.MID_CAP_TECH,  # 聯詠
    "3711": StockRegime.MID_CAP_TECH,  # 日月光投控
    "2303": StockRegime.MID_CAP_TECH,  # 聯電
    # 傳產
    "1301": StockRegime.TRADITIONAL,  # 台塑
    "1303": StockRegime.TRADITIONAL,  # 南亞
    "1326": StockRegime.TRADITIONAL,  # 台化
    "1101": StockRegime.TRADITIONAL,  # 台泥
    "2002": StockRegime.TRADITIONAL,  # 中鋼
    # 金融
    "2882": StockRegime.FINANCIAL,  # 國泰金
    "2886": StockRegime.FINANCIAL,  # 中信金
    "2891": StockRegime.FINANCIAL,  # 永豐金
    "2884": StockRegime.FINANCIAL,  # 玉山金
    "2881": StockRegime.FINANCIAL,  # 富邦金
}


# ============================================================
# 2. 特徵/算子名稱 (與 ai_dig_money_core.py 對齊)
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


# ============================================================
# 3. Regime 偵測器
# ============================================================

class RegimeDetector:
    """
    股性偵測器 — 根據市場數據判斷股票的 regime

    偵測優先順序：
    1. 已知對照表 (KNOWN_REGIMES)
    2. 數據驅動偵測 (成交量/波動度/法人佔比)
    3. 預設 MID_CAP_TECH (最中性的 regime)
    """

    # [UNCALIBRATED] 所有閾值均未經 walk-forward 驗證
    DETECTION_THRESHOLDS = {
        "large_cap_daily_volume": 50_000,    # 日均量 > 5萬張
        "large_cap_inst_ratio": 0.15,        # 法人買賣超佔成交量 > 15%
        "financial_volatility_cap": 0.025,    # ATR/close < 2.5% = 低波動
        "traditional_volatility_floor": 0.02, # ATR/close > 2% = 非金融
    }

    @classmethod
    def detect(cls, stock_id: str, df: pd.DataFrame,
               inst_df: pd.DataFrame = None,
               margin_df: pd.DataFrame = None) -> StockRegime:
        """
        偵測單一股票的 regime

        Args:
            stock_id: 股票代碼
            df: 日K資料
            inst_df: 三大法人 (optional)
            margin_df: 融資融券 (optional)

        Returns:
            StockRegime
        """
        # 1. 已知對照表
        if stock_id in KNOWN_REGIMES:
            return KNOWN_REGIMES[stock_id]

        # 2. 數據驅動偵測
        stock_data = df[df["stock_id"] == stock_id].copy()
        if len(stock_data) < 20:
            return StockRegime.MID_CAP_TECH  # 數據不足，預設中性

        return cls._detect_from_data(stock_data, inst_df, margin_df)

    @classmethod
    def _detect_from_data(cls, stock_data: pd.DataFrame,
                          inst_df: pd.DataFrame = None,
                          margin_df: pd.DataFrame = None) -> StockRegime:
        """從數據特徵判斷 regime"""
        thresholds = cls.DETECTION_THRESHOLDS

        # 計算日均量
        avg_volume = stock_data["volume"].mean()

        # 計算波動度 (ATR/close)
        high = stock_data["high"].values
        low = stock_data["low"].values
        close = stock_data["close"].values
        prev_close = np.roll(close, 1)
        prev_close[0] = close[0]

        tr = np.maximum(
            high - low,
            np.maximum(
                np.abs(high - prev_close),
                np.abs(low - prev_close)
            )
        )
        avg_atr_ratio = np.mean(tr / (close + 1e-6))

        # 金融股判斷：低波動
        if avg_atr_ratio < thresholds["financial_volatility_cap"]:
            # 進一步用股號判斷 (28xx 通常是金融)
            stock_id = stock_data["stock_id"].iloc[0]
            if isinstance(stock_id, str) and stock_id.startswith("28"):
                return StockRegime.FINANCIAL
            # 非金融股號但低波動 → 可能是高市值股
            if avg_volume > thresholds["large_cap_daily_volume"]:
                return StockRegime.LARGE_CAP
            return StockRegime.TRADITIONAL

        # 高市值判斷：大量 + 法人佔比
        if avg_volume > thresholds["large_cap_daily_volume"]:
            # 檢查法人佔比 (如果有數據)
            inst_ratio = 0.0
            if inst_df is not None and len(inst_df) > 0:
                stock_id = stock_data["stock_id"].iloc[0]
                stock_inst = inst_df[inst_df["stock_id"] == stock_id]
                if len(stock_inst) > 0:
                    inst_buy = stock_inst.get("foreign_buy", pd.Series([0])).sum()
                    inst_total = stock_inst.get("trust_buy", pd.Series([0])).sum()
                    inst_volume = abs(inst_buy) + abs(inst_total)
                    inst_ratio = inst_volume / (avg_volume * 1000 + 1e-6)

            if inst_ratio > thresholds["large_cap_inst_ratio"]:
                return StockRegime.LARGE_CAP
            return StockRegime.MID_CAP_TECH

        # 中低量 + 中高波動 → 中型科技
        if avg_atr_ratio > thresholds["traditional_volatility_floor"]:
            return StockRegime.MID_CAP_TECH

        # 其餘 → 傳產
        return StockRegime.TRADITIONAL

    @classmethod
    def detect_batch(cls, df: pd.DataFrame,
                     inst_df: pd.DataFrame = None,
                     margin_df: pd.DataFrame = None) -> Dict[str, StockRegime]:
        """
        批次偵測所有股票的 regime

        Returns:
            {stock_id: StockRegime}
        """
        results = {}
        for stock_id in df["stock_id"].unique():
            results[stock_id] = cls.detect(stock_id, df, inst_df, margin_df)
        return results


# ============================================================
# 4. Regime 訓練配置
# ============================================================

@dataclass
class RegimeConfig:
    """
    各 Regime 的 GRPO 訓練配置

    [UNCALIBRATED] 所有權重和偏好均未經驗證
    """

    # 各 regime 的特徵權重 (1.0 = 正常, >1.0 = 強調, <1.0 = 抑制)
    feature_weights: Dict[StockRegime, Dict[str, float]] = field(default_factory=lambda: {
        StockRegime.LARGE_CAP: {
            "RET": 1.0, "LIQ_SCORE": 1.0, "PRESSURE": 1.5,
            "FOMO": 0.3, "DEV": 1.2, "LOG_VOL": 1.0,
            "INST_FLOW": 2.0, "MARGIN_PRESS": 0.5,
            "FIVE_DAY_HIGH": 1.0, "VOL_BREAKOUT": 1.0,
            "CVD_PROXY": 1.0, "ABSORPTION": 0.5,
            "SURF_ENTRY": 0.3, "ATR": 1.0,
            "CLOSE_POS": 1.0, "MOM_REV": 0.5,
        },
        StockRegime.MID_CAP_TECH: {
            "RET": 1.0, "LIQ_SCORE": 1.0, "PRESSURE": 1.0,
            "FOMO": 1.2, "DEV": 1.0, "LOG_VOL": 1.0,
            "INST_FLOW": 0.8, "MARGIN_PRESS": 1.0,
            "FIVE_DAY_HIGH": 1.5, "VOL_BREAKOUT": 1.5,
            "CVD_PROXY": 1.5, "ABSORPTION": 1.0,
            "SURF_ENTRY": 1.2, "ATR": 1.0,
            "CLOSE_POS": 1.0, "MOM_REV": 1.2,
        },
        StockRegime.TRADITIONAL: {
            "RET": 1.0, "LIQ_SCORE": 1.0, "PRESSURE": 0.8,
            "FOMO": 0.5, "DEV": 1.5, "LOG_VOL": 1.0,
            "INST_FLOW": 1.0, "MARGIN_PRESS": 0.8,
            "FIVE_DAY_HIGH": 1.2, "VOL_BREAKOUT": 1.5,
            "CVD_PROXY": 0.5, "ABSORPTION": 0.3,
            "SURF_ENTRY": 0.3, "ATR": 1.0,
            "CLOSE_POS": 1.0, "MOM_REV": 1.0,
        },
        StockRegime.FINANCIAL: {
            "RET": 1.0, "LIQ_SCORE": 1.5, "PRESSURE": 0.8,
            "FOMO": 0.3, "DEV": 1.5, "LOG_VOL": 1.0,
            "INST_FLOW": 1.0, "MARGIN_PRESS": 0.5,
            "FIVE_DAY_HIGH": 0.8, "VOL_BREAKOUT": 0.8,
            "CVD_PROXY": 0.5, "ABSORPTION": 0.3,
            "SURF_ENTRY": 0.3, "ATR": 1.2,
            "CLOSE_POS": 1.5, "MOM_REV": 0.5,
        },
    })

    # 各 regime 允許的算子 (True/False)
    operator_mask: Dict[StockRegime, Dict[str, bool]] = field(default_factory=lambda: {
        StockRegime.LARGE_CAP: {
            "ADD": True, "SUB": True, "MUL": True, "DIV": True,
            "NEG": True, "ABS": True, "SIGN": True, "GATE": True,
            "JUMP": True, "DECAY": True, "DELAY1": True, "MAX3": True,
        },
        StockRegime.MID_CAP_TECH: {
            "ADD": True, "SUB": True, "MUL": True, "DIV": True,
            "NEG": True, "ABS": True, "SIGN": True, "GATE": True,
            "JUMP": True, "DECAY": True, "DELAY1": True, "MAX3": True,
        },
        StockRegime.TRADITIONAL: {
            "ADD": True, "SUB": True, "MUL": True, "DIV": True,
            "NEG": True, "ABS": True, "SIGN": False, "GATE": True,
            "JUMP": False, "DECAY": True, "DELAY1": True, "MAX3": True,
        },
        StockRegime.FINANCIAL: {
            "ADD": True, "SUB": True, "MUL": True, "DIV": True,
            "NEG": True, "ABS": True, "SIGN": False, "GATE": True,
            "JUMP": False, "DECAY": True, "DELAY1": True, "MAX3": True,
        },
    })

    # 各 regime 的 GRPO 訓練參數
    training_params: Dict[StockRegime, Dict] = field(default_factory=lambda: {
        StockRegime.LARGE_CAP: {
            "group_size": 8,        # 大樣本 → 大 group
            "target_holding_days": 5,
            "reward_horizon": 5,     # reward 計算前 5 天報酬
            "focus": "法人籌碼 + 買賣壓力，抑制散戶指標 (fomo/surf)",
        },
        StockRegime.MID_CAP_TECH: {
            "group_size": 6,
            "target_holding_days": 4,
            "reward_horizon": 4,
            "focus": "技術突破 + 量價確認，五日高點/CVD/放量為核心",
        },
        StockRegime.TRADITIONAL: {
            "group_size": 4,
            "target_holding_days": 5,
            "reward_horizon": 5,
            "focus": "營收驅動 + 放量結構，抑制 CVD/吸收等高頻指標",
        },
        StockRegime.FINANCIAL: {
            "group_size": 4,
            "target_holding_days": 7,
            "reward_horizon": 7,
            "focus": "均值回歸 + 位置指標，長持倉窗口，抑制波動指標",
        },
    })


# ============================================================
# 5. Regime 訓練計畫
# ============================================================

class RegimeTrainingPlan:
    """
    依據 StockRegime 生成 GRPO 訓練計畫

    計畫包含：
    - feature_mask: 強調/抑制的特徵遮罩
    - operator_mask: 允許/禁止的算子遮罩
    - group_size: GRPO group 大小
    - target_holding_days: 目標持倉天數
    - focus_description: 人類可讀的策略描述
    """

    def __init__(self, config: RegimeConfig = None):
        self.config = config or RegimeConfig()

    def create_plan(self, stock_id: str, regime: StockRegime) -> dict:
        """
        生成訓練計畫

        Args:
            stock_id: 股票代碼
            regime: 偵測到的 regime

        Returns:
            {
                stock_id, regime,
                feature_weights: array[16],
                feature_mask: array[16] bool (weight > 0.8),
                operator_mask: array[12] bool,
                group_size: int,
                target_holding_days: int,
                reward_horizon: int,
                focus_description: str,
            }
        """
        # 特徵權重
        weights_dict = self.config.feature_weights[regime]
        feature_weights = np.array(
            [weights_dict.get(f, 1.0) for f in FEATURE_NAMES],
            dtype=np.float32
        )

        # 特徵遮罩: 權重 > 0.8 為 True (啟用)
        feature_mask = feature_weights > 0.8

        # 算子遮罩
        ops_dict = self.config.operator_mask[regime]
        operator_mask = np.array(
            [ops_dict.get(op, True) for op in OPERATOR_NAMES],
            dtype=bool
        )

        # 訓練參數
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

    def create_plans_batch(self, regime_map: Dict[str, StockRegime]) -> Dict[str, dict]:
        """
        批次生成訓練計畫

        Args:
            regime_map: {stock_id: StockRegime}

        Returns:
            {stock_id: plan_dict}
        """
        plans = {}
        for stock_id, regime in regime_map.items():
            plans[stock_id] = self.create_plan(stock_id, regime)
        return plans

    def summarize_regimes(self, plans: Dict[str, dict]) -> pd.DataFrame:
        """
        將訓練計畫摘要為 DataFrame

        Returns:
            DataFrame with columns: stock_id, regime, group_size,
            holding_days, focus, n_active_features
        """
        rows = []
        for stock_id, plan in plans.items():
            rows.append({
                "stock_id": stock_id,
                "regime": plan["regime"].value,
                "group_size": plan["group_size"],
                "holding_days": plan["target_holding_days"],
                "focus": plan["focus_description"],
                "n_active_features": int(plan["feature_mask"].sum()),
                "n_active_operators": int(plan["operator_mask"].sum()),
            })
        return pd.DataFrame(rows)


# ============================================================
# 6. 示範
# ============================================================

def demo():
    """Stock Regime 偵測示範"""
    print("=" * 60)
    print(" Stock Regime 偵測器 — 示範")
    print("=" * 60)

    # 生成 4 檔代表性標的的模擬資料
    np.random.seed(42)
    n_days = 120
    dates = pd.bdate_range(end="2024-12-31", periods=n_days)

    demo_configs = {
        "2330": {"price": 800, "vol": 60000, "atr_pct": 0.020, "regime": "LARGE_CAP"},
        "2454": {"price": 1200, "vol": 15000, "atr_pct": 0.030, "regime": "MID_CAP_TECH"},
        "1301": {"price": 100, "vol": 8000, "atr_pct": 0.022, "regime": "TRADITIONAL"},
        "2882": {"price": 60, "vol": 30000, "atr_pct": 0.018, "regime": "FINANCIAL"},
    }

    records = []
    for sid, cfg in demo_configs.items():
        price = cfg["price"]
        for d in dates:
            ret = np.random.normal(0, cfg["atr_pct"] * 0.5)
            price *= (1 + ret)
            h = price * (1 + abs(np.random.normal(0, cfg["atr_pct"] * 0.5)))
            l = price * (1 - abs(np.random.normal(0, cfg["atr_pct"] * 0.5)))
            records.append({
                "date": d, "stock_id": sid,
                "open": price * (1 + np.random.normal(0, 0.003)),
                "high": h, "low": l, "close": price,
                "volume": int(cfg["vol"] * (1 + np.random.normal(0, 0.3))),
            })

    df = pd.DataFrame(records)

    # 1. 偵測 regime
    print("\n--- Regime 偵測 ---")
    regime_map = RegimeDetector.detect_batch(df)
    for sid, regime in regime_map.items():
        expected = demo_configs[sid]["regime"]
        match = "V" if regime.value == expected.lower() else "X"
        print(f"  {sid}: {regime.value:15s} (expected: {expected}) [{match}]")

    # 2. 生成訓練計畫
    print("\n--- 訓練計畫 ---")
    planner = RegimeTrainingPlan()
    plans = planner.create_plans_batch(regime_map)
    summary = planner.summarize_regimes(plans)
    print(summary.to_string(index=False))

    # 3. 各 regime 的特徵權重
    print("\n--- 特徵權重細節 ---")
    for sid, plan in plans.items():
        regime = plan["regime"]
        weights = plan["feature_weights"]
        active = [FEATURE_NAMES[i] for i in range(16) if plan["feature_mask"][i]]
        suppressed = [FEATURE_NAMES[i] for i in range(16)
                      if not plan["feature_mask"][i]]
        print(f"\n  {sid} ({regime.value}):")
        print(f"    強調: {', '.join(active)}")
        print(f"    抑制: {', '.join(suppressed) if suppressed else '無'}")
        print(f"    Group Size: {plan['group_size']}")
        print(f"    目標持倉: {plan['target_holding_days']} 天")
        print(f"    策略: {plan['focus_description']}")

    print("\n[OK] Stock Regime 偵測器就緒")


if __name__ == "__main__":
    demo()
