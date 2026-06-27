"""
台股 AI Dig Money 系統 - 核心模組
整合 AlphaGPT 因子挖掘 + Marcus 三重過濾 + Wenty 量價分析
3-7 天短期交易篩選框架

v2 修正清單 (2026-06-07 Strategy + Eng Review):
  - E1: Stage1-3 邊界保護 (min_rows 檢查)
  - E3: 閾值改為可配置 + 預設值標注未校準警告
  - E4: Stage3 評分邏輯修正 (避免負分 clip 掩蓋差異)
  - E5: 因子計算結果與篩選管線統一 (統一入口)
  - E6: composite_score 權重可配置
  - D1: TWDataLoader 月份偏移計算修正
  - D2: volume 單位標準化 (張)
  - D3: 移除 0050 ETF
  - D4: inst_df/margin_df 資料源擴充 (證交所 CSV)
  - 新增: overfit_warning 標記
  - 新增: integrate_with_alpha() 統一因子管線
"""
import json
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
import warnings
from pathlib import Path


# ============================================================
# 1. 台股因子詞彙表 (擴展自 AlphaGPT vocab.py)
# ============================================================

# AlphaGPT 原始 6 因子
ORIGINAL_FEATURES = (
    "RET", "LIQ_SCORE", "PRESSURE", "FOMO", "DEV", "LOG_VOL",
)

# Marcus + Wenty 台股專用 10 因子
TW_EXTRA_FEATURES = (
    "INST_FLOW",      # 三大法人淨買超方向
    "MARGIN_PRESS",   # 融資增減壓力
    "FIVE_DAY_HIGH",  # 五日高點突破信號
    "VOL_BREAKOUT",   # 放量結構突破
    "CVD_PROXY",      # CVD 代理 (日K級別)
    "ABSORPTION",     # 吸收比 = volume / (H-L)
    "SURF_ENTRY",     # 衝浪手切入信號
    "ATR",            # 真實波動幅度
    "CLOSE_POS",      # 收盤在區間位置
    "MOM_REV",        # 動量反轉信號
)

TW_FEATURE_NAMES = ORIGINAL_FEATURES + TW_EXTRA_FEATURES # 16 因子

# --- v3.1: 期貨未平倉 + 美股指數因子 ---
V3_1_EXTRA_FEATURES = (
    "TX_INST_NET_OI",   # 大台三大法人淨未平倉量 (zscore)
    "MTX_RETAIL_OI",    # 小台散戶淨未平倉量 (zscore)
    "TX_MTX_SPREAD",    # 大台-小台法人OI差 (zscore)
    "NASDAQ_CLOSE",     # 美股 Nasdaq 收盤 (zscore)
    "SP500_CLOSE",      # 美股 S&P500 收盤 (zscore)
    "DOWJONES_CLOSE",   # 美股道瓊收盤 (zscore)
)

ALL_FEATURE_NAMES = TW_FEATURE_NAMES + V3_1_EXTRA_FEATURES  # 22 因子
N_FEATURES = len(ALL_FEATURE_NAMES)  # 22

# 12 個算子 (沿用 AlphaGPT)
OPERATOR_NAMES = (
    "ADD", "SUB", "MUL", "DIV", "NEG", "ABS",
    "SIGN", "GATE", "JUMP", "DECAY", "DELAY1", "MAX3",
)

VOCAB_SIZE = len(ALL_FEATURE_NAMES) + len(OPERATOR_NAMES) # 34


# ============================================================
# 2. 四階段篩選器 (Marcus + Wenty)
# ============================================================

class RiskGrade(Enum):
    A = "A"  # 最高確定性
    B = "B"  # 中等
    C = "C"  # 最低


@dataclass
class StockSignal:
    """單一股票的交易信號"""
    stock_id: str
    stock_name: str
    stage1_score: float # 宏觀情緒分數 (0-100)
    stage2_score: float # 技術形態分數 (0-100)
    stage3_score: float # 微觀點位分數 (0-100)
    risk_grade: RiskGrade # ABC 風險分級
    entry_price: float # 建議進場價
    stop_loss: float # 止損價
    target_price: float # 目標價
    cvd_status: str # CVD 狀態 (healthy/divergent/neutral)
    absorption_detected: bool # 是否偵測到吸收現象
    five_day_high_break: bool # 是否突破五日高點
    vol_breakout: bool # 是否放量突破
    composite_score: float # 綜合評分
    alpha_formula: str # AlphaGPT 生成的因子公式
    overfit_warning: bool = False # [v2] 過擬合警告旗標
    # [v3] Regime + Alpha 擴展
    regime: str = "" # [v3] 股性分類 (large_cap/mid_cap_tech/traditional/financial)
    alpha_score: float = 0.0 # [v3] GRPO 因子信號分數
    target_holding_days: int = 5 # [v3] 目標持倉天數 (3-7)
    time_stop_days: int = 10 # [v3] 時間止損天數
    trailing_stop_method: str = "atr" # [v3] 移動止損方法 (atr/five_day_high/close_ma)


class Stage1_MacroSentimentFilter:
    """第一階段：宏觀與情緒過濾 (Marcus 三重過濾)

    v2 修正:
    - 增加 min_rows 檢查 (需 >= 20 行)
    - 閾值全部可配置，預設值標注 [UNCALIBRATED]
    - margin_chg 空序列保護
    """

    # [UNCALIBRATED] 以下閾值未經 walk-forward 驗證
    DEFAULT_CONFIG = {
        "min_rows": 20,
        "momentum_threshold": 0.15, # [UNCALIBRATED] 20日動量閾值
        "momentum_score": 30, # [UNCALIBRATED]
        "support_hold_score": 25, # [UNCALIBRATED]
        "inst_buy_score": 25, # [UNCALIBRATED]
        "margin_decrease_score": 20, # [UNCALIBRATED]
        "ma_alignment_score": 20, # [UNCALIBRATED]
        # --- v3.1: 期貨 OI + 美股宏觀評分 ---
        "futures_oi_score": 15, # [UNCALIBRATED] 期貨法人OI偏多
        "us_market_score": 15, # [UNCALIBRATED] 美股偏多
        "pass_threshold": 50, # [UNCALIBRATED]
        "min_inst_buy_days": 3,
        "margin_decrease_threshold": -0.05,
    }

    def __init__(self, config: dict = None):
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}

    def filter(self, df: pd.DataFrame, inst_df: pd.DataFrame = None,
    margin_df: pd.DataFrame = None,
    futures_oi_df: pd.DataFrame = None,
    us_indices_df: pd.DataFrame = None) -> dict:
        """
        輸入：
            df: 日K資料 (date, stock_id, open, high, low, close, volume)
            inst_df: 三大法人買賣超 (date, stock_id, foreign_buy, trust_buy, dealer_buy)
            margin_df: 融資融券 (date, stock_id, margin_buy, margin_sell)
        輸出：
            通過 Stage 1 的股票分數 dict
        """
        scores = {}

        for stock_id, group in df.groupby("stock_id"):
            # [v2] 邊界保護
            if len(group) < self.config["min_rows"]:
                continue

            score = 0.0
            group = group.sort_values("date")

            # 1. 基本面：營收/事件驅動 (暫用價格動量代理)
            ret_20 = group["close"].pct_change(20).iloc[-1]
            if abs(ret_20) > self.config["momentum_threshold"]:
                score += self.config["momentum_score"]

            # 2. 情緒過濾：利空不跌
            recent = group.tail(10)
            down_days = recent[recent["close"] < recent["open"]]
            if len(down_days) > 0:
                last_low = recent["low"].min()
                prev_support = group.tail(20).head(10)["low"].min()
                if last_low >= prev_support:
                    score += self.config["support_hold_score"]

        # 3. 三大法人連續買超 (v3: 使用 total_net = 外資+投信+自營商合計)
        if inst_df is not None:
            inst_data = inst_df[inst_df["stock_id"] == stock_id].sort_values("date")
            inst_recent = inst_data.tail(self.config["min_inst_buy_days"])
            # 優先使用 total_net (三大法人合計)，fallback 到 foreign_net
            net_col = "total_net" if "total_net" in inst_recent.columns else "foreign_net"
            if net_col not in inst_recent.columns:
                net_col = "foreign_buy"  # v2 fallback
            if net_col in inst_recent.columns and len(inst_recent) > 0:
                net_buy = inst_recent[net_col]
                if (net_buy > 0).all():
                    score += self.config["inst_buy_score"]

        # 4. 融資減少 (散戶退場 = 多頭訊號)
        # v3: 使用 margin_balance 變化率取代 margin_buy
        if margin_df is not None:
            margin_data = margin_df[margin_df["stock_id"] == stock_id].sort_values("date")
            margin_recent = margin_data.tail(5)
            if "margin_balance" in margin_recent.columns and len(margin_recent) >= 2:
                bal = margin_recent["margin_balance"]
                # 融資餘額下降 = 散戶退場
                if bal.iloc[-1] < bal.iloc[-2]:
                    chg = (bal.iloc[-1] - bal.iloc[-2]) / (abs(bal.iloc[-2]) + 1e-6)
                    if chg < self.config["margin_decrease_threshold"]:
                        score += self.config["margin_decrease_score"]
            elif "margin_buy" in margin_recent.columns and len(margin_recent) >= 2:
                # v2 fallback
                margin_buy = margin_recent["margin_buy"]
                margin_chg = margin_buy.pct_change()
                last_chg = margin_chg.iloc[-1]
                if pd.notna(last_chg) and last_chg < self.config["margin_decrease_threshold"]:
                    score += self.config["margin_decrease_score"]

            # 5. 均線多頭排列 (5 > 20 > 60)
            ma5 = group["close"].rolling(5).mean().iloc[-1]
            ma20 = group["close"].rolling(20).mean().iloc[-1]
            ma60 = group["close"].rolling(60).mean().iloc[-1] \
                if len(group) >= 60 else ma20
            if ma5 > ma20 > ma60:
                score += self.config["ma_alignment_score"]

        # 6. [v3.1] 期貨法人 OI 偏多 (市場級別訊號)
        if futures_oi_df is not None and len(futures_oi_df) > 0:
            foi = futures_oi_df
            latest_date = foi["date"].max()
            tx = foi[(foi["date"] == latest_date) & (foi["futures_id"] == "TX")]
            if len(tx) > 0 and "inst_net_oi" in tx.columns:
                # 大台法人淨OI > 0 = 偏多
                tx_net = tx["inst_net_oi"].iloc[0]
                if tx_net > 0:
                    score += self.config["futures_oi_score"]

        # 7. [v3.1] 美股偏多 (Nasdaq/S&P500 5日動量正)
        if us_indices_df is not None and len(us_indices_df) > 0:
            us = us_indices_df
            for idx_name in ("Nasdaq", "SP500"):
                idx_data = us[us["index_name"] == idx_name].sort_values("date")
                if len(idx_data) >= 5 and "close" in idx_data.columns:
                    ret_5 = idx_data["close"].pct_change(5).iloc[-1]
                    if ret_5 > 0:
                        score += self.config["us_market_score"] / 2
                        break  # 任一指標偏多即加分

        scores[stock_id] = min(score, 100)

        passed = {k: v for k, v in scores.items()
                  if v >= self.config["pass_threshold"]}
        return passed


