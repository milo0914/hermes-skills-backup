# -*- coding: utf-8 -*-
"""
AI Dig Money 實盤訊號機器人 v1.4 (Cron 版)
- 整合 TWFeatureEngineer、robust_normalize、StackVM (完全對齊 V7)
- 修正 LINE Messaging API (Notify API 已停用)
- 改為單次執行模式 (cron 負責定時觸發)
- Token 全部從環境變數讀取
- 支援 4 個 regime: mid_cap_tech, traditional, large_cap, financial
- 使用 FinMind REST API 抓取即時數據
- v1.1: 修正期貨籌碼 rename bug (oid→oi) 及取值方式對齊 V7
- v1.2: 修正 retail_net_oi = total_net_oi - inst_net_oi (對齊 V7 定義)
        更新 mid_cap_tech/traditional 公式 tokens (V8 訓練結果)
- v1.3: 修正 robust_normalize NaN 處理 bug — np.median 含 NaN 回傳 NaN，
        導致所有含 NaN 的特徵 Z-score 全部歸零。改用 np.nanmedian。
        修正 compute_features 中 NaN fillna 順序 — 先 fillna 再傳入
        robust_normalize，確保滾動窗口內無 NaN。
- v1.4: robust_normalize 升級為實盤防彈版:
        (1) len<window 回傳 np.zeros_like (非 return arr，防 NaN 洩漏 StackVM)
        (2) result 初始化為 np.zeros_like (非 np.copy(arr)，邏輯更乾淨)
        (3) 逐值檢查 np.isnan(arr[i]) 不依賴事後兜底
        (4) warmup 期逐值檢查 arr[i] NaN
        (5) np.errstate(all='ignore') 壓制 RuntimeWarning
        (6) 保留 n_valid >= max(window//2, 10) 嚴格門檻
"""

import os
import json
import time
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# ============================================================
# 0. 系統設定 (環境變數)
# ============================================================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_USER_ID = os.environ.get("LINE_USER_ID", "")

# 若有 best_strategy_per_regime.json 路徑可設定
BEST_STRATEGY_PATH = os.environ.get("BEST_STRATEGY_PATH", "/data/.hermes/skills/research/twstock-alpha-gpt/scripts/best_strategy_per_regime.json")

# ============================================================
# 1. 特徵與公式定義
# ============================================================
FEATURE_NAMES = (
    "RET", "LIQ_SCORE", "PRESSURE", "FOMO", "DEV", "LOG_VOL",
    "INST_FLOW", "MARGIN_PRESS", "FIVE_DAY_HIGH", "VOL_BREAKOUT",
    "CVD_PROXY", "ABSORPTION", "SURF_ENTRY", "ATR", "CLOSE_POS", "MOM_REV",
    "TX_INST_NET_OI", "MTX_RETAIL_OI", "TX_MTX_SPREAD",
    "NASDAQ_CLOSE", "SP500_CLOSE", "DOWJONES_CLOSE",
)
N_FEATURES = len(FEATURE_NAMES)

OPERATOR_NAMES = (
    "ADD", "SUB", "MUL", "DIV", "NEG", "ABS",
    "SIGN", "GATE", "OUTLIER", "EMA", "LAG", "MAX3",
)
OPERATOR_ARITY = (2, 2, 2, 2, 1, 1, 1, 3, 1, 1, 1, 1)
N_OPERATORS = len(OPERATOR_NAMES)
VOCAB_SIZE = N_FEATURES + N_OPERATORS

# 預設策略 (若找不到 JSON 檔)
DEFAULT_STRATEGIES = {
    "mid_cap_tech": {
        "stocks": ["2303", "2317", "2382", "2454", "3008", "3034", "3711"],
        "tokens": [16, 20, 13, 33, 28, 32, 28, 22, 12, 27, 22, 13, 22, 27, 22],  # V8 訓練公式
    },
    "traditional": {
        "stocks": ["1301", "1101", "2002"],
        "tokens": [16, 17, 17, 33, 31, 27, 31, 27, 24, 27, 10, 31, 33, 23, 22],  # V8 訓練公式
    },
    "large_cap": {
        "stocks": ["2330", "2308", "2412", "1303", "1326"],
        "tokens": [1],  # LIQ_SCORE
    },
    "financial": {
        "stocks": ["2882", "2886", "2891", "2881", "2884"],
        "tokens": [14],  # CLOSE_POS
    },
}

