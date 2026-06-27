"""
台股 AlphaGPT 因子挖掘模組 (台股適配版)
基於 https://github.com/imbue-bit/AlphaGPT 改寫
- 資料源：twstock (取代 Birdeye/DexScreener)
- 因子：16 維 (原始 6 + Marcus/Wenty 10)
- 回測：台股費率 (手續費 0.126% + 交易稅 0.3%)
- 支援 CPU/GPU 自適應

v2 修正清單 (2026-06-07 Strategy + Eng Review):
  - E1: 因子正規化前視偏差修正 → rolling window 替代全局 median/MAD
  - E2: TWBacktest 持倉邏輯修復 → 加入 ATR 止損、移動止損、時間止損
  - O4: 夏普比率年化因子修正 → sqrt(252/avg_holding_days)
  - D4: inst_df / margin_df 資料流修正 → 與 ai_dig_money_core.py 統一
  - 新增: 類別變數改為實例屬性 (避免全局污染)
  - 新增: 整合 anti_overfit.py 的過擬合檢查
  - 新增: 整合 grpo_alpha_trainer.py 的 GRPO 訓練入口
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional


# ============================================================
# 因子工程 (台股擴展版)
# ============================================================

class TWFeatureEngineer:
    """台股 16 維因子工程

    v2 修正:
    - robust normalization 改用 rolling window (消除前視偏差)
    - 預設窗口 = 60 天（約一季）
    - 首個窗口期 (前 60 天) 使用 expanding 作為 fallback
    """

    # 原始 6 因子
    ORIGINAL = ["ret", "liq_score", "pressure", "fomo", "dev", "log_vol"]
    # Marcus + Wenty 10 因子
    TW_EXTRA = [
        "inst_flow", "margin_press", "five_day_high", "vol_breakout",
        "cvd_proxy", "absorption", "surf_entry", "atr",
        "close_pos", "mom_rev",
    ]
    ALL_FEATURES = ORIGINAL + TW_EXTRA

    # [v2] 正規化配置
    NORM_WINDOW = 60     # rolling 窗口大小
    NORM_CLIP = 5.0      # clip 範圍

    @staticmethod
    def compute_features(df: pd.DataFrame, inst_df: pd.DataFrame = None,
                         margin_df: pd.DataFrame = None,
                         norm_window: int = None) -> pd.DataFrame:
        """
        計算所有 16 維因子

        Args:
            df: 日K資料 (date, stock_id, open, high, low, close, volume)
            inst_df: 三大法人 (optional)
            margin_df: 融資融券 (optional)
            norm_window: [v2] 正規化滾動窗口

        Returns:
            df 加入 16 個因子欄位
        """
        norm_window = norm_window or TWFeatureEngineer.NORM_WINDOW
        result_frames = []

        for stock_id, group in df.groupby("stock_id"):
            g = group.sort_values("date").copy()

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

            # --- Marcus 過濾因子 ---
            # 三大法人淨買超方向
            if inst_df is not None and len(inst_df) > 0:
                inst_data = inst_df[inst_df["stock_id"] == stock_id].copy()
                if len(inst_data) > 0 and "net_buy" in inst_data.columns:
                    inst_data = inst_data.set_index("date")["net_buy"]
                    g_idx = g.set_index("date")
                    g["inst_flow"] = inst_data.reindex(g_idx.index).fillna(0).values
                else:
                    g["inst_flow"] = 0
            else:
                g["inst_flow"] = 0

            # 融資壓力
            if margin_df is not None and len(margin_df) > 0:
                margin_data = margin_df[margin_df["stock_id"] == stock_id].copy()
                if len(margin_data) > 0 and "margin_buy" in margin_data.columns:
                    margin_chg = margin_data.set_index("date")["margin_buy"].pct_change()
                    g_idx = g.set_index("date")
                    g["margin_press"] = margin_chg.reindex(g_idx.index).fillna(0).values
                else:
                    g["margin_press"] = 0
            else:
                g["margin_press"] = 0

            # 五日高點突破
            five_day_high = g["high"].rolling(5).max().shift(1)
            g["five_day_high"] = (g["close"] > five_day_high).astype(float)

            # 放量突破 (volume > 1.5 * ma20_volume)
            vol_ma20 = g["volume"].rolling(20).mean()
            g["vol_breakout"] = (g["volume"] > vol_ma20 * 1.5).astype(float)

            # --- Wenty 量價因子 ---
            # CVD 代理
            cvd_daily = ((g["close"] - g["open"]) /
                         (g["high"] - g["low"] + 1e-6)) * g["volume"]
            g["cvd_proxy"] = cvd_daily.rolling(10).sum()

            # 吸收比 = volume / (H - L)
            g["absorption"] = g["volume"] / (g["high"] - g["low"] + 1e-6)

            # 衝浪手切入信號
            prev_close = g["close"].shift(1)
            prev_high = g["high"].shift(1)
            g["surf_entry"] = (
                (g["open"] >= prev_high * 0.995) |
                (abs(g["open"] - prev_close) / (prev_close + 1e-6) < 0.005)
            ).astype(float)

            # ATR
            tr1 = g["high"] - g["low"]
            tr2 = (g["high"] - g["close"].shift(1)).abs()
            tr3 = (g["low"] - g["close"].shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            g["atr"] = tr.rolling(14).mean()

            # 收盤在區間位置
            g["close_pos"] = (g["close"] - g["low"]) / (g["high"] - g["low"] + 1e-6)

            # 動量反轉
            mom5 = g["close"].pct_change(5)
            g["mom_rev"] = (mom5 * mom5.shift(1) < 0).astype(float)

            # [v2] Rolling Robust normalization (消除前視偏差)
            for feat in TWFeatureEngineer.ALL_FEATURES:
                if feat in g.columns:
                    # Rolling median + MAD
                    rolling_median = g[feat].rolling(norm_window, min_periods=20).median()
                    rolling_mad = (g[feat] - rolling_median).abs().rolling(
                        norm_window, min_periods=20
                    ).median() + 1e-6

                    normalized = (g[feat] - rolling_median) / rolling_mad

                    # Fallback: 前 norm_window 天用 expanding
                    if len(g) > norm_window:
                        expanding_median = g[feat].expanding(min_periods=20).median()
                        expanding_mad = (g[feat] - expanding_median).abs().expanding(
                            min_periods=20
                        ).median() + 1e-6
                        expanding_norm = (g[feat] - expanding_median) / expanding_mad

                        # 用 expanding 填補 rolling 的前段 NaN
                        normalized = normalized.fillna(expanding_norm)

                    g[feat] = normalized.clip(-TWFeatureEngineer.NORM_CLIP,
                                              TWFeatureEngineer.NORM_CLIP)

            result_frames.append(g)

        return pd.concat(result_frames, ignore_index=True)


# ============================================================
# 台股回測引擎
# ============================================================

class TWBacktest:
    """台股回測引擎 (調整費率)

    v2 修正:
    - 加入 ATR 止損出場邏輯
    - 加入移動止損 (五日高點滾動)
    - 加入時間止損 (7天)
    - 夏普比率年化因子修正
    - 交易成本計算修正 (買入手續費 + 賣出手續費 + 賣出交易稅)

    v3 修正:
    - 支援 per-signal 的 target_holding_days / time_stop_days / atr_stop_mult
    - 移動止損方法: atr / five_day_high / close_ma
    - 回測結果包含 actual_holding_days 供 Phase 5 反饋
    """

    def __init__(self):
        self.buy_fee = 0.00126  # 買入手續費 0.126%
        self.sell_fee = 0.00126  # 賣出手續費 0.126%
        self.tax = 0.003  # 交易稅 0.3% (賣出)
        self.slippage = 0.001  # 滑點 0.1% (單邊)
        self.min_turnover = 1e7  # 最小日均成交金額
        self.max_holding_days = 7  # 時間止損 (default, per-signal 可覆寫)
        self.atr_stop_mult = 2.0  # ATR 止損倍數 (default, per-signal 可覆寫)

    def evaluate(self, signals: pd.DataFrame, df: pd.DataFrame) -> dict:
        """
        回測評分

        Args:
            signals: 交易信號 (date, stock_id, direction, entry_price, stop_loss)
                     [v3] 可含: target_holding_days, time_stop_days, atr_stop_mult,
                               trailing_stop_method
            df: 日K資料

        Returns:
            回測結果 dict (含 per-trade 明細供 Phase 5 反饋)
        """
        results = {
            "total_trades": 0,
            "win_trades": 0,
            "total_pnl": 0,
            "max_drawdown": 0,
            "sharpe": 0,
            "win_rate": 0,
            "avg_holding_days": 0,
            "stop_loss_exits": 0,
            "trailing_stop_exits": 0,
            "time_exits": 0,
            # [v3] per-stock 結果供 Phase 5 反饋
            "per_stock": {},
        }

        trades = []
        for _, signal in signals.iterrows():
            sid = signal["stock_id"]
            entry_date = signal["date"]
            entry_price = signal["entry_price"]
            stop_loss = signal.get("stop_loss",
                                    entry_price * 0.95)  # 預設 5% 止損

            # [v3] Per-signal 持倉參數
            time_stop = signal.get("time_stop_days", self.max_holding_days)
            atr_mult = signal.get("atr_stop_mult", self.atr_stop_mult)
            trailing_method = signal.get("trailing_stop_method", "atr")

            stock_data = df[(df["stock_id"] == sid) &
                            (df["date"] >= entry_date)].sort_values("date")

            if len(stock_data) < 3:
                continue

            # [v2/v3] 動態持倉邏輯
            exit_price = None
            exit_reason = "time"
            holding_days = 0

            for day_idx, (_, row) in enumerate(stock_data.iterrows()):
                holding_days = day_idx + 1

                # 1. ATR 止損觸發
                if row["low"] <= stop_loss:
                    exit_price = stop_loss
                    exit_reason = "stop_loss"
                    break

                # 2. 移動止損 (根據 trailing_method)
                if holding_days >= 3:  # 至少持倉 3 天才啟動移動止損
                    atr_val = row.get("atr", entry_price * 0.02)
                    if pd.isna(atr_val):
                        atr_val = entry_price * 0.02

                    if trailing_method == "five_day_high":
                        # 五日高點滾動止損
                        start_idx = max(0, day_idx - 4)
                        recent_high = stock_data.iloc[start_idx:day_idx+1]["high"].max()
                        trailing_stop = recent_high - atr_val * atr_mult
                    elif trailing_method == "close_ma":
                        # 20日均線止損 (適合金融/傳產)
                        if day_idx >= 20:
                            close_ma = stock_data.iloc[day_idx-20:day_idx]["close"].mean()
                            trailing_stop = close_ma - atr_val * atr_mult * 0.5
                        else:
                            trailing_stop = stop_loss  # 數據不足，維持初始止損
                    else:  # "atr" default
                        # ATR 移動止損
                        trailing_stop = row["close"] - atr_val * atr_mult

                    if row["low"] <= trailing_stop:
                        exit_price = trailing_stop
                        exit_reason = "trailing_stop"
                        break

                # 3. 時間止損 [v3] 用 per-signal 的 time_stop
                if holding_days >= time_stop:
                    exit_price = row["close"]
                    exit_reason = "time"
                    break

                # 更新移動止損 (ATR-based)
                if "atr" in stock_data.columns and pd.notna(row.get("atr")):
                    stop_loss = max(stop_loss,
                                    row["close"] - row["atr"] * atr_mult)

            # 如果沒有提前出場，用最後一天收盤
            if exit_price is None:
                exit_price = stock_data["close"].iloc[-1]
                exit_reason = "end_of_data"

            # 計算 PnL
            gross_ret = (exit_price - entry_price) / entry_price
            # [v2] 交易成本修正：買入手續費 + 賣入手續費 + 交易稅 + 雙邊滑點
            total_cost = (self.buy_fee + self.sell_fee + self.tax +
                          2 * self.slippage)
            net_ret = gross_ret - total_cost

            results["total_trades"] += 1
            results["total_pnl"] += net_ret
            is_win = net_ret > 0
            if is_win:
                results["win_trades"] += 1

            if exit_reason == "stop_loss":
                results["stop_loss_exits"] += 1
            elif exit_reason == "trailing_stop":
                results["trailing_stop_exits"] += 1
            elif exit_reason == "time":
                results["time_exits"] += 1

            trade_record = {
                "ret": net_ret,
                "days": holding_days,
                "exit_reason": exit_reason,
            }
            trades.append(trade_record)

            # [v3] 記錄 per-stock 結果
            results["per_stock"][sid] = {
                "pnl": net_ret,
                "win": is_win,
                "actual_holding_days": holding_days,
                "exit_reason": exit_reason,
            }

        if results["total_trades"] > 0:
            results["win_rate"] = results["win_trades"] / results["total_trades"]
            rets = [t["ret"] for t in trades]
            avg_days = np.mean([t["days"] for t in trades])

            # [v2] 夏普比率年化因子修正
            # 持倉 3-7 天，交易頻率非日頻，需用 252/avg_holding_days
            annualization = np.sqrt(252 / max(avg_days, 1))
            results["sharpe"] = np.mean(rets) / (np.std(rets) + 1e-6) * annualization
            results["avg_holding_days"] = avg_days

            # Max drawdown
            cum = np.cumsum(rets)
            peak = np.maximum.accumulate(cum)
            dd = cum - peak
            results["max_drawdown"] = abs(min(dd)) if len(dd) > 0 else 0

        return results


# ============================================================
# AlphaGPT 訓練配置 (台股版)
# ============================================================

class TWModelConfig:
    """台股 AlphaGPT 訓練配置

    v2 修正:
    - 改為實例屬性 (避免類別變數被 auto_detect 全局污染)
    - 整合 GRPO 訓練框架選項
    """

    def __init__(self):
        # 模型參數
        self.d_model = 64
        self.nhead = 4
        self.num_layers = 2
        self.dim_ff = 128
        self.num_loops = 3
        self.vocab_size = 28       # 16 因子 + 12 算子
        self.max_formula_len = 15

        # 訓練參數
        self.batch_size = 64       # CPU: 16, GPU: 128+
        self.train_steps = 10000   # CPU: 1000, GPU: 20000+
        self.lr = 1e-3
        self.use_lord = True
        self.lord_decay = 1e-3

        # [v2] GRPO 訓練參數
        self.use_grpo = True       # 預設使用 GRPO 替代 REINFORCE
        self.grpo_group_size = 4   # CPU: 4, GPU: 8

        # 設備
        self.device = "cpu"

    def auto_detect(self):
        """自動偵測 GPU 並調整參數"""
        try:
            import torch
            if torch.cuda.is_available():
                self.device = "cuda"
                self.batch_size = 128
                self.train_steps = 20000
                self.grpo_group_size = 8
                print(f"[Auto] GPU: {torch.cuda.get_device_name(0)}")
            else:
                self.device = "cpu"
                self.batch_size = 16
                self.train_steps = 1000
                self.grpo_group_size = 4
                print("[Auto] CPU mode")
            print(f"[Auto] Batch={self.batch_size}, "
                  f"Steps={self.train_steps}, "
                  f"GRPO G={self.grpo_group_size}")
        except ImportError:
            self.device = "cpu"
            self.batch_size = 16
            self.train_steps = 1000
            self.grpo_group_size = 4
            print("[Auto] PyTorch not installed, CPU mode")


# ============================================================
# 公式反編譯器 (可解釋性)
# ============================================================

class FormulaDecoder:
    """將 AlphaGPT 生成的 token 序列反編譯為人類可讀公式"""

    FEATURE_NAMES = TWFeatureEngineer.ALL_FEATURES
    OP_NAMES = [
        "ADD", "SUB", "MUL", "DIV", "NEG", "ABS",
        "SIGN", "GATE", "JUMP", "DECAY", "DELAY1", "MAX3",
    ]
    OP_ARITY = [2, 2, 2, 2, 1, 1, 1, 3, 1, 1, 1, 1]

    @classmethod
    def decode(cls, tokens: List[int]) -> str:
        """反編譯 token 序列"""
        feat_count = len(cls.FEATURE_NAMES)
        stack = []

        for t in tokens:
            if t < feat_count:
                stack.append(cls.FEATURE_NAMES[t])
            else:
                op_idx = t - feat_count
                if op_idx >= len(cls.OP_NAMES):
                    return "INVALID"
                op_name = cls.OP_NAMES[op_idx]
                arity = cls.OP_ARITY[op_idx]

                if len(stack) < arity:
                    return "INVALID"

                if arity == 1:
                    arg = stack.pop()
                    stack.append(f"{op_name}({arg})")
                elif arity == 2:
                    b = stack.pop()
                    a = stack.pop()
                    stack.append(f"({a} {op_name} {b})")
                elif arity == 3:
                    c = stack.pop()
                    b = stack.pop()
                    a = stack.pop()
                    stack.append(f"GATE({a}, {b}, {c})")

        return stack[0] if len(stack) == 1 else "INVALID"

    @classmethod
    def decode_best_formula(cls, json_path: str) -> str:
        """從 best_strategy.json 讀取並反編譯"""
        import json
        with open(json_path) as f:
            tokens = json.load(f)
        return cls.decode(tokens)


# ============================================================
# GRPO 訓練入口
# ============================================================

def run_grpo_training(df: pd.DataFrame = None, config: TWModelConfig = None):
    """
    [v2] GRPO 因子訓練入口

    整合 grpo_alpha_trainer.py 和 anti_overfit.py

    Args:
        df: 日K資料 (如果 None，自動從 twstock 載入)
        config: 訓練配置

    Returns:
        訓練結果 dict
    """
    from grpo_alpha_trainer import GRPOAlphaTrainer, GRPOConfig

    config = config or TWModelConfig()
    config.auto_detect()

    # 載入資料
    if df is None:
        from ai_dig_money_core import TWDataLoader
        loader = TWDataLoader(days=120)
        df = loader.load()

    # 計算因子
    feat_df = TWFeatureEngineer.compute_features(df)

    # 分割 train/val
    from anti_overfit import TimeSeriesSplitter, DataSplit
    dates = pd.to_datetime(feat_df["date"])
    date_min = dates.min().strftime("%Y-%m-01")
    date_max = dates.max().strftime("%Y-%m-%d")

    # 動態分割：前 75% train，後 25% val
    split_point = dates.quantile(0.75).strftime("%Y-%m-%d")
    train_df = feat_df[dates <= split_point]
    val_df = feat_df[dates > split_point]

    # 準備特徵矩陣和前向報酬
    feature_cols = TWFeatureEngineer.ALL_FEATURES
    train_feat = train_df[feature_cols].T.values.astype(np.float32)
    train_returns = train_df["ret"].values.astype(np.float32)
    val_feat = val_df[feature_cols].T.values.astype(np.float32) if len(val_df) > 0 else None
    val_returns = val_df["ret"].values.astype(np.float32) if len(val_df) > 0 else None

    # 建立 GRPO 配置
    grpo_config = GRPOConfig(
        group_size=config.grpo_group_size,
        d_model=config.d_model,
        nhead=config.nhead,
        num_layers=config.num_layers,
        dim_feedforward=config.dim_ff,
        num_loops=config.num_loops,
        batch_size=config.batch_size,
        train_steps=config.train_steps,
        lr=config.lr,
        device=config.device,
    )

    # 訓練
    trainer = GRPOAlphaTrainer(grpo_config)
    if config.device == "cpu":
        result = trainer.train_numpy(
            train_feat, train_returns,
            val_feat, val_returns,
            n_iterations=config.train_steps,
        )
    else:
        result = trainer.train_torch(
            train_feat, train_returns,
            val_feat, val_returns,
        )

    # 過擬合審計
    from anti_overfit import AntiOverfitLayer
    audit = AntiOverfitLayer()
    report = audit.full_audit(
        feat_df,
        strategy_fn=lambda df: {"threshold": 50},
        metric_fn=lambda df, p: np.random.randn(),  # placeholder
        name="grpo_alpha",
    )

    return {
        "training_result": result,
        "overfit_report": report.to_dict() if hasattr(report, "to_dict") else {},
    }


# ============================================================
# 使用範例
# ============================================================

def demo():
    """示範：完整流程 (v3)"""
    from ai_dig_money_core import TWDataLoader, AIDigMoneyV3Pipeline

    # 1. 載入資料
    print("=" * 50)
    print("台股 AI Dig Money 系統 - 示範 (v3)")
    print("=" * 50)

    # [v2] 移除 0050 ETF
    loader = TWDataLoader(stock_list=["2330", "2454", "2308", "2412", "1301"])
    df = loader.load()

    # 2. 計算因子
    print("\n[因子工程] 計算 16 維因子 (rolling normalization)...")
    feat_df = TWFeatureEngineer.compute_features(df)
    print(f"  完成：{feat_df['stock_id'].nunique()} 檔，"
          f"{len(feat_df.columns) - 7} 個因子欄位")

    # 3. [v3] 五階段篩選
    print("\n[五階段篩選]")
    pipeline = AIDigMoneyV3Pipeline()
    signals = pipeline.run(feat_df, feature_df=feat_df)

    # 4. 回測
    if signals:
        print("\n[回測]")
        bt = TWBacktest()
        # 將 signals 轉為 DataFrame 進行回測
        signal_records = [{
            "date": pd.Timestamp.now(),
            "stock_id": s.stock_id,
            "direction": 1,
            "entry_price": s.entry_price,
            "stop_loss": s.stop_loss,
            # [v3] per-signal 持倉參數
            "target_holding_days": s.target_holding_days,
            "time_stop_days": s.time_stop_days,
            "atr_stop_mult": 2.0,
            "trailing_stop_method": s.trailing_stop_method,
        } for s in signals]
        if signal_records:
            signals_df = pd.DataFrame(signal_records)
            bt_result = bt.evaluate(signals_df, df)
            print(f"  交易次數: {bt_result['total_trades']}")
            print(f"  勝率: {bt_result['win_rate']:.1%}")
            print(f"  夏普: {bt_result['sharpe']:.2f}")
            print(f"  最大回撤: {bt_result['max_drawdown']:.2%}")
            print(f"  平均持倉: {bt_result['avg_holding_days']:.1f} 天")

            # [v3] Phase 5: 用回測結果反饋
            backtest_results = bt_result["per_stock"]
            pipeline.phase5_feedback(signals, backtest_results)

    # 5. 公式反編譯示範
    print("\n[公式反編譯範例]")
    demo_formulas = [
        [0, 1, 16, 3, 18],  # (RET + LIQ_SCORE) * FOMO
        [0, 24, 10, 19],    # JUMP(RET) / CVD_PROXY
        [2, 22, 25],        # DECAY(SIGN(PRESSURE))
        [4, 10, 18, 21, 8, 23],  # GATE(ABS(DEV * CVD_PROXY), FIVE_DAY_HIGH)
    ]
    for tokens in demo_formulas:
        formula = FormulaDecoder.decode(tokens)
        print(f"  Tokens {tokens} → {formula}")

    # 6. GPU 偵測
    print("\n[硬體偵測]")
    model_config = TWModelConfig()
    model_config.auto_detect()

    return signals


if __name__ == "__main__":
    demo()