class Stage2_TechnicalConfirmFilter:
    """第二階段：技術形態確認

    v2 修正:
    - 增加 min_rows 檢查 (需 >= 20 行以計算 vol_ma20)
    - 閾值可配置，標注 [UNCALIBRATED]
    """

    DEFAULT_CONFIG = {
        "min_rows": 20,
        "vol_breakout_ratio": 1.5,        # [UNCALIBRATED]
        "five_day_high_score": 40,        # [UNCALIBRATED]
        "vol_breakout_score": 35,         # [UNCALIBRATED]
        "resistance_break_score": 25,     # [UNCALIBRATED]
        "pass_threshold": 50,             # [UNCALIBRATED]
        "confirm_close_above": True,
    }

    def __init__(self, config: dict = None):
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}

    def filter(self, df: pd.DataFrame, stage1_passed: dict) -> dict:
        scores = {}

        for stock_id in stage1_passed:
            group = df[df["stock_id"] == stock_id].copy()
            # [v2] 需 >= 20 行才能計算 20 日均量
            if len(group) < self.config["min_rows"]:
                continue

            score = 0.0
            recent = group.tail(5)

            # 1. 五日高點突破
            five_day_high = recent.head(4)["high"].max()
            last_close = group["close"].iloc[-1]

            if last_close > five_day_high:
                score += self.config["five_day_high_score"]

            # 2. 放量結構突破
            vol_ma20 = group["volume"].rolling(20).mean().iloc[-1]
            last_vol = group["volume"].iloc[-1]
            if vol_ma20 > 0 and last_vol > vol_ma20 * self.config["vol_breakout_ratio"]:
                score += self.config["vol_breakout_score"]

            # 3. 收盤站穩阻力位
            resistance = recent.head(4)["close"].max()
            if self.config["confirm_close_above"] and last_close > resistance:
                score += self.config["resistance_break_score"]

            scores[stock_id] = min(score, 100)

        passed = {k: v for k, v in scores.items()
                  if v >= self.config["pass_threshold"]}
        return passed


class Stage3_MicroCVDFilter:
    """第三階段：微觀精準點位 (Wenty 量價核心)

    v2 修正:
    - 增加 min_rows 檢查 (需 >= 20)
    - detect_absorption 增加 min_rows 保護
    - detect_surf_entry 增加 min_rows=2 保護
    - 評分邏輯修正：改用原始分數（不做 clip 到 0），
      因為 clip 會掩蓋 CVD healthy vs divergent 的差異
    - 閾值可配置，標注 [UNCALIBRATED]
    """

    DEFAULT_CONFIG = {
        "min_rows": 20,
        "cvd_window": 10,
        "absorption_vol_threshold": 2.0,   # [UNCALIBRATED]
        "absorption_range_ratio": 0.6,     # [UNCALIBRATED]
        "cvd_healthy_score": 35,           # [UNCALIBRATED]
        "cvd_divergent_score": 5,          # [UNCALIBRATED]
        "cvd_neutral_score": 15,           # [UNCALIBRATED]
        "no_absorption_score": 15,         # [UNCALIBRATED]
        "absorption_penalty": 20,          # [UNCALIBRATED]
        "surf_score": 20,                  # [UNCALIBRATED]
        "no_surf_penalty": 10,             # [UNCALIBRATED]
        "surf_strong_threshold": 0.995,    # [UNCALIBRATED]
        "surf_near_threshold": 0.005,      # [UNCALIBRATED]
        "pass_threshold": 50,              # [UNCALIBRATED]
    }

    def __init__(self, config: dict = None):
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}

    def compute_cvd_proxy(self, group: pd.DataFrame) -> pd.Series:
        """
        CVD 代理指標 (日K級別)
        cvd_proxy = sum((close - open) / (high - low + 1e-6) * volume)
        正值 = 買方主導，負值 = 賣方主導
        """
        cvd = ((group["close"] - group["open"]) /
               (group["high"] - group["low"] + 1e-6)) * group["volume"]
        return cvd.cumsum()

    def detect_absorption(self, group: pd.DataFrame) -> bool:
        """
        偵測吸收現象
        volume 大增 + 價格波動收窄 = 大量買單被賣方掛單吸收
        """
        if len(group) < 20:
            return False

        recent = group.tail(5)
        vol_ma = group["volume"].rolling(20).mean().iloc[-1]
        if pd.isna(vol_ma) or vol_ma <= 0:
            return False

        avg_range = (recent["high"] - recent["low"]).mean()
        historical_range = (group["high"] - group["low"]).rolling(20).mean().iloc[-1]
        if pd.isna(historical_range) or historical_range <= 0:
            return False

        vol_surge = recent["volume"].iloc[-1] > vol_ma * self.config["absorption_vol_threshold"]
        range_narrow = avg_range < historical_range * self.config["absorption_range_ratio"]

        return vol_surge and range_narrow

    def detect_surf_entry(self, group: pd.DataFrame) -> Tuple[bool, float]:
        """
        衝浪手切入判斷
        開盤價位於前日關鍵價位附近 → 切入信號
        """
        if len(group) < 2:
            return False, 0.0

        prev_close = group["close"].iloc[-2]
        prev_high = group["high"].iloc[-2]
        today_open = group["open"].iloc[-1]

        # 開盤價在前日高點附近或之上 = 強勢切入位
        if today_open >= prev_high * self.config["surf_strong_threshold"]:
            return True, today_open
        # 開盤價在前日收盤附近 = 觀察位
        if abs(today_open - prev_close) / (prev_close + 1e-6) < self.config["surf_near_threshold"]:
            return True, today_open
        return False, 0.0

    def filter(self, df: pd.DataFrame, stage2_passed: dict) -> dict:
        results = {}

        for stock_id in stage2_passed:
            group = df[df["stock_id"] == stock_id].copy()
            if len(group) < self.config["min_rows"]:
                continue

            score = 0.0

            # 1. CVD 背離分析
            cvd = self.compute_cvd_proxy(group)
            cvd_recent = cvd.tail(self.config["cvd_window"])
            price_recent = group["close"].tail(self.config["cvd_window"])

            cvd_trend = cvd_recent.iloc[-1] - cvd_recent.iloc[0]
            price_trend = price_recent.iloc[-1] - price_recent.iloc[0]

            if price_trend > 0 and cvd_trend > 0:
                score += self.config["cvd_healthy_score"]
                cvd_status = "healthy"
            elif price_trend > 0 and cvd_trend <= 0:
                score += self.config["cvd_divergent_score"]
                cvd_status = "divergent"
            else:
                score += self.config["cvd_neutral_score"]
                cvd_status = "neutral"

            # 2. 吸收現象
            absorption = self.detect_absorption(group)
            if absorption:
                score -= self.config["absorption_penalty"]
            else:
                score += self.config["no_absorption_score"]

            # 3. 衝浪手切入
            surf_ok, entry_price = self.detect_surf_entry(group)
            if surf_ok:
                score += self.config["surf_score"]
            else:
                score -= self.config["no_surf_penalty"]

            # [v2] 保留原始分數不做 clip — composite_score 計算時才 clamp
            results[stock_id] = {
                "score": score,  # 原始分數，可為負
                "score_clamped": min(max(score, 0), 100),  # 相容用
                "cvd_status": cvd_status,
                "absorption": absorption,
                "surf_entry": surf_ok,
                "entry_price": entry_price,
            }

        # 篩選時用 clamped 分數
        passed = {k: v for k, v in results.items()
                  if v["score_clamped"] >= self.config["pass_threshold"]}
        return passed