STOCK_NAME_MAP = {
    "2303": "聯電", "2317": "鴻海", "2382": "廣達", "2454": "聯發科",
    "3008": "大立光", "3034": "聯詠", "3711": "日月光投控",
    "1301": "台塑", "1101": "台泥", "2002": "中鋼",
    "2330": "台積電", "2308": "台達電", "2412": "中華電", "1303": "南亞", "1326": "台化",
    "2882": "國泰金", "2886": "兆豐金", "2891": "中信金", "2881": "富邦金", "2884": "玉山金",
}


# ============================================================
# 2. 載入策略 JSON
# ============================================================
def load_strategies():
    """從 best_strategy_per_regime.json 載入 AI 訓練出的公式"""
    strategies = dict(DEFAULT_STRATEGIES)  # deep copy would be better but this is fine
    
    try:
        if os.path.exists(BEST_STRATEGY_PATH):
            with open(BEST_STRATEGY_PATH, 'r') as f:
                data = json.load(f)
            
            # v6.x format: {"mid_cap_tech": {"best_formula": [...]}}
            # v7 format: {"regimes": {"mid_cap_tech": {"formula_tokens": [...]}}}
            regimes_data = data.get("regimes", data)
            
            for regime_name, regime_data in regimes_data.items():
                if regime_name in strategies:
                    # Prefer formula_tokens, fallback to best_formula
                    tokens = regime_data.get("formula_tokens", regime_data.get("best_formula", None))
                    if tokens and isinstance(tokens, list) and len(tokens) > 0:
                        strategies[regime_name]["tokens"] = tokens
                        val_ic = regime_data.get("val_ic", 0)
                        print(f"  [INFO] Regime {regime_name}: loaded {len(tokens)} tokens, val_ic={val_ic:.4f}")
    except Exception as e:
        print(f"  [WARN] 載入策略 JSON 失敗: {e}, 使用預設策略")
    
    return strategies