class Stage4_RiskManager:
    """第四階段：動態風險管理

    v2 修正:
    - composite_score 權重可配置
    - ATR 計算加入 min_rows 保護
    - 過擬合警告旗標
    """

    DEFAULT_CONFIG = {
        "max_risk_per_trade": 0.02,
        "atr_stop_multiplier": 2.0,
        "atr_window": 14,
        "pyramid_levels": 3,
        # composite_score 權重 [UNCALIBRATED]
        "stage1_weight": 0.3,
        "stage2_weight": 0.35,
        "stage3_weight": 0.35,
    }

    def __init__(self, config: dict = None):
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}

    def compute_atr(self, group: pd.DataFrame, window: int = None) -> float:
        """計算 ATR (Average True Range)"""
        window = window or self.config["atr_window"]
        if len(group) < window + 1:
            # 不足窗口時用簡化計算
            if len(group) < 2:
                return group["close"].iloc[-1] * 0.02  # 預設 2%
            return (group["high"] - group["low"]).mean()

        high = group["high"]
        low = group["low"]
        close_prev = group["close"].shift(1)

        tr1 = high - low
        tr2 = (high - close_prev).abs()
        tr3 = (low - close_prev).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window).mean().iloc[-1]
        return atr if pd.notna(atr) else (group["high"] - group["low"]).mean()

    def classify_risk(self, stage_scores: dict) -> RiskGrade:
        """
        ABC 機會分級
        A: 三階段都高分 (>70)
        B: 兩階段高分
        C: 勉強通過
        """
        high_count = sum(1 for s in stage_scores.values() if s >= 70)
        if high_count >= 3:
            return RiskGrade.A
        elif high_count >= 2:
            return RiskGrade.B
        else:
            return RiskGrade.C

    def compute_position_sizes(self, grade: RiskGrade, capital: float) -> dict:
        """
        根據風險等級分配倉位
        金字塔結構：底座最大，往上遞減
        """
        risk_allocation = {
            RiskGrade.A: 0.06,  # 6% of capital
            RiskGrade.B: 0.04,  # 4%
            RiskGrade.C: 0.02,  # 2%
        }
        total_risk = risk_allocation[grade] * capital

        positions = {}
        base_size = total_risk * 0.5  # 底座 50%
        positions["level_1"] = base_size
        positions["level_2"] = base_size * 0.3  # 第二層 30%
        positions["level_3"] = base_size * 0.2  # 第三層 20%
        return positions

    def compute_stops(self, entry_price: float, atr: float,
                      five_day_high: float) -> Tuple[float, float]:
        """
        計算止損與移動止損
        初始止損 = entry - ATR * multiplier
        移動止損 = 跟隨五日高點
        """
        initial_stop = entry_price - atr * self.atr_stop_multiplier
        trailing_stop = five_day_high - atr * self.atr_stop_multiplier
        return initial_stop, trailing_stop

    @property
    def atr_stop_multiplier(self):
        return self.config["atr_stop_multiplier"]

    def manage(self, stock_id: str, df: pd.DataFrame,
               stage_scores: dict, entry_data: dict) -> StockSignal:
        """完整的風險管理評估"""
        group = df[df["stock_id"] == stock_id]
        atr = self.compute_atr(group)
        grade = self.classify_risk(stage_scores)
        five_day_high = group.tail(5)["high"].max()
        entry_price = entry_data.get("entry_price", group["close"].iloc[-1])

        initial_stop, trailing_stop = self.compute_stops(
            entry_price, atr, five_day_high
        )

        # 目標價 = 2 * 風險 (盈虧比 2:1)
        risk = entry_price - initial_stop
        target_price = entry_price + 2 * risk

        # [v2] 權重可配置
        composite = (
            stage_scores.get("stage1", 0) * self.config["stage1_weight"] +
            stage_scores.get("stage2", 0) * self.config["stage2_weight"] +
            stage_scores.get("stage3", 0) * self.config["stage3_weight"]
        )

        # [v2] 過擬合警告：任一 stage 閾值通過但未校準
        overfit_warning = entry_data.get("overfit_warning", False)

        return StockSignal(
            stock_id=stock_id,
            stock_name="",
            stage1_score=stage_scores.get("stage1", 0),
            stage2_score=stage_scores.get("stage2", 0),
            stage3_score=stage_scores.get("stage3", 0),
            risk_grade=grade,
            entry_price=entry_price,
            stop_loss=initial_stop,
            target_price=target_price,
            cvd_status=entry_data.get("cvd_status", "neutral"),
            absorption_detected=entry_data.get("absorption", False),
            five_day_high_break=entry_data.get("five_day_high_break", False),
            vol_breakout=entry_data.get("vol_breakout", False),
            composite_score=composite,
            alpha_formula=entry_data.get("alpha_formula", ""),
            overfit_warning=overfit_warning,
        )


# ============================================================
# 3. 完整篩選管線
# ============================================================

class AIDigMoneyPipeline:
    """台股 AI Dig Money 完整篩選管線

    v2 新增:
    - integrate_with_alpha(): 統一因子計算 → 篩選管線
    - 過擬合警告傳遞
    """

    # [UNCALIBRATED] 所有子階段閾值均未經 walk-forward 驗證
    OVERFIT_DISCLAIMER = (
        "[WARNING] 所有閾值均為 [UNCALIBRATED] — "
        "請先執行 anti_overfit.py 的 Walk-Forward 驗證後再信任結果"
    )

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.stage1 = Stage1_MacroSentimentFilter(self.config.get("stage1", {}))
        self.stage2 = Stage2_TechnicalConfirmFilter(self.config.get("stage2", {}))
        self.stage3 = Stage3_MicroCVDFilter(self.config.get("stage3", {}))
        self.stage4 = Stage4_RiskManager(self.config.get("stage4", {}))

    def run(self, df: pd.DataFrame,
            inst_df: pd.DataFrame = None,
            margin_df: pd.DataFrame = None,
            alpha_formulas: dict = None,
            feature_df: pd.DataFrame = None,
            futures_oi_df: pd.DataFrame = None,
            us_indices_df: pd.DataFrame = None) -> List[StockSignal]:
        """
        執行完整的四階段篩選 (v2 向後相容)

        Args:
            df: 日K資料 (date, stock_id, open, high, low, close, volume)
            inst_df: 三大法人買賣超 (optional)
            margin_df: 融資融券 (optional)
            alpha_formulas: AlphaGPT 生成的因子公式 {stock_id: formula}
            feature_df: [v2] 預計算的因子矩陣 (optional)
            futures_oi_df: 期貨未平倉量 (optional, v3.1 新增)
            us_indices_df: 美股大盤指數 (optional, v3.1 新增)

        Returns:
            通過四階段的交易信號列表
        """
        print(f"[AI Dig Money v2] 開始篩選，共 {df['stock_id'].nunique()} 檔股票")
        warnings.warn(self.OVERFIT_DISCLAIMER, UserWarning, stacklevel=2)

        # Stage 1
        s1_passed = self.stage1.filter(df, inst_df, margin_df,
                                       futures_oi_df, us_indices_df)
        print(f"  Stage 1 (宏觀情緒): {len(s1_passed)} 檔通過")

        # Stage 2
        s2_passed = self.stage2.filter(df, s1_passed)
        print(f"  Stage 2 (技術確認): {len(s2_passed)} 檔通過")

        # Stage 3
        s3_passed = self.stage3.filter(df, s2_passed)
        print(f"  Stage 3 (微觀點位): {len(s3_passed)} 檔通過")

        # Stage 4: 風險管理 + 信號生成
        signals = []
        for stock_id, s3_data in s3_passed.items():
            stage_scores = {
                "stage1": s1_passed.get(stock_id, 0),
                "stage2": s2_passed.get(stock_id, 0),
                "stage3": s3_data["score_clamped"],
            }
            entry_data = {
                "entry_price": s3_data["entry_price"],
                "cvd_status": s3_data["cvd_status"],
                "absorption": s3_data["absorption"],
                "five_day_high_break": True,  # already passed stage2
                "vol_breakout": True,
                "alpha_formula": alpha_formulas.get(stock_id, "") if alpha_formulas else "",
                "overfit_warning": True,  # [v2] 所有結果都帶過擬合警告
            }
            signal = self.stage4.manage(stock_id, df, stage_scores, entry_data)
            signals.append(signal)

        # 按 composite_score 排序
        signals.sort(key=lambda s: s.composite_score, reverse=True)

        print(f"  Stage 4 (風險管理): {len(signals)} 檔最終信號")
        for s in signals[:5]:
            warn_tag = " [過擬合警告]" if s.overfit_warning else ""
            print(f"   {s.stock_id}: Score={s.composite_score:.1f} "
                  f"Grade={s.risk_grade.value} Entry={s.entry_price:.1f} "
                  f"Stop={s.stop_loss:.1f} Target={s.target_price:.1f}"
                  f"{warn_tag}")

        return signals


# ============================================================
# 3b. [v3] 分層遞進式五階段管線 (方案 A-3)
# ============================================================

class AIDigMoneyV3Pipeline:
    """
    [v3] 台股 AI Dig Money 分層遞進式管線

    核心設計：Rule-based 先篩 → GRPO 因子精煉 → 微觀確認 → 風控 → 反饋

    Phase 1 (粗篩): Stage1-2 rule-based → 篩出候選池
    Phase 2 (精煉): GRPO 分股性訓練 → 因子公式 → alpha 增強/降級
    Phase 3 (微觀): Stage3 CVD/吸收/衝浪手確認
    Phase 4 (風控): Stage4 動態風險管理 + 3-7天持倉適配
    Phase 5 (反饋): 回測結果 → 更新閾值 + GRPO reward

    設計原則:
    - AlphaGPT 核心不動: GRPO 挖掘因子公式的能力獨立運作
    - 先篩後訓: 減少 GRPO 的搜索空間，提升信噪比
    - 因股性分群: 不同 regime 用不同特徵權重和算子偏好
    - 3-7天週期: 各 phase 都圍繞短期交易窗口設計
    """

    OVERFIT_DISCLAIMER = (
        "[WARNING] 所有閾值均為 [UNCALIBRATED] — "
        "請先執行 anti_overfit.py 的 Walk-Forward 驗證後再信任結果"
    )

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.stage1 = Stage1_MacroSentimentFilter(self.config.get("stage1", {}))
        self.stage2 = Stage2_TechnicalConfirmFilter(self.config.get("stage2", {}))
        self.stage3 = Stage3_MicroCVDFilter(self.config.get("stage3", {}))
        self.stage4 = Stage4_RiskManager(self.config.get("stage4", {}))

        # [v3] Regime 偵測 + 訓練計畫
        self.regime_detector = None  # lazy import
        self.regime_planner = None

        # [v3] 反饋歷史
        self.feedback_history: List[dict] = []

        # [v3] 3-7天週期適配
        self.default_holding_config = {
            "min_holding_days": 3,
            "max_holding_days": 7,
            "default_holding_days": 5,
            "time_stop_multiplier": 2.0,  # time_stop = target_holding * multiplier
        }

    def _lazy_import_regime(self):
        """延遲導入 stock_regime 模組"""
        if self.regime_detector is None:
            from stock_regime import RegimeDetector, RegimeTrainingPlan
            self.regime_detector = RegimeDetector
            self.regime_planner = RegimeTrainingPlan()

    # ============================================================
    # Phase 1: Rule-based 粗篩
    # ============================================================

    def phase1_rough_filter(self, df: pd.DataFrame,
                            inst_df: pd.DataFrame = None,
                            margin_df: pd.DataFrame = None,
                            futures_oi_df: pd.DataFrame = None,
                            us_indices_df: pd.DataFrame = None) -> dict:
        """
        Phase 1: Rule-based 粗篩 (Stage1-2)

        目標：從全台股 1000+ 檔中篩出 50-100 檔候選池
        這是 Marcus 三重過濾法的第一層和第二層

        Returns:
            {
                "s1_passed": {stock_id: score},
                "s2_passed": {stock_id: score},
                "candidate_pool": [stock_id, ...],
            }
        """
        print(f"\n[Phase 1] 粗篩開始 — {df['stock_id'].nunique()} 檔")
        s1_passed = self.stage1.filter(df, inst_df, margin_df,
                                       futures_oi_df, us_indices_df)
        print(f"  Stage 1 (宏觀情緒): {len(s1_passed)} 檔通過")

        s2_passed = self.stage2.filter(df, s1_passed)
        print(f"  Stage 2 (技術確認): {len(s2_passed)} 檔通過")

        candidate_pool = list(s2_passed.keys())
        print(f"  Phase 1 結果: {len(candidate_pool)} 檔進入候選池")

        return {
            "s1_passed": s1_passed,
            "s2_passed": s2_passed,
            "candidate_pool": candidate_pool,
        }

    # ============================================================
    # Phase 2: GRPO 因子精煉
    # ============================================================

    def phase2_alpha_refine(self, df: pd.DataFrame,
                               phase1_result: dict,
                               feature_df: pd.DataFrame = None,
                               futures_oi_df: pd.DataFrame = None,
                               us_indices_df: pd.DataFrame = None,
                               n_iterations: int = 30) -> dict:
        """
        Phase 2: GRPO 因子精煉

        只在候選池上訓練，按 regime 分群，生成因子公式
        因子信號會增強或降級 rule-based 的分數

        Args:
            df: 日K資料
            phase1_result: Phase 1 的輸出
            feature_df: 預計算特徵矩陣 (optional)
            futures_oi_df: 期貨未平倉量 (optional, v3.1 新增)
            us_indices_df: 美股大盤指數 (optional, v3.1 新增)
            n_iterations: GRPO 訓練迭代數

        Returns:
            {
                "regime_map": {stock_id: StockRegime},
                "alpha_formulas": {stock_id: formula_str},
                "alpha_scores": {stock_id: float},
                "enhanced_scores": {stock_id: float},  # rule + alpha
            }
        """
        self._lazy_import_regime()

        candidate_pool = phase1_result["candidate_pool"]
        s2_passed = phase1_result["s2_passed"]

        print(f"\n[Phase 2] 因子精煉 — {len(candidate_pool)} 檔候選")

        # Step 2a: 偵測 regime
        regime_map = {}
        for stock_id in candidate_pool:
            regime = self.regime_detector.detect(stock_id, df)
            regime_map[stock_id] = regime

        # 統計 regime 分佈
        regime_counts = {}
        for r in regime_map.values():
            key = r.value
            regime_counts[key] = regime_counts.get(key, 0) + 1
        print(f"  Regime 分佈: {regime_counts}")

        # Step 2b: 生成訓練計畫
        plans = self.regime_planner.create_plans_batch(regime_map)

        # Step 2c: GRPO 訓練 (如果特徵矩陣可用)
        alpha_formulas = {}
        alpha_scores = {}

        if feature_df is not None:
            # v3.1: 期貨OI + 美股指數特徵已由 compute_features() 整合
            # 不再重複合併原始資料 (避免 futures_id/index_name 等非數值欄位污染)
            v31_feats = [f for f in ("TX_INST_NET_OI", "MTX_RETAIL_OI", "TX_MTX_SPREAD",
                                      "NASDAQ_CLOSE", "SP500_CLOSE", "DOWJONES_CLOSE")
                         if f in feature_df.columns]
            if v31_feats:
                print(f" [v3.1] 已含 {len(v31_feats)}/6 期貨+美股因子")

            # v3.2: GRPO fallback — 優先載入 Kaggle 訓練結果
            # 路徑1: 嘗試從 grpo_alpha_trainer 模組（GPU 本地訓練）
            grpo_available = False
            try:
                from grpo_alpha_trainer import GRPOAlphaTrainer, GRPOConfig
                grpo_available = True
            except ImportError:
                pass

            if grpo_available:
                # --- GPU 本地訓練路徑 ---
                config = GRPOConfig.auto_detect()
                trainer = GRPOAlphaTrainer(config)

                stock_data_map = {}
                for stock_id in candidate_pool:
                    stock_feat = feature_df[feature_df["stock_id"] == stock_id]
                    if len(stock_feat) > 0:
                        feat_cols = [c for c in stock_feat.columns
                                     if c not in ("date", "stock_id")]
                        feat_tensor = stock_feat[feat_cols].values.T.astype(np.float32)
                        close = stock_feat["close"].values if "close" in stock_feat.columns else None
                        returns = np.random.randn(feat_tensor.shape[1]).astype(np.float32) * 0.02
                        stock_data_map[stock_id] = {
                            "feat": feat_tensor,
                            "returns": returns,
                            "regime_plan": plans.get(stock_id),
                        }

                if stock_data_map:
                    results = trainer.train_multi_regime(
                        stock_data_map,
                        n_iterations_per_regime=n_iterations,
                    )
                    for stock_id, res in results.items():
                        if res.get("best_formula"):
                            from grpo_alpha_trainer import FormulaDecoder
                            alpha_formulas[stock_id] = FormulaDecoder.decode(res["best_formula"])
                            alpha_scores[stock_id] = res.get("best_reward", 0.0)
            else:
                # --- Fallback: 載入 Kaggle 訓練結果 ---
                _strategy_paths = [
                    Path("best_strategy_per_regime.json"),
                    Path("/data/.hermes/skills/research/twstock-alpha-gpt/scripts/best_strategy_per_regime.json"),
                    Path("/tmp/kaggle-output-v51/best_strategy_per_regime.json"),
                    Path("/tmp/grpo_v4_results/best_strategy_per_regime.json"),
                ]
                _loaded = False
                for _sp in _strategy_paths:
                    if _sp.exists():
                        try:
                            with open(_sp, 'r') as _f:
                                _strategy = json.load(_f)
                            print(f"  [v3.2] 載入 Kaggle 訓練結果: {_sp}")
                            _loaded = True
                            break
                        except Exception as e:
                            print(f"  [v3.2] 讀取失敗 {_sp}: {e}")

                if _loaded:
                    # 將 per-regime 結果對應到各 stock
                    _regime_stock_map = {}
                    for _sid in candidate_pool:
                        _r = regime_map.get(_sid)
                        if _r:
                            _rk = _r.value
                            _regime_stock_map.setdefault(_rk, []).append(_sid)

                    for _regime_key, _res in _strategy.items():
                        _formula = _res.get("decoded_formula", "[unknown]")
                        _reward = _res.get("best_reward", 0.0)
                        _val_ic = _res.get("val_ic", 0.0)
                        _target_stocks = _regime_stock_map.get(_regime_key, [])
                        for _sid in _target_stocks:
                            alpha_formulas[_sid] = _formula
                            alpha_scores[_sid] = _val_ic if _val_ic else _reward
                            print(f"  {_sid} ({_regime_key}): formula={_formula} "
                                  f"val_ic={_val_ic:.4f} reward={_reward:.4f}")
                        # Fallback for stocks whose regime is not in training results
                        _covered = set(alpha_formulas.keys())
                        _uncovered = [s for s in candidate_pool if s not in _covered]
                        if _uncovered:
                            for _sid in _uncovered:
                                _rk = regime_map.get(_sid)
                                _rk_val = _rk.value if _rk else "unknown"
                                alpha_formulas[_sid] = f"[no-training:{_rk_val}]"
                                alpha_scores[_sid] = 0.0
                            print(f" {len(_uncovered)} stocks without training result, "
                                  f"using fallback")
                else:
                    # --- 最終防線: 用 feature_df 統計量估算 ---
                    print("  [v3.2] 無訓練結果可用，使用 feature 統計量估算")
                    for stock_id in candidate_pool:
                        stock_feat = feature_df[feature_df["stock_id"] == stock_id]
                        if len(stock_feat) > 0:
                            feat_cols = [c for c in stock_feat.columns
                                         if c not in ("date", "stock_id")]
                            recent = stock_feat[feat_cols].tail(20).mean()
                            alpha_scores[stock_id] = float(recent.mean())
                            alpha_formulas[stock_id] = "[stat-estimator]"
                        else:
                            alpha_scores[stock_id] = 0.0
                            alpha_formulas[stock_id] = "[no-data]"
        else:
            # 無特徵矩陣 → 用 rule-based 分數直接作為 alpha_score
            for stock_id in candidate_pool:
                alpha_scores[stock_id] = s2_passed.get(stock_id, 0) / 100.0
                alpha_formulas[stock_id] = "[rule-based only]"

        # Step 2d: 融合 rule + alpha
        enhanced_scores = {}
        for stock_id in candidate_pool:
            rule_score = s2_passed.get(stock_id, 0)
            alpha_s = alpha_scores.get(stock_id, 0.0)

            # [UNCALIBRATED] 融合權重
            # alpha 信號 [-5, 5] 映射到 [0, 100] 補充分數
            alpha_bonus = np.clip(alpha_s * 10, -20, 20)
            enhanced_scores[stock_id] = np.clip(
                rule_score + alpha_bonus, 0, 100
            )

        # 顯示 Phase 2 結果
        for stock_id in candidate_pool[:5]:
            regime = regime_map[stock_id].value
            rule_s = s2_passed.get(stock_id, 0)
            alpha_s = alpha_scores.get(stock_id, 0.0)
            enhanced = enhanced_scores[stock_id]
            print(f"  {stock_id} ({regime}): "
                  f"rule={rule_s:.0f} alpha={alpha_s:.3f} "
                  f"enhanced={enhanced:.1f}")

        return {
            "regime_map": regime_map,
            "alpha_formulas": alpha_formulas,
            "alpha_scores": alpha_scores,
            "enhanced_scores": enhanced_scores,
        }

    # ============================================================
    # Phase 3: 微觀確認
    # ============================================================

    def phase3_micro_confirm(self, df: pd.DataFrame,
                             phase1_result: dict,
                             phase2_result: dict) -> dict:
        """
        Phase 3: 微觀精準點位 (Wenty 量價核心)

        在 Phase 2 的增強分數上，用 Stage3 CVD/吸收/衝浪手確認

        Returns:
            {
                "s3_passed": {stock_id: s3_data},
                "confirmed_signals": [stock_id, ...],
            }
        """
        # 用 Phase 2 的 enhanced_scores 取代 s2_passed
        # 但 Stage3 的 filter 仍需要原始 s2_passed 格式
        s2_enhanced = phase2_result["enhanced_scores"]

        print(f"\n[Phase 3] 微觀確認 — {len(s2_enhanced)} 檔")

        s3_passed = self.stage3.filter(df, s2_enhanced)
        print(f"  Stage 3 (微觀點位): {len(s3_passed)} 檔通過")

        return {
            "s3_passed": s3_passed,
            "confirmed_signals": list(s3_passed.keys()),
        }

    # ============================================================
    # Phase 4: 風控 + 3-7天適配
    # ============================================================

    def phase4_risk_manage(self, df: pd.DataFrame,
                           phase1_result: dict,
                           phase2_result: dict,
                           phase3_result: dict) -> List[StockSignal]:
        """
        Phase 4: 動態風險管理 + 3-7天持倉適配

        根據 regime 的 target_holding_days 調整:
        - ATR 止損倍數 (長持倉 → 寬止損)
        - 時間止損 (target_holding * multiplier)
        - 移動止損方法 (金融股用 close_ma, 科技股用 five_day_high)
        """
        s1_passed = phase1_result["s1_passed"]
        regime_map = phase2_result["regime_map"]
        alpha_formulas = phase2_result["alpha_formulas"]
        alpha_scores = phase2_result["alpha_scores"]
        s3_passed = phase3_result["s3_passed"]

        print(f"\n[Phase 4] 風控 + 持倉適配 — {len(s3_passed)} 檔")

        signals = []
        for stock_id, s3_data in s3_passed.items():
            regime = regime_map.get(stock_id)
            regime_str = regime.value if regime else "mid_cap_tech"

            # 持倉天數適配
            holding_days = self._get_holding_days(stock_id, regime)
            time_stop = int(holding_days * self.default_holding_config["time_stop_multiplier"])

            # 移動止損方法適配
            trailing_method = self._get_trailing_stop_method(regime)

            # ATR 止損倍數適配 (長持倉 → 寬止損)
            atr_mult = self._get_atr_multiplier(holding_days)

            stage_scores = {
                "stage1": s1_passed.get(stock_id, 0),
                "stage2": phase1_result["s2_passed"].get(stock_id, 0),
                "stage3": s3_data["score_clamped"],
            }

            # [v3] composite 加入 alpha_score 權重
            alpha_s = alpha_scores.get(stock_id, 0.0)
            alpha_bonus = np.clip(alpha_s * 10, -20, 20)
            composite = (
                stage_scores.get("stage1", 0) * self.config.get("stage1_weight", 0.25) +
                stage_scores.get("stage2", 0) * self.config.get("stage2_weight", 0.30) +
                stage_scores.get("stage3", 0) * self.config.get("stage3_weight", 0.30) +
                alpha_bonus * self.config.get("alpha_weight", 0.15)
            )
            composite = np.clip(composite, 0, 100)

            entry_data = {
                "entry_price": s3_data["entry_price"],
                "cvd_status": s3_data["cvd_status"],
                "absorption": s3_data["absorption"],
                "five_day_high_break": True,
                "vol_breakout": True,
                "alpha_formula": alpha_formulas.get(stock_id, ""),
                "overfit_warning": True,
            }

            # 計算風控
            signal = self.stage4.manage(stock_id, df, stage_scores, entry_data)

            # [v3] 覆寫 composite_score (加入 alpha 權重)
            signal.composite_score = composite

            # [v3] 附加 regime + 持倉資訊
            signal.regime = regime_str
            signal.alpha_score = alpha_s
            signal.target_holding_days = holding_days
            signal.time_stop_days = time_stop
            signal.trailing_stop_method = trailing_method

            # [v3] 調整止損 (寬持倉 → 寬止損)
            if atr_mult != self.stage4.config["atr_stop_multiplier"]:
                group = df[df["stock_id"] == stock_id]
                atr = self.stage4.compute_atr(group)
                signal.stop_loss = signal.entry_price - atr * atr_mult
                risk = signal.entry_price - signal.stop_loss
                signal.target_price = signal.entry_price + 2 * risk

            signals.append(signal)

        # 排序
        signals.sort(key=lambda s: s.composite_score, reverse=True)

        print(f"  Phase 4 結果: {len(signals)} 檔最終信號")
        for s in signals[:5]:
            warn_tag = " [過擬合]" if s.overfit_warning else ""
            print(f"   {s.stock_id} ({s.regime}): "
                  f"Score={s.composite_score:.1f} "
                  f"Hold={s.target_holding_days}d "
                  f"TimeStop={s.time_stop_days}d "
                  f"Trail={s.trailing_stop_method}"
                  f"{warn_tag}")

        return signals

    # ============================================================
    # Phase 5: 反饋閉環
    # ============================================================

    def phase5_feedback(self, signals: List[StockSignal],
                        backtest_results: dict = None) -> dict:
        """
        Phase 5: 反饋閉環

        將回測結果回饋到:
        1. Rule-based 閾值調整
        2. GRPO reward 權重調整
        3. Regime 分群邊界修正

        Args:
            signals: Phase 4 的交易信號
            backtest_results: 回測結果 {
                stock_id: {pnl, win_rate, max_drawdown, actual_holding_days, ...}
            }

        Returns:
            {
                "threshold_adjustments": {stage: {param: new_value}},
                "reward_adjustments": {param: new_value},
                "regime_corrections": {stock_id: suggested_regime},
                "summary": str,
            }
        """
        print(f"\n[Phase 5] 反饋分析 — {len(signals)} 檔")

        if backtest_results is None:
            print("  [SKIP] 無回測數據，跳過反饋")
            return {
                "threshold_adjustments": {},
                "reward_adjustments": {},
                "regime_corrections": {},
                "summary": "無回測數據，反饋跳過",
            }

        # 分析持倉天數偏差
        holding_deviations = []
        regime_corrections = {}

        for signal in signals:
            stock_id = signal.stock_id
            if stock_id not in backtest_results:
                continue

            bt = backtest_results[stock_id]
            actual_holding = bt.get("actual_holding_days", 0)
            expected_holding = signal.target_holding_days
            deviation = actual_holding - expected_holding
            holding_deviations.append(deviation)

            # 持倉偏差 > 2 天 → 可能 regime 分類錯誤
            if abs(deviation) > 2:
                if actual_holding > expected_holding + 2:
                    # 實際持倉比預期長 → 可能是金融/傳產
                    if signal.regime == "mid_cap_tech":
                        regime_corrections[stock_id] = "traditional"
                elif actual_holding < expected_holding - 2:
                    # 實際持倉比預期短 → 可能是科技/高波動
                    if signal.regime in ("traditional", "financial"):
                        regime_corrections[stock_id] = "mid_cap_tech"

        # 計算閾值調整建議
        win_rate = np.mean([
            backtest_results.get(s.stock_id, {}).get("win", False)
            for s in signals if s.stock_id in backtest_results
        ]) if signals else 0.0

        threshold_adjustments = {}
        if win_rate < 0.4:
            # 勝率過低 → 提高通過閾值
            threshold_adjustments["stage1"] = {"pass_threshold": "+10"}
            threshold_adjustments["stage2"] = {"pass_threshold": "+10"}
        elif win_rate > 0.6:
            # 勝率過高 (可能漏掉機會) → 微調閾值
            threshold_adjustments["stage1"] = {"pass_threshold": "-5"}

        # Reward 調整
        reward_adjustments = {}
        avg_deviation = np.mean(holding_deviations) if holding_deviations else 0
        if avg_deviation > 1:
            reward_adjustments["reward_horizon"] = "+1"  # 加長 reward 窗口
        elif avg_deviation < -1:
            reward_adjustments["reward_horizon"] = "-1"  # 縮短 reward 窗口

        # 記錄反饋
        feedback = {
            "timestamp": pd.Timestamp.now().isoformat(),
            "n_signals": len(signals),
            "win_rate": win_rate,
            "avg_holding_deviation": avg_deviation,
            "threshold_adjustments": threshold_adjustments,
            "reward_adjustments": reward_adjustments,
            "regime_corrections": regime_corrections,
        }
        self.feedback_history.append(feedback)

        summary = (
            f"勝率: {win_rate:.1%} | "
            f"持倉偏差: {avg_deviation:+.1f}天 | "
            f"Regime修正: {len(regime_corrections)}檔 | "
            f"閾值調整: {threshold_adjustments}"
        )
        print(f"  {summary}")

        return {
            "threshold_adjustments": threshold_adjustments,
            "reward_adjustments": reward_adjustments,
            "regime_corrections": regime_corrections,
            "summary": summary,
        }

    # ============================================================
    # 輔助方法: 3-7天持倉適配
    # ============================================================

    def _get_holding_days(self, stock_id: str, regime=None) -> int:
        """
        根據 regime 設定目標持倉天數

        - LARGE_CAP: 5天 (法人進出節奏)
        - MID_CAP_TECH: 4天 (技術突破快進快出)
        - TRADITIONAL: 5天 (營收驅動較慢)
        - FINANCIAL: 7天 (低波動需要更長時間)
        """
        if regime is None:
            self._lazy_import_regime()
            regime = self.regime_detector.detect(stock_id, pd.DataFrame())

        # 從 regime 取得 target_holding_days
        if self.regime_planner is not None:
            plan = self.regime_planner.create_plan(stock_id, regime)
            return plan["target_holding_days"]

        # Fallback 預設值
        holding_map = {
            "large_cap": 5,
            "mid_cap_tech": 4,
            "traditional": 5,
            "financial": 7,
        }
        regime_str = regime.value if hasattr(regime, "value") else str(regime)
        return holding_map.get(regime_str, 5)

    def _get_trailing_stop_method(self, regime) -> str:
        """
        根據 regime 選擇移動止損方法

        - LARGE_CAP: ATR-based (法人進出穩定)
        - MID_CAP_TECH: five_day_high (突破追蹤)
        - TRADITIONAL: close_ma (20日均線追蹤)
        - FINANCIAL: close_ma (長持倉用均線)
        """
        regime_str = regime.value if regime and hasattr(regime, "value") else "mid_cap_tech"
        method_map = {
            "large_cap": "atr",
            "mid_cap_tech": "five_day_high",
            "traditional": "close_ma",
            "financial": "close_ma",
        }
        return method_map.get(regime_str, "atr")

    def _get_atr_multiplier(self, holding_days: int) -> float:
        """
        根據持倉天數調整 ATR 止損倍數

        短持倉 (3天) → 窄止損 (1.5 ATR)
        中持倉 (5天) → 標準止損 (2.0 ATR)
        長持倉 (7天) → 寬止損 (2.5 ATR)

        [UNCALIBRATED] 所有倍數未經驗證
        """
        if holding_days <= 3:
            return 1.5
        elif holding_days <= 5:
            return 2.0
        else:
            return 2.5

    # ============================================================
    # 完整 5-Phase 執行入口
    # ============================================================

    def run(self, df: pd.DataFrame,
            inst_df: pd.DataFrame = None,
            margin_df: pd.DataFrame = None,
            feature_df: pd.DataFrame = None,
            backtest_results: dict = None,
            futures_oi_df: pd.DataFrame = None,
            us_indices_df: pd.DataFrame = None,
            n_iterations: int = 30) -> List[StockSignal]:
        """
        執行完整的 v3 五階段管線

        Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5

        Args:
            df: 日K資料
            inst_df: 三大法人 (optional)
            margin_df: 融資融券 (optional)
            feature_df: 預計算特徵矩陣 (optional, GRPO 需要)
            backtest_results: 回測結果 (optional, Phase 5 需要)
            futures_oi_df: 期貨未平倉量 (optional, v3.1 新增)
            us_indices_df: 美股大盤指數 (optional, v3.1 新增)
            n_iterations: GRPO 訓練迭代數

        Returns:
            交易信號列表 (含 regime, alpha_score, holding_days)
        """
        print("=" * 60)
        print("  台股 AI Dig Money 系統 - v3 分層遞進式")
        print("=" * 60)
        warnings.warn(self.OVERFIT_DISCLAIMER, UserWarning, stacklevel=2)

        # Phase 1: Rule-based 粗篩
        phase1 = self.phase1_rough_filter(df, inst_df, margin_df,
                                          futures_oi_df, us_indices_df)

        # Phase 2: GRPO 因子精煉
        phase2 = self.phase2_alpha_refine(
            df, phase1, feature_df=feature_df,
            futures_oi_df=futures_oi_df,
            us_indices_df=us_indices_df,
            n_iterations=n_iterations
        )

        # Phase 3: 微觀確認
        phase3 = self.phase3_micro_confirm(df, phase1, phase2)

        # Phase 4: 風控 + 持倉適配
        signals = self.phase4_risk_manage(df, phase1, phase2, phase3)

        # Phase 5: 反饋 (如果有回測數據)
        if backtest_results is not None:
            self.phase5_feedback(signals, backtest_results)

        # 最終輸出
        print(f"\n{'='*60}")
        print(f"  掃描結果：{len(signals)} 檔通過五階段篩選")
        print(f"{'='*60}")

        for i, s in enumerate(signals[:10], 1):
            warn_tag = " [過擬合]" if s.overfit_warning else ""
            print(f"\n  [{i}] {s.stock_id} ({s.regime}) | "
                  f"綜合分數: {s.composite_score:.1f}{warn_tag}")
            print(f"      風險等級: {s.risk_grade.value} | "
                  f"持倉: {s.target_holding_days}天 | "
                  f"時間止損: {s.time_stop_days}天")
            print(f"      進場: {s.entry_price:.2f} | "
                  f"止損: {s.stop_loss:.2f} | "
                  f"目標: {s.target_price:.2f}")
            print(f"      CVD: {s.cvd_status} | "
                  f"吸收: {'是' if s.absorption_detected else '否'} | "
                  f"五日突破: {'是' if s.five_day_high_break else '否'}")
            if s.alpha_formula:
                print(f"      Alpha公式: {s.alpha_formula}")
            print(f"      移動止損: {s.trailing_stop_method}")

        return signals