# ============================================================
# 3. robust_normalize (Z-score with MAD, window=60)
#    v1.4: 實盤防彈版 — 完美處理 NaN / 連續0 / 資料不足
# ============================================================
def robust_normalize(arr, window=60):
    """
    實盤防彈版 Z-score 正規化：
    1. 完美處理 NaN (忽略 NaN 計算中位數)
    2. 完美處理連續 0 (MAD=0 時輸出 0.0)
    3. 確保輸出絕對不會有 NaN 或 Inf
    4. 資料不足 window 時回傳全零 (防 NaN 洩漏到 StackVM)
    5. warmup 期逐值檢查 arr[i] NaN
    6. 保留 n_valid >= max(window//2, 10) 嚴格門檻
    """
    if arr is None or len(arr) < window:
        return np.zeros_like(arr, dtype=np.float64) if arr is not None else arr

    # 確保輸入為 float64 陣列
    arr = np.array(arr, dtype=np.float64)
    result = np.zeros_like(arr)

    # 處理第 60 天之後的滾動視窗
    for i in range(window, len(arr)):
        segment = arr[i - window:i]

        # 🚀 升級：使用 nanmedian，即使 segment 裡面有 NaN 也能正確算出中位數
        # 加上 RuntimeWarning 忽略，防止 segment 全是 NaN 時跳警告
        with np.errstate(all='ignore'):
            med = np.nanmedian(segment)
            # v1.4 保留：嚴格門檻 — 有效值太少時不計算
            valid_mask = ~np.isnan(segment)
            n_valid = valid_mask.sum()
            if n_valid < max(window // 2, 10):
                result[i] = 0.0
                continue
            valid_values = segment[valid_mask]
            mad = np.nanmedian(np.abs(valid_values - med))

        # 嚴格檢查：當前值不是 NaN，且 MAD 有效大於 1e-8 時才計算
        if not np.isnan(arr[i]) and not np.isnan(mad) and mad > 1e-8:
            result[i] = (arr[i] - med) / (1.4826 * mad)
        else:
            result[i] = 0.0  # 包含 NaN 或連續 0 的情況，給予中性訊號 0.0

    # 處理前 60 天的 Global 數值 (用前 60 天的整體分佈來填補)
    with np.errstate(all='ignore'):
        valid_mask = ~np.isnan(arr[:window])
        n_valid = valid_mask.sum()
        if n_valid >= max(window // 2, 10):
            global_med = np.nanmedian(arr[:window])
            valid_values = arr[:window][valid_mask]
            global_mad = np.nanmedian(np.abs(valid_values - global_med))
        else:
            global_med = np.nan
            global_mad = np.nan

    for i in range(window):
        if not np.isnan(arr[i]) and not np.isnan(global_mad) and global_mad > 1e-8:
            result[i] = (arr[i] - global_med) / (1.4826 * global_mad)
        else:
            result[i] = 0.0

    return result


# ============================================================
# 4. TWFeatureEngineer (從 v7 完整移植，逐行對齊)
#    v1.3: 修正 NaN 傳入 robust_normalize 的問題
# ============================================================
class TWFeatureEngineer:
    NORM_WINDOW = 60
    NORM_CLIP = 5.0

    @staticmethod
    def compute_features(df, inst_df=None, margin_df=None, futures_oi_df=None, us_indices_df=None):
        result_frames = []
        for stock_id, group in df.groupby("stock_id"):
            g = group.sort_values("date").copy().reset_index(drop=True)
            g["date"] = pd.to_datetime(g["date"])
            
            # 基礎特徵
            g["ret"] = np.log(g["close"] / (g["close"].shift(1) + 1e-6) + 1e-8)
            g["liq_score"] = g["volume"] / (g["volume"].rolling(20).mean() + 1e-6)
            g["pressure"] = np.tanh(3.0 * (g["close"] - g["open"]) / (g["high"] - g["low"] + 1e-6))
            vol_chg = g["volume"].pct_change()
            g["fomo"] = vol_chg - vol_chg.shift(1)
            ma20 = g["close"].rolling(20).mean()
            g["dev"] = (g["close"] - ma20) / (ma20 + 1e-6)
            g["log_vol"] = np.log1p(g["volume"].clip(lower=0))
            
            # 法人買賣超
            if inst_df is not None and len(inst_df) > 0:
                _inst_merge = inst_df[inst_df["stock_id"] == stock_id][["date", "total_net"]].copy()
                if len(_inst_merge) > 0:
                    _inst_merge["date"] = pd.to_datetime(_inst_merge["date"])
                    _inst_merge = _inst_merge.rename(columns={"total_net": "inst_flow_raw"})
                    g = g.merge(_inst_merge[["date", "inst_flow_raw"]], on="date", how="left")
                    g["inst_flow"] = g["inst_flow_raw"].fillna(0)
                    g.drop(columns=["inst_flow_raw"], inplace=True)
                else:
                    g["inst_flow"] = 0.0
            else:
                g["inst_flow"] = 0.0
            
            # 融資融券
            if margin_df is not None and len(margin_df) > 0:
                _mg_merge = margin_df[margin_df["stock_id"] == stock_id][["date", "margin_balance", "margin_change", "short_balance"]].copy()
                if len(_mg_merge) > 0:
                    _mg_merge["date"] = pd.to_datetime(_mg_merge["date"])
                    _mg_merge["margin_press_raw"] = _mg_merge["margin_change"].fillna(0) / (_mg_merge["margin_balance"].fillna(1) + 1e-6)
                    g = g.merge(_mg_merge[["date", "margin_press_raw"]], on="date", how="left")
                    g["margin_press"] = g["margin_press_raw"].fillna(0)
                    g.drop(columns=["margin_press_raw"], inplace=True)
                else:
                    g["margin_press"] = 0.0
            else:
                g["margin_press"] = 0.0
            
            # 進階特徵
            high5 = g["close"].rolling(5).max()
            g["five_day_high"] = (g["close"] - high5) / (high5 + 1e-6)
            vol_ma5 = g["volume"].rolling(5).mean()
            g["vol_breakout"] = g["volume"] / (vol_ma5 + 1e-6)
            cvd_intraday = (g["close"] - g["open"]) / (g["high"] - g["low"] + 1e-6) * g["volume"]
            g["cvd_proxy"] = cvd_intraday.rolling(20).sum() / (g["volume"].rolling(20).mean() * 20 + 1e-6)
            g["absorption"] = (g["high"] - g["close"]) / (g["high"] - g["low"] + 1e-6) * g["volume"]
            
            # 期貨籌碼 (v1.2: retail_net_oi = total_net_oi - inst_net_oi 對齊 V7)
            if futures_oi_df is not None and len(futures_oi_df) > 0:
                foi = futures_oi_df.copy()
                foi["date"] = pd.to_datetime(foi["date"])
                tx_oi = foi[foi["futures_id"] == "TX"][["date", "inst_net_oi", "retail_net_oi"]].copy()
                tx_oi = tx_oi.rename(columns={"inst_net_oi": "tx_inst_net_oi", "retail_net_oi": "tx_retail_net_oi"})
                mtx_oi = foi[foi["futures_id"] == "MTX"][["date", "inst_net_oi", "retail_net_oi"]].copy()
                mtx_oi = mtx_oi.rename(columns={"inst_net_oi": "mtx_inst_net_oi", "retail_net_oi": "mtx_retail_net_oi"})
                g = g.merge(tx_oi, on="date", how="left")
                g = g.merge(mtx_oi, on="date", how="left")
                g["TX_INST_NET_OI"] = g["tx_inst_net_oi"].fillna(0)
                g["MTX_RETAIL_OI"] = g["mtx_retail_net_oi"].fillna(0)
                g["TX_MTX_SPREAD"] = (g["tx_inst_net_oi"].fillna(0) - g["mtx_inst_net_oi"].fillna(0))
                for c in ["tx_inst_net_oi", "tx_retail_net_oi", "mtx_inst_net_oi", "mtx_retail_net_oi"]:
                    if c in g.columns:
                        g.drop(columns=[c], inplace=True)
            else:
                for f in ["TX_INST_NET_OI", "MTX_RETAIL_OI", "TX_MTX_SPREAD"]:
                    g[f] = 0.0
            
            # 美股指數
            if us_indices_df is not None and len(us_indices_df) > 0:
                us = us_indices_df.copy()
                us["date"] = pd.to_datetime(us["date"])
                for idx_name, feat_name in [("Nasdaq", "NASDAQ_CLOSE"), ("SP500", "SP500_CLOSE"), ("DowJones", "DOWJONES_CLOSE")]:
                    idx_data = us[us["index_name"] == idx_name][["date", "close"]].copy()
                    idx_data = idx_data.rename(columns={"close": feat_name})
                    g = g.merge(idx_data, on="date", how="left")
                    g[feat_name] = g[feat_name].fillna(0).shift(1).fillna(0)
            else:
                for f in ["NASDAQ_CLOSE", "SP500_CLOSE", "DOWJONES_CLOSE"]:
                    g[f] = 0.0
            
            # 更多特徵
            key_level = g["close"].rolling(20).mean()
            g["surf_entry"] = np.where(np.abs(g["close"] - key_level) / (key_level + 1e-6) < 0.01, 1.0, 0.0)
            high_arr, low_arr, close_arr = g["high"].values, g["low"].values, g["close"].values
            prev_close = np.roll(close_arr, 1)
            prev_close[0] = close_arr[0]
            tr = np.maximum(high_arr - low_arr, np.maximum(np.abs(high_arr - prev_close), np.abs(low_arr - prev_close)))
            g["atr"] = pd.Series(tr).rolling(14).mean() / (close_arr + 1e-6)
            g["close_pos"] = (g["close"] - g["low"]) / (g["high"] - g["low"] + 1e-6)
            g["mom_rev"] = -1 * g["ret"].rolling(5).sum()
            
            # 統一命名
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
            
            # v1.3 修正：在傳入 robust_normalize 之前，先將 NaN 填為 0
            # 這是因為許多特徵在 warmup 期會產生 NaN（如 rolling(20) 前 19 筆、rolling(14) 前 13 筆等）
            # 舊版直接將含 NaN 的 array 傳給 robust_normalize，導致 np.median 回傳 NaN → Z-score 全歸零
            # 正確做法：先 fillna(0)，讓 robust_normalize 用 nanmedian 計算時也不受影響
            for feat in FEATURE_NAMES:
                if feat not in g.columns:
                    g[feat] = 0.0
                    continue
                # v1.3: 先 fillna(0)，確保 robust_normalize 收到的是純數值陣列
                raw_values = g[feat].fillna(0).values
                g[feat] = robust_normalize(raw_values, window=TWFeatureEngineer.NORM_WINDOW)
                g[feat] = g[feat].clip(-TWFeatureEngineer.NORM_CLIP, TWFeatureEngineer.NORM_CLIP)
            
            keep_cols = ["date", "stock_id", "close"] + list(FEATURE_NAMES)
            result_frames.append(g[keep_cols].copy())
        
        return pd.concat(result_frames, ignore_index=True) if result_frames else pd.DataFrame()


# ============================================================
# 5. StackVM 虛擬機 (從 v7 整合)
# ============================================================
class StackVM:
    @staticmethod
    def _safe_math(arr):
        return np.nan_to_num(np.clip(arr, -1e4, 1e4), nan=0.0, posinf=1e4, neginf=-1e4)

    def execute(self, tokens, feat_tensor):
        stack = []
        for t in tokens:
            if t < len(FEATURE_NAMES):
                stack.append(feat_tensor[t].copy())
            else:
                op_idx = t - len(FEATURE_NAMES)
                if len(stack) < [2, 2, 2, 2, 1, 1, 1, 3, 1, 1, 1, 1][op_idx]:
                    return None
                if op_idx in [4, 5, 6, 8, 9, 10, 11]:  # Unary
                    a = stack.pop()
                    if op_idx == 4: res = -a
                    elif op_idx == 5: res = np.abs(a)
                    elif op_idx == 6: res = np.sign(a)
                    elif op_idx == 8: res = np.where(np.abs((a - np.mean(a)) / (np.std(a) + 1e-6)) > 3, np.sign(a), 0)
                    elif op_idx == 9: res = 0.8 * a + 0.6 * np.roll(a, 1)
                    elif op_idx == 10: res = np.roll(a, 1)
                    elif op_idx == 11: res = np.maximum(np.maximum(a, np.roll(a, 1)), np.roll(a, 2))
                    stack.append(self._safe_math(res))
                elif op_idx in [0, 1, 2, 3]:  # Binary
                    b, a = stack.pop(), stack.pop()
                    if op_idx == 0: res = a + b
                    elif op_idx == 1: res = a - b
                    elif op_idx == 2: res = a * b
                    elif op_idx == 3: res = a / np.where(np.abs(b) < 1e-5, 1e-5, b)
                    stack.append(self._safe_math(res))
                elif op_idx == 7:  # Ternary (GATE)
                    c, b, a = stack.pop(), stack.pop(), stack.pop()
                    stack.append(self._safe_math(np.where(c > 0, a, b)))
        return stack[0] if len(stack) == 1 else None


# ============================================================
# 6. LINE Messaging API 推播
# ============================================================
def send_line_message(message, max_retries=3, base_delay=5):
    """使用 LINE Messaging API 發送推播訊息（含 429 重試機制）"""
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print(f"[本地印出]\n{message}")
        return
    
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    
    # LINE 文字訊息上限 5000 字
    if len(message) > 4500:
        message = message[:4497] + "..."
    
    data = {
        "to": LINE_USER_ID,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=headers, json=data, timeout=10)
            if resp.status_code == 200:
                print("LINE 訊息發送成功！")
                return
            elif resp.status_code == 429:
                wait_time = base_delay * (2 ** attempt)  # 指數背離：5s, 10s, 20s
                print(f"LINE 速率限制 (429)，等待 {wait_time} 秒後重試 (attempt {attempt+1}/{max_retries})")
                time.sleep(wait_time)
            else:
                print(f"LINE 發送失敗：狀態碼 {resp.status_code}, 錯誤：{resp.text[:200]}")
                return
        except Exception as e:
            print(f"LINE 發送發生例外：{e}")
            if attempt < max_retries - 1:
                wait_time = base_delay * (2 ** attempt)
                print(f"等待 {wait_time} 秒後重試...")
                time.sleep(wait_time)
            else:
                raise
    
    print(f"LINE 發送失敗：已達到最大重試次數 {max_retries}")


# ============================================================
# 7. FinMind API 資料抓取
# ============================================================
def fetch_finmind_data(dataset, data_id, start_date):
    """使用 FinMind REST API 抓取資料"""
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": dataset, "data_id": data_id, "start_date": start_date}
    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        if data.get("msg") == "success":
            return pd.DataFrame(data.get("data", []))
    except Exception as e:
        print(f"  抓取 {dataset}/{data_id} 失敗: {e}")
    return pd.DataFrame()


def get_live_features(stock_list):
    """抓取過去 120 天資料，計算 Z-score 正規化特徵"""
    # 使用 120 天以確保 robust_normalize(window=60) 有足夠的 warmup 期
    start_date = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")
    
    # 1. 抓取 OHLCV
    df_list = []
    for stock_id in stock_list:
        raw = fetch_finmind_data("TaiwanStockPrice", stock_id, start_date)
        if not raw.empty:
            raw = raw.rename(columns={"Trading_Volume": "volume", "max": "high", "min": "low"})
            raw["stock_id"] = stock_id
            df_list.append(raw)
    if not df_list:
        return None
    df = pd.concat(df_list, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    print(f"  抓取到 {len(df)} 筆 OHLCV 資料, {df['stock_id'].nunique()} 檔股票")
    
    # 2. 抓取期貨籌碼 (v1.2: retail_net_oi = total_net_oi - inst_net_oi 對齊 V7)
    tx_raw = fetch_finmind_data("TaiwanFuturesInstitutionalInvestors", "TX", start_date)
    mtx_raw = fetch_finmind_data("TaiwanFuturesInstitutionalInvestors", "MTX", start_date)
    
    futures_records = []
    for raw, f_id in [(tx_raw, "TX"), (mtx_raw, "MTX")]:
        if not raw.empty:
            # FinMind API v4: institutional_investors 欄位
            # V7 定義: retail_net_oi = total_net_oi - inst_net_oi
            # 其中 total_net_oi = sum of ALL investors' (long-short)
            # inst_net_oi = 外資 (long-short)
            if "institutional_investors" in raw.columns:
                # 計算每個日期所有投資者的 total_net_oi
                raw["net_oi"] = raw.get("long_open_interest_balance_volume", raw.get("long_oi", 0)).fillna(0) - \
                                raw.get("short_open_interest_balance_volume", raw.get("short_oi", 0)).fillna(0)
                total_oi_per_date = raw.groupby("date")["net_oi"].sum().reset_index()
                total_oi_per_date = total_oi_per_date.rename(columns={"net_oi": "total_net_oi"})
                
                # 篩選外資的 inst_net_oi
                if "long_open_interest_balance_volume" in raw.columns and "short_open_interest_balance_volume" in raw.columns:
                    foreign = raw[raw["institutional_investors"] == "外資"].copy()
                    foreign["inst_net_oi"] = foreign["long_open_interest_balance_volume"].fillna(0) - foreign["short_open_interest_balance_volume"].fillna(0)
                elif "long_oi" in raw.columns and "short_oi" in raw.columns:
                    foreign = raw[raw["institutional_investors"] == "外資"].copy()
                    foreign["inst_net_oi"] = foreign["long_oi"].fillna(0) - foreign["short_oi"].fillna(0)
                else:
                    foreign = raw[raw["institutional_investors"] == "外資"].copy()
                    foreign["inst_net_oi"] = 0
                
                # 合併 total + inst，計算 retail_net_oi = total - inst
                foreign = foreign[["date", "inst_net_oi"]].copy()
                foreign = foreign.merge(total_oi_per_date, on="date", how="left")
                foreign["total_net_oi"] = foreign["total_net_oi"].fillna(0)
                foreign["retail_net_oi"] = foreign["total_net_oi"] - foreign["inst_net_oi"]
                foreign["futures_id"] = f_id
                futures_records.append(foreign[["date", "futures_id", "inst_net_oi", "retail_net_oi"]])
                
            elif "name" in raw.columns:
                # 舊格式 fallback
                foreign = raw[raw["name"] == "外資及陸資"].copy()
                foreign["futures_id"] = f_id
                if "long_open_interest_balance_volume" in foreign.columns and "short_open_interest_balance_volume" in foreign.columns:
                    foreign["inst_net_oi"] = foreign["long_open_interest_balance_volume"].fillna(0) - foreign["short_open_interest_balance_volume"].fillna(0)
                elif "long_oi" in foreign.columns and "short_oi" in foreign.columns:
                    foreign["inst_net_oi"] = foreign["long_oi"].fillna(0) - foreign["short_oi"].fillna(0)
                else:
                    foreign["inst_net_oi"] = 0
                # 舊格式無法計算 total，退回 -inst_net_oi
                foreign["retail_net_oi"] = foreign["total_net_oi"] - foreign["inst_net_oi"] if "total_net_oi" in foreign.columns else -foreign["inst_net_oi"]
                futures_records.append(foreign[["date", "futures_id", "inst_net_oi", "retail_net_oi"]])
            else:
                # 無法識別投資者類型
                raw["futures_id"] = f_id
                raw["inst_net_oi"] = 0
                raw["retail_net_oi"] = 0
                futures_records.append(raw[["date", "futures_id", "inst_net_oi", "retail_net_oi"]].drop_duplicates(subset=["date"]))
    futures_oi_df = pd.concat(futures_records) if futures_records else None
    
    # 3. 抓取美股指數 (改用 FinMind 的 USStockPrice 或似指數資料集)
    us_records = []
    for idx_id, idx_name in [("^DJI", "DowJones"), ("^GSPC", "SP500"), ("^IXIC", "Nasdaq")]:
        raw = fetch_finmind_data("USStockPrice", idx_id, start_date)
        if not raw.empty and "Close" in raw.columns:
            raw["index_name"] = idx_name
            raw["close"] = raw["Close"]
            us_records.append(raw[["date", "index_name", "close"]])
    us_indices_df = pd.concat(us_records) if us_records else None
    
    # 4. 特徵工程
    feat_df = TWFeatureEngineer.compute_features(df, None, None, futures_oi_df, us_indices_df)
    return feat_df


# ============================================================
# 8. 解碼公式為人類可讀
# ============================================================
def decode_formula(tokens):
    """將 formula tokens 解碼為人類可讀的字串"""
    stack_str = []
    for t in tokens:
        if t < len(FEATURE_NAMES):
            stack_str.append(FEATURE_NAMES[t])
        else:
            op_idx = t - len(FEATURE_NAMES)
            op_name = OPERATOR_NAMES[op_idx] if op_idx < len(OPERATOR_NAMES) else f"OP{op_idx}"
            if op_idx in [0, 1, 2, 3]:  # Binary
                if len(stack_str) >= 2:
                    b, a = stack_str.pop(), stack_str.pop()
                    stack_str.append(f"({a} {op_name} {b})")
                else:
                    stack_str.append(f"[ERR:{op_name}]")
            elif op_idx == 7:  # Ternary
                if len(stack_str) >= 3:
                    c, b, a = stack_str.pop(), stack_str.pop(), stack_str.pop()
                    stack_str.append(f"GATE({c}>0?{a}:{b})")
                else:
                    stack_str.append(f"[ERR:GATE]")
            else:  # Unary
                if len(stack_str) >= 1:
                    a = stack_str.pop()
                    stack_str.append(f"{op_name}({a})")
                else:
                    stack_str.append(f"[ERR:{op_name}]")
    return stack_str[0] if len(stack_str) == 1 else str(stack_str)


# ============================================================
# 9. 主程式 (單次執行)
# ============================================================
def main():
    today_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    weekday = datetime.now().weekday()  # 0=Mon, 4=Fri
    
    # 檢查是否為週末，但允許透過環境變數 FORCE_RUN 強制執行
    force_run = os.environ.get("FORCE_RUN", "0") == "1"
    if weekday >= 5 and not force_run:
        print(f"[{today_str}] 今天是週末，不執行訊號計算（可設定 FORCE_RUN=1 強制執行）")
        return
    
    print(f"[{today_str}] === AI Dig Money 實盤訊號機器人啟動 ===")
    
    # 載入策略
    strategies = load_strategies()
    
    # 收集所有需要監控的股票
    all_stocks = []
    for regime, config in strategies.items():
        all_stocks.extend(config["stocks"])
    all_stocks = list(set(all_stocks))
    
    # 抓取資料並計算特徵
    print(f"  正在抓取 {len(all_stocks)} 檔股票的 120 天資料...")
    feat_df = get_live_features(all_stocks)
    
    if feat_df is None or feat_df.empty:
        error_msg = f"[{today_str}] AI Dig Money 錯誤: 無法抓取最新行情資料！"
        print(error_msg)
        send_line_message(error_msg)
        return
    
    vm = StackVM()
    msg_buffer = [f"== AI Dig Money 實盤訊號 ==\n{today_str}"]
    
    for regime, config in strategies.items():
        tokens = config["tokens"]
        regime_label = {"mid_cap_tech": "科技中光帽", "traditional": "傳統產業", "large_cap": "大型權值", "financial": "金融股"}.get(regime, regime)
        msg_buffer.append(f"\n-- {regime_label} --")
        formula_str = decode_formula(tokens)
        msg_buffer.append(f"公式: {formula_str}")
        
        for stock_id in config["stocks"]:
            stock_name = STOCK_NAME_MAP.get(stock_id, stock_id)
            stock_data = feat_df[feat_df["stock_id"] == stock_id].sort_values("date")
            if stock_data.empty:
                msg_buffer.append(f"  {stock_name}({stock_id}): 無資料")
                continue
            
            # 將特徵轉為 Tensor (Shape: [N_FEATURES, N_DAYS])
            feat_cols = [stock_data[f].values if f in stock_data.columns else np.zeros(len(stock_data)) for f in FEATURE_NAMES]
            feat_tensor = np.nan_to_num(np.array(feat_cols, dtype=np.float32), nan=0.0, posinf=5.0, neginf=-5.0)
            
            # 執行 AI 公式
            signal_array = vm.execute(tokens, feat_tensor)
            
            if signal_array is not None and len(signal_array) > 0:
                today_signal = float(np.tanh(signal_array[-1]))
                if today_signal > 0.3:
                    action = "看多"
                elif today_signal < -0.3:
                    action = "看空"
                else:
                    action = "觀望"
                
                emoji = "+" if today_signal > 0 else ""
                msg_buffer.append(f"  {stock_name}({stock_id}): {emoji}{today_signal:.2f} [{action}]")
            else:
                msg_buffer.append(f"  {stock_name}({stock_id}): 訊號計算失敗")
    
    # 加入免責聲明
    msg_buffer.append(f"\n-- 仅供参考，投资有风险 --")
    
    # 發送
    final_msg = "\n".join(msg_buffer)
    print(final_msg)
    send_line_message(final_msg)
    
    print(f"\n[{today_str}] === 實盤訊號計算完成 ===")


if __name__ == "__main__":
    main()