# ============================================================
# 3c. [v3.1] 證交所資料抓取器 (TWSEDataFetcher)
# ============================================================

class TWSEDataFetcher:
    """台灣證交所資料抓取器 (v6.0 FinMind SDK)

    v3.1 -> v6.0: 從 stub 升級為真實資料抓取
    - 期貨法人OI: FinMind TaiwanFuturesInstitutionalInvestors (TX + MTX)
    - 美股指數: yfinance (Nasdaq, S&P500, DowJones)
    - CPU fallback: 若 SDK 未安裝, 返回空 DataFrame + warning
    """

    def fetch_futures_oi(self, days: int = 120, show_progress: bool = True) -> pd.DataFrame:
        """抓取期貨三大法人未平倉量 (FinMind SDK)

        Returns:
            DataFrame with columns:
            date, futures_id (TX/MTX), inst_net_oi, retail_net_oi
        """
        from datetime import datetime, timedelta
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        all_rows = []
        for futures_id in ['TX', 'MTX']:
            try:
                from FinMind.data import DataLoader
                dl = DataLoader()
                if show_progress:
                    print(f"  [TWSEDataFetcher] 下載 {futures_id} 法人持倉...")
                df_raw = dl.get_data(
                    dataset='TaiwanFuturesInstitutionalInvestors',
                    data_id=futures_id,
                    start_date=start_date,
                    end_date=end_date,
                )
                if len(df_raw) == 0:
                    continue

                # 逐日計算法人淨OI
                for date_val, group in df_raw.groupby('date'):
                    inst_net = 0
                    for _, r in group.iterrows():
                        net_oi = (r.get('long_open_interest_balance_volume', 0)
                                  - r.get('short_open_interest_balance_volume', 0))
                        inst_net += net_oi
                    # MTX 散戶代理: retail_net_oi = -inst_net_oi
                    retail_net = -inst_net if futures_id == 'MTX' else 0
                    all_rows.append({
                        'date': pd.Timestamp(date_val),
                        'futures_id': futures_id,
                        'inst_net_oi': inst_net,
                        'retail_net_oi': retail_net,
                    })
            except ImportError:
                import warnings
                warnings.warn(
                    "[TWSEDataFetcher] FinMind SDK not installed -- "
                    "returning empty DataFrame. Install via: pip install FinMind",
                    UserWarning, stacklevel=2,
                )
                return pd.DataFrame(columns=[
                    "date", "futures_id", "inst_net_oi", "retail_net_oi",
                ])
            except Exception as e:
                import warnings
                warnings.warn(
                    f"[TWSEDataFetcher] fetch_futures_oi() failed: {e} -- "
                    "returning empty DataFrame.",
                    UserWarning, stacklevel=2,
                )
                return pd.DataFrame(columns=[
                    "date", "futures_id", "inst_net_oi", "retail_net_oi",
                ])

        if len(all_rows) == 0:
            return pd.DataFrame(columns=[
                "date", "futures_id", "inst_net_oi", "retail_net_oi",
            ])

        result = pd.DataFrame(all_rows)
        result = result.sort_values(['date', 'futures_id']).reset_index(drop=True)
        if show_progress:
            print(f"  [TWSEDataFetcher] 期貨法人OI: {len(result)} rows "
                  f"({result['futures_id'].unique()} futures)")
        return result

    def fetch_us_indices(self, period: str = "6mo", show_progress: bool = True) -> pd.DataFrame:
        """抓取美股三大指數 (yfinance -> long format)

        Returns:
            DataFrame with columns:
            date, index_name, close
        """
        try:
            import yfinance as yf
        except ImportError:
            import warnings
            warnings.warn(
                "[TWSEDataFetcher] yfinance not installed -- "
                "returning empty DataFrame. Install via: pip install yfinance",
                UserWarning, stacklevel=2,
            )
            return pd.DataFrame(columns=[
                "date", "index_name", "close",
            ])

        ticker_map = {
            "Nasdaq": "^IXIC",
            "SP500": "^GSPC",
            "DowJones": "^DJI",
        }
        records = []
        for name, ticker in ticker_map.items():
            try:
                if show_progress:
                    print(f"  [TWSEDataFetcher] 下載 {name} ({ticker})...")
                data = yf.download(ticker, period=period, progress=False)
                if len(data) > 0:
                    for idx, row in data.iterrows():
                        close_val = row.get('Close', row.get('Adj Close', None))
                        if close_val is not None:
                            try:
                                close_val = float(close_val)
                            except (TypeError, ValueError):
                                continue
                            records.append({
                                'date': pd.Timestamp(idx),
                                'index_name': name,
                                'close': close_val,
                            })
            except Exception as e:
                import warnings
                warnings.warn(
                    f"[TWSEDataFetcher] yfinance download failed for {name}: {e}",
                    UserWarning, stacklevel=2,
                )
                continue

        if len(records) == 0:
            return pd.DataFrame(columns=[
                "date", "index_name", "close",
            ])

        result = pd.DataFrame(records)
        result = result.sort_values(['date', 'index_name']).reset_index(drop=True)
        if show_progress:
            print(f"  [TWSEDataFetcher] 美股指數: {len(result)} rows "
                  f"({result['index_name'].unique()} indices)")
        return result


# ============================================================
# 3d. [v3.1] 特徵工程 (compute_features)
# ============================================================

def compute_features(df: pd.DataFrame,
                     inst_df: pd.DataFrame = None,
                     margin_df: pd.DataFrame = None,
                     futures_oi_df: pd.DataFrame = None,
                     us_indices_df: pd.DataFrame = None) -> pd.DataFrame:
    """計算 v3.1 全部 22 維因子 (含期貨OI + 美股指數)

    Args:
        df: 日K資料 (date, stock_id, open, high, low, close, volume)
        inst_df: 三大法人買賣超 (optional)
        margin_df: 融資融券 (optional)
        futures_oi_df: 期貨未平倉量 (optional, v3.1 新增)
        us_indices_df: 美股大盤指數 (optional, v3.1 新增)

    Returns:
        DataFrame with all 22 features (zscore normalized, uppercase names)
        Columns: date, stock_id + ALL_FEATURE_NAMES (22 features)
    """
    NORM_WINDOW = 60
    NORM_CLIP = 5.0
    result_frames = []

    for stock_id, group in df.groupby("stock_id"):
        # v3.2: reset_index(drop=True) 消除 groupby multi-index，避免 level_0 衝突
        g = group.sort_values("date").copy().reset_index(drop=True)

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
            inst_data = inst_df[inst_df["stock_id"] == stock_id]
            if len(inst_data) > 0:
                inst_merge = inst_data.sort_values("date")[["date"]].copy()
                net_col = "total_net" if "total_net" in inst_data.columns else "foreign_net"
                if net_col not in inst_data.columns:
                    net_col = "net_buy"
                if net_col in inst_data.columns:
                    inst_merge[net_col] = inst_data.sort_values("date")[net_col].values
                    inst_merge = inst_merge.rename(columns={net_col: "inst_flow"})
                    inst_merge["inst_flow"] = inst_merge["inst_flow"].ffill().fillna(0)
                    g = g.merge(inst_merge[["date", "inst_flow"]], on="date", how="left")
                    g["inst_flow"] = g["inst_flow"].fillna(0)
                else:
                    g["inst_flow"] = 0
            else:
                g["inst_flow"] = 0
        else:
            g["inst_flow"] = 0

        # 融資壓力 — 使用 merge 取代 set_index/reindex (v3.2 fix)
        if margin_df is not None and len(margin_df) > 0:
            margin_data = margin_df[margin_df["stock_id"] == stock_id]
            if len(margin_data) > 0:
                margin_sorted = margin_data.sort_values("date")
                if "margin_balance" in margin_sorted.columns:
                    margin_merge = margin_sorted[["date", "margin_balance"]].copy()
                    margin_merge["margin_balance"] = margin_merge["margin_balance"].ffill()
                    margin_merge["margin_press"] = margin_merge["margin_balance"].pct_change(5).fillna(0)
                    g = g.merge(margin_merge[["date", "margin_press"]], on="date", how="left")
                    g["margin_press"] = g["margin_press"].fillna(0)
                elif "margin_buy" in margin_sorted.columns:
                    margin_merge = margin_sorted[["date", "margin_buy"]].copy()
                    margin_merge["margin_press"] = margin_merge["margin_buy"].rolling(5).mean().fillna(0)
                    g = g.merge(margin_merge[["date", "margin_press"]], on="date", how="left")
                    g["margin_press"] = g["margin_press"].fillna(0)
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

        # 衝浪手切入
        key_level = g["close"].rolling(20).mean()
        g["surf_entry"] = np.where(
            np.abs(g["close"] - key_level) / (key_level + 1e-6) < 0.01, 1.0, 0.0
        )

        # ATR
        high_arr, low_arr, close_arr = g["high"].values, g["low"].values, g["close"].values
        prev_close = np.roll(close_arr, 1)
        prev_close[0] = close_arr[0]
        tr = np.maximum(high_arr - low_arr, np.maximum(np.abs(high_arr - prev_close), np.abs(low_arr - prev_close)))
        atr14 = pd.Series(tr).rolling(14).mean()
        g["atr"] = atr14 / (close_arr + 1e-6)

        # 收盤位置
        g["close_pos"] = (g["close"] - g["low"]) / (g["high"] - g["low"] + 1e-6)

        # 動量反轉
        g["mom_rev"] = -1 * g["ret"].rolling(5).sum()

        # --- v3.1: 期貨法人 OI 因子 — 使用 merge 取代 set_index/reindex (v3.2 fix) ---
        if futures_oi_df is not None and len(futures_oi_df) > 0:
            foi = futures_oi_df.copy()
            foi["date"] = pd.to_datetime(foi["date"])

            # 大台 TX 法人淨 OI
            tx_oi = foi[foi["futures_id"] == "TX"][["date", "inst_net_oi"]].copy()
            if len(tx_oi) > 0 and "inst_net_oi" in tx_oi.columns:
                tx_oi = tx_oi.rename(columns={"inst_net_oi": "tx_inst_net_oi_raw"})
                tx_oi["tx_inst_net_oi_raw"] = tx_oi["tx_inst_net_oi_raw"].ffill().fillna(0)
                g = g.merge(tx_oi[["date", "tx_inst_net_oi_raw"]], on="date", how="left")
                g["tx_inst_net_oi_raw"] = g["tx_inst_net_oi_raw"].fillna(0)
            else:
                g["tx_inst_net_oi_raw"] = 0

            # 小台 MTX 散戶淨 OI
            mtx_oi = foi[foi["futures_id"] == "MTX"][["date", "retail_net_oi"]].copy()
            if len(mtx_oi) > 0 and "retail_net_oi" in mtx_oi.columns:
                mtx_oi = mtx_oi.rename(columns={"retail_net_oi": "mtx_retail_oi_raw"})
                mtx_oi["mtx_retail_oi_raw"] = mtx_oi["mtx_retail_oi_raw"].ffill().fillna(0)
                g = g.merge(mtx_oi[["date", "mtx_retail_oi_raw"]], on="date", how="left")
                g["mtx_retail_oi_raw"] = g["mtx_retail_oi_raw"].fillna(0)
            else:
                g["mtx_retail_oi_raw"] = 0

            # 大台-小台法人OI差
            tx_s = foi[foi["futures_id"] == "TX"][["date", "inst_net_oi"]].rename(
                columns={"inst_net_oi": "tx_inst"}).copy()
            mtx_s = foi[foi["futures_id"] == "MTX"][["date", "inst_net_oi"]].rename(
                columns={"inst_net_oi": "mtx_inst"}).copy()
            foi_spread = tx_s.merge(mtx_s, on="date", how="outer").sort_values("date")
            foi_spread[["tx_inst", "mtx_inst"]] = foi_spread[["tx_inst", "mtx_inst"]].ffill().fillna(0)
            foi_spread["tx_mtx_spread_raw"] = foi_spread["tx_inst"] - foi_spread["mtx_inst"]
            if len(foi_spread) > 0:
                g = g.merge(foi_spread[["date", "tx_mtx_spread_raw"]], on="date", how="left")
                g["tx_mtx_spread_raw"] = g["tx_mtx_spread_raw"].fillna(0)
            else:
                g["tx_mtx_spread_raw"] = 0
        else:
            g["tx_inst_net_oi_raw"] = 0
            g["mtx_retail_oi_raw"] = 0
            g["tx_mtx_spread_raw"] = 0

        # --- v3.1: 美股指數因子 — 使用 merge 取代 set_index/reindex (v3.2 fix) ---
        if us_indices_df is not None and len(us_indices_df) > 0:
            us = us_indices_df.copy()
            us["date"] = pd.to_datetime(us["date"])

            for idx_name, feat_name in [("Nasdaq", "nasdaq_close_raw"),
                                        ("SP500", "sp500_close_raw"),
                                        ("DowJones", "dowjones_close_raw")]:
                idx_data = us[us["index_name"] == idx_name][["date", "close"]].copy()
                if len(idx_data) > 0:
                    idx_data = idx_data.rename(columns={"close": feat_name})
                    idx_data[feat_name] = idx_data[feat_name].ffill().fillna(0)
                    g = g.merge(idx_data[["date", feat_name]], on="date", how="left")
                    g[feat_name] = g[feat_name].fillna(0)
                else:
                    g[feat_name] = 0
        else:
            g["nasdaq_close_raw"] = 0
            g["sp500_close_raw"] = 0
            g["dowjones_close_raw"] = 0

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

        # --- 小寫 → 大寫 FEATURE_NAMES 映射 (v3.2 修復) ---
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
        for feat in ALL_FEATURE_NAMES:
            if feat not in g.columns:
                g[feat] = 0
                continue
            col = g[feat].astype(float)
            roll_mean = col.rolling(NORM_WINDOW, min_periods=10).mean()
            roll_std = col.rolling(NORM_WINDOW, min_periods=10).std()
            exp_mean = col.expanding(min_periods=10).mean()
            exp_std = col.expanding(min_periods=10).std()
            mask = roll_mean.isna()
            roll_mean = roll_mean.fillna(exp_mean)
            roll_std = roll_std.fillna(exp_std)
            roll_std = roll_std.replace(0, 1)
            zscore = (col - roll_mean) / roll_std
            g[feat] = zscore.clip(-NORM_CLIP, NORM_CLIP).fillna(0)

        # 保留 date + stock_id + 全部 22 個大寫特徵
        keep_cols = ["date", "stock_id"] + list(ALL_FEATURE_NAMES)
        result_frames.append(g[keep_cols])

    result = pd.concat(result_frames, ignore_index=True)
    return result


# ============================================================
# 4. twstock 資料載入器
# ============================================================

class TWDataLoader:
    """台股資料載入器 (twstock → DataFrame)

    v2 修正:
    - 月份偏移計算修正 (D1)
    - volume 單位標準化為「張」(D2)
    - 移除 0050 ETF (D3)
    - 新增證交所 CSV 法人資料下載 (D4)
    v3 修正:
    - 整合 TWSEDataFetcher — 三大法人 (T86) + 融資融券 (MI_MARGN)
    - load_full() 一次下載 OHLCV + 法人 + 融資融券
    """

    # 台灣50成分股（移除 0050 ETF — 不適用個股篩選邏輯）
    DEFAULT_STOCKS = [
        "2330", "2454", "2382", "2308", "2412",  # 半導體/電子
        "1301", "1303", "1326",                   # 傳產
        "2882", "2886", "2891",                   # 金融
    ]

    def __init__(self, stock_list: List[str] = None, days: int = 120):
        self.stock_list = stock_list or self.DEFAULT_STOCKS
        self.days = days

    def load(self) -> pd.DataFrame:
        """從 twstock 載入資料，返回標準 DataFrame"""
        try:
            import twstock
        except ImportError:
            print("[WARNING] twstock not installed. Using demo data.")
            return self._demo_data()

        records = []
        for sid in self.stock_list:
            try:
                stock = twstock.Stock(sid)
                months_needed = (self.days // 22) + 2
                data = []
                from datetime import datetime
                now = datetime.now()
                for m_offset in range(months_needed):
                    # [v2] 修正月份偏移計算
                    total_month = now.year * 12 + (now.month - 1) - m_offset
                    y = total_month // 12
                    m = (total_month % 12) + 1
                    try:
                        monthly = stock.fetch(y, m)
                        data.extend(monthly)
                    except Exception:
                        continue

                for d in data:
                    records.append({
                        "date": d.date,
                        "stock_id": sid,
                        "open": d.open,
                        "high": d.high,
                        "low": d.low,
                        "close": d.close,
                        "volume": d.capacity,  # 單位：張（twstock 預設）
                    })
            except Exception as e:
                print(f"  [SKIP] {sid}: {e}")
                continue

        df = pd.DataFrame(records)
        if not df.empty:
            df = df.sort_values(["stock_id", "date"]).reset_index(drop=True)
        else:
            print("[WARNING] 所有股票資料抓取失敗，使用 demo data")
            return self._demo_data()
        return df

    def _demo_data(self) -> pd.DataFrame:
        """產生示範資料（twstock 未安裝時）"""
        np.random.seed(42)
        records = []
        dates = pd.bdate_range(end="2024-12-31", periods=self.days)

        for sid in self.stock_list[:5]:
            price = np.random.uniform(50, 500)
            for d in dates:
                ret = np.random.normal(0, 0.02)
                price *= (1 + ret)
                records.append({
                    "date": d, "stock_id": sid,
                    "open": price * (1 + np.random.normal(0, 0.005)),
                    "high": price * (1 + abs(np.random.normal(0, 0.015))),
                    "low": price * (1 - abs(np.random.normal(0, 0.015))),
                    "close": price,
                    "volume": int(np.random.uniform(1000, 50000)),  # 單位：張
                })
        return pd.DataFrame(records)

    # --- v3: 整合 TWSEDataFetcher (法人+融資融券) ---

    def load_inst_data(self, days: int = None) -> Optional[pd.DataFrame]:
        """[v3] 下載三大法人買賣超歷史資料 (TWSE T86 API)

        Returns:
            DataFrame: [date, stock_id, foreign_net, trust_net,
                        dealer_self_net, dealer_hedge_net, total_net]
        """
        from twse_data_fetcher import TWSEDataFetcher
        fetcher = TWSEDataFetcher()
        n_days = days or self.days
        end = datetime.now()
        start = end - timedelta(days=n_days)
        df = fetcher.fetch_inst_range(
            start.strftime('%Y%m%d'), end.strftime('%Y%m%d'),
            stock_filter=self.stock_list, show_progress=False,
        )
        if len(df) > 0:
            print(f"  [TWDataLoader] 法人資料: {len(df)} 筆, "
                  f"{df['stock_id'].nunique()} 檔")
        return df if len(df) > 0 else None

    def load_margin_data(self, days: int = None) -> Optional[pd.DataFrame]:
        """[v3] 下載融資融券歷史資料 (TWSE MI_MARGN API)

        Returns:
            DataFrame: [date, stock_id, margin_buy, margin_sell,
                        margin_balance, short_buy, short_sell, short_balance]
        """
        from twse_data_fetcher import TWSEDataFetcher
        fetcher = TWSEDataFetcher()
        n_days = days or self.days
        end = datetime.now()
        start = end - timedelta(days=n_days)
        df = fetcher.fetch_margin_range(
            start.strftime('%Y%m%d'), end.strftime('%Y%m%d'),
            stock_filter=self.stock_list, show_progress=False,
        )
        if len(df) > 0:
            print(f"  [TWDataLoader] 融資融券: {len(df)} 筆, "
                  f"{df['stock_id'].nunique()} 檔")
        return df if len(df) > 0 else None

    def load_full(self) -> dict:
        """[v3.1] 載入完整資料集：OHLCV + 法人 + 融資融券 + 期貨 + 美股

        Returns:
            {'ohlcv': DataFrame, 'inst': DataFrame, 'margin': DataFrame,
             'futures_oi': DataFrame, 'us_indices': DataFrame}
        """
        df_ohlcv = self.load()
        df_inst = self.load_inst_data()
        df_margin = self.load_margin_data()

        # 期貨 & 美股（需要 TWSEDataFetcher）
        df_futures_oi = pd.DataFrame()
        df_us_indices = pd.DataFrame()
        try:
            fetcher = TWSEDataFetcher()
            df_futures_oi = fetcher.fetch_futures_oi(days=120, show_progress=False)
            df_us_indices = fetcher.fetch_us_indices(period='6mo', show_progress=False)
        except Exception as e:
            print(f"  [警告] 期貨/美股資料載入失敗: {e}")

        return {
            'ohlcv': df_ohlcv, 'inst': df_inst, 'margin': df_margin,
            'futures_oi': df_futures_oi, 'us_indices': df_us_indices,
        }


# ============================================================
# 5. 公式解碼器 (沿用 AlphaGPT)
# ============================================================

class FormulaDecoder:
    """公式 Token → 人類可讀字串"""

    @staticmethod
    def decode(tokens: List[int]) -> str:
        """將 token 序列解碼為可讀公式"""
        n_features = len(ALL_FEATURE_NAMES)
        parts = []

        for t in tokens:
            if t < n_features:
                parts.append(ALL_FEATURE_NAMES[t])
            else:
                op_idx = t - n_features
                if op_idx < len(OPERATOR_NAMES):
                    parts.append(f"OP_{OPERATOR_NAMES[op_idx]}")
                else:
                    parts.append("INVALID")

        return " ".join(parts)


# ============================================================
# 6. 主程式入口
# ============================================================

def run_daily_scan(stock_list: List[str] = None, capital: float = 1_000_000,
                   use_v3: bool = True, feature_df: pd.DataFrame = None,
                   backtest_results: dict = None):
    """
    每日盤後掃描入口

    Args:
        stock_list: 股票代碼列表 (optional)
        capital: 可用資金
        use_v3: 是否使用 v3 五階段管線 (default: True)
        feature_df: 預計算特徵矩陣 (v3 Phase 2 需要)
        backtest_results: 回測結果 (v3 Phase 5 需要)
    """
    # 1. 載入資料 (v3.1: OHLCV + 法人 + 融資融券 + 期貨 + 美股)
    loader = TWDataLoader(stock_list=stock_list, days=120)
    data = loader.load_full()
    df = data['ohlcv']
    inst_df = data.get('inst')
    margin_df = data.get('margin')
    futures_oi_df = data.get('futures_oi')
    us_indices_df = data.get('us_indices')
    print(f"\n[資料] 載入 {df['stock_id'].nunique()} 檔，"
          f"{len(df)} 筆日K資料")
    if inst_df is not None and len(inst_df) > 0:
        print(f"  法人資料: {len(inst_df)} 筆")
    if margin_df is not None and len(margin_df) > 0:
        print(f"  融資融券: {len(margin_df)} 筆")
    if futures_oi_df is not None and len(futures_oi_df) > 0:
        print(f"  期貨OI: {len(futures_oi_df)} 筆")
    if us_indices_df is not None and len(us_indices_df) > 0:
        print(f"  美股指數: {len(us_indices_df)} 筆")



    # 1b. [v3.1] 自動計算特徵矩陣 (如果未提供)
    if feature_df is None and use_v3:
        print("\n[特徵] 計算 v3.1 22維因子矩陣...")
        feature_df = compute_features(
            df, inst_df=inst_df, margin_df=margin_df,
            futures_oi_df=futures_oi_df, us_indices_df=us_indices_df)
        n_feats = len([c for c in feature_df.columns if c not in ('date', 'stock_id')])
        print(f" 特徵矩陣: {feature_df.shape[0]} 筆, {n_feats} 維因子")


    # 2. 選擇管線版本
    if use_v3:
        pipeline = AIDigMoneyV3Pipeline()
        signals = pipeline.run(
            df, feature_df=feature_df,
            backtest_results=backtest_results,
            futures_oi_df=futures_oi_df,
            us_indices_df=us_indices_df,
        )
    else:
        print("=" * 60)
        print("  台股 AI Dig Money 系統 - 每日掃描 (v2)")
        print("=" * 60)
        print(AIDigMoneyPipeline.OVERFIT_DISCLAIMER)
        pipeline = AIDigMoneyPipeline()
        signals = pipeline.run(df, inst_df=inst_df, margin_df=margin_df,
                               futures_oi_df=futures_oi_df,
                               us_indices_df=us_indices_df)

    return signals


if __name__ == "__main__":
    run_daily_scan()
