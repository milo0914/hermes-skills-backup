# -*- coding: utf-8 -*-
"""
TWStock Real Data Fetcher — 台股真實數據拉取模組
v4.4 / 2026-06-12
- 載入已有數據避免重複抓取 yfinance（反爬限制）
- FinMind API 直接使用 requests 呼叫，不透過 pip install（避免版本衝突）
"""

import time, numpy as np, pandas as pd, requests, json
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime, timedelta

DATA_DIR = Path("/kaggle/working/twstock_v6_data")
DATA_DIR.mkdir(parents=True, exist_ok=True)


class FinMindAPI:
    """FinMind REST API 包裝 — 不需安裝 FinMind 套件"""
    BASE = "https://api.finmindtrade.com/api/v4/data"

    @staticmethod
    def _fetch(dataset: str, params: dict) -> pd.DataFrame:
        params["dataset"] = dataset
        for attempt in range(3):
            try:
                resp = requests.get(FinMindAPI.BASE, params=params, timeout=30)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    if data:
                        return pd.DataFrame(data)
                    return pd.DataFrame()
                print(f"  FinMind API {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                print(f"  FinMind API error: {e}")
            time.sleep(2 ** attempt)
        return pd.DataFrame()

    @classmethod
    def taiwan_stock_institutional_investors(cls, stock_id: str, start_date: str) -> pd.DataFrame:
        return cls._fetch("TaiwanStockInstitutionalInvestorsBuySell", {
            "data_id": stock_id, "start_date": start_date
        })

    @classmethod
    def taiwan_stock_margin_purchase_short_sale(cls, stock_id: str, start_date: str) -> pd.DataFrame:
        return cls._fetch("TaiwanStockMarginPurchaseShortSale", {
            "data_id": stock_id, "start_date": start_date
        })

    @classmethod
    def taiwan_futures_institutional_investors(cls, futures_id: str, start_date: str) -> pd.DataFrame:
        return cls._fetch("TaiwanFuturesInstitutionalInvestors", {
            "data_id": futures_id, "start_date": start_date
        })

def _flatten_yf_columns(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df

def _parse_yf_date(series):
    dt = pd.to_datetime(series, utc=True)
    try:
        dt = dt.dt.tz_localize(None)
    except TypeError:
        pass
    return dt

class TWStockDataFetcher:
    TW_TICKERS = {
        "2330": "2330.TW", "2308": "2308.TW", "2412": "2412.TW", "2311": "2311.TW",
        "2454": "2454.TW", "2382": "2382.TW", "3008": "3008.TW", "3034": "3034.TW",
        "3711": "3711.TW", "2303": "2303.TW",
        "1301": "1301.TW", "1303": "1303.TW", "1326": "1326.TW", "1101": "1101.TW", "2002": "2002.TW",
        "2882": "2882.TW", "2886": "2886.TW", "2891": "2891.TW", "2884": "2884.TW", "2881": "2881.TW",
    }
    US_INDEX_TICKERS = {"Nasdaq": "^IXIC", "SP500": "^GSPC", "DowJones": "^DJI"}
    FUTURES_INST_MAP = {"外資": "Foreign_Investor", "投信": "Investment_Trust",
                        "自營商": "Dealer_self", "避險": "Dealer_Hedging"}

    def __init__(self, rate_limit_delay=3.0, max_retries=3):
        self.delay = rate_limit_delay
        self.max_retries = max_retries

    @property
    def finmind(self):
        """FinMind API wrapper (REST, no package needed)"""
        return FinMindAPI

    def _finmind_fetch(self, dataset: str, data_id: str, start_date: str) -> pd.DataFrame:
        """Helper to call FinMindAPI with consistent params."""
        return FinMindAPI._fetch(dataset, {"data_id": data_id, "start_date": start_date})

    def _yf_download_with_retry(self, ticker, period="2y", interval="1d"):
        import yfinance as yf
        for attempt in range(self.max_retries):
            try:
                time.sleep(self.delay)
                data = yf.download(ticker, period=period, interval=interval, progress=False)
                if len(data) > 0:
                    return data
            except Exception as e:
                if "Rate" in str(e) or "429" in str(e):
                    wait = self.delay * (attempt + 2)
                    print(f"  Rate limited, waiting {wait:.0f}s...")
                    time.sleep(wait)
                else:
                    print(f"  yf error: {e}")
        return pd.DataFrame()

    def fetch_ohlcv(self, stock_ids, period="2y"):
        """載入已有的 CSV 避免重複抓取"""
        csv_path = DATA_DIR / "price_ohlcv.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path, parse_dates=["date"])
            print(f"  [OHLCV] 載入已有數據: {len(df)} rows (from {csv_path})")
            return df
        # 無緩存才抓
        all_frames = []
        for sid in stock_ids:
            ticker = self.TW_TICKERS.get(sid, f"{sid}.TW")
            data = self._yf_download_with_retry(ticker, period)
            if len(data) > 0:
                data = _flatten_yf_columns(data)
                df = data.reset_index()
                col_map = {}
                for c in df.columns:
                    cl = c.lower().strip()
                    if cl in ("date", "price"):
                        col_map[c] = "date"
                    elif cl in ("open", "high", "low", "close", "volume"):
                        col_map[c] = cl
                df = df.rename(columns=col_map)
                if "date" not in df.columns:
                    df = df.rename(columns={df.columns[0]: "date"})
                df["date"] = _parse_yf_date(df["date"])
                df["stock_id"] = sid
                keep = ["date", "stock_id", "open", "high", "low", "close", "volume"]
                df = df[[c for c in keep if c in df.columns]]
                all_frames.append(df)
                print(f"  [OHLCV] {sid}: {len(df)} rows")
            else:
                print(f"  [OHLCV] {sid}: NO DATA")
        if not all_frames:
            return pd.DataFrame()
        return pd.concat(all_frames, ignore_index=True)

    def fetch_inst_flow(self, stock_ids, start_date="2021-01-01"):
        all_frames = []
        for sid in stock_ids:
            try:
                df = self._finmind_fetch("TaiwanStockInstitutionalInvestorsBuySell", sid, start_date)
                if len(df) > 0:
                    df["date"] = pd.to_datetime(df["date"])
                    df["net_buy"] = df["buy"] - df["sell"]
                    pivoted = df.pivot_table(index="date", columns="name", values="net_buy", aggfunc="sum").reset_index()
                    pivoted.columns.name = None
                    net_cols = [c for c in pivoted.columns if c != "date"]
                    pivoted["total_net"] = pivoted[net_cols].sum(axis=1)
                    pivoted["stock_id"] = sid
                    all_frames.append(pivoted)
                    print(f"  [Inst] {sid}: {len(pivoted)} rows")
            except Exception as e:
                print(f"  [Inst] {sid}: ERROR - {e}")
        if not all_frames:
            return pd.DataFrame()
        return pd.concat(all_frames, ignore_index=True)

    def fetch_margin(self, stock_ids, start_date="2021-01-01"):
        all_frames = []
        for sid in stock_ids:
            try:
                df = self._finmind_fetch("TaiwanStockMarginPurchaseShortSale", sid, start_date)
                if len(df) > 0:
                    df["date"] = pd.to_datetime(df["date"])
                    df["margin_balance"] = df["MarginPurchaseTodayBalance"]
                    df = df[["date", "stock_id", "margin_balance"]].copy()
                    all_frames.append(df)
                    print(f"  [Margin] {sid}: {len(df)} rows")
            except Exception as e:
                print(f"  [Margin] {sid}: ERROR - {e}")
        if not all_frames:
            return pd.DataFrame()
        return pd.concat(all_frames, ignore_index=True)

    def fetch_futures_oi(self, futures_ids=None, start_date="2021-01-01"):
        if futures_ids is None:
            futures_ids = ["TX", "MTX"]
        all_frames = []
        for fid in futures_ids:
            try:
                df = self._finmind_fetch("TaiwanFuturesInstitutionalInvestors", fid, start_date)
                if len(df) > 0:
                    df["date"] = pd.to_datetime(df["date"])
                    df["futures_id"] = fid
                    df["net_oi"] = df["long_open_interest_balance_volume"] - df["short_open_interest_balance_volume"]
                    all_frames.append(df)
                    print(f"  [FuturesOI] {fid}: {len(df)} raw rows")
            except Exception as e:
                print(f"  [FuturesOI] {fid}: ERROR - {e}")
        if not all_frames:
            return pd.DataFrame()
        raw = pd.concat(all_frames, ignore_index=True)
        agg_rows = []
        for (fid, date), grp in raw.groupby(["futures_id", "date"]):
            row = {"date": date, "futures_id": fid}
            for cn_name, en_name in self.FUTURES_INST_MAP.items():
                inst_grp = grp[grp["institutional_investors"] == cn_name]
                row[f"{en_name}_net_oi"] = inst_grp["net_oi"].iloc[0] if len(inst_grp) > 0 else 0
            total_inst = sum(row.get(f"{en}_net_oi", 0) for en in self.FUTURES_INST_MAP.values())
            if fid == "TX":
                row["inst_net_oi"] = row.get("Foreign_Investor_net_oi", 0)
                row["retail_net_oi"] = -total_inst
            if fid == "MTX":
                row["retail_net_oi"] = row.get("Dealer_self_net_oi", 0)
                row["inst_net_oi"] = -row["retail_net_oi"]
            agg_rows.append(row)
        result = pd.DataFrame(agg_rows)
        print(f"  [FuturesOI] aggregated: {len(result)} rows")
        return result

    def fetch_us_indices(self, period="2y"):
        """載入已有的 CSV 避免重複抓取"""
        csv_path = DATA_DIR / "us_indices.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path, parse_dates=["date"])
            print(f"  [US] 載入已有數據: {len(df)} rows (from {csv_path})")
            return df
        all_frames = []
        for name, ticker in self.US_INDEX_TICKERS.items():
            data = self._yf_download_with_retry(ticker, period)
            if len(data) > 0:
                data = _flatten_yf_columns(data)
                df = data.reset_index()
                col_map = {}
                for c in df.columns:
                    cl = c.lower().strip()
                    if cl in ("date", "price"):
                        col_map[c] = "date"
                    elif cl == "close":
                        col_map[c] = "close"
                df = df.rename(columns=col_map)
                if "date" not in df.columns:
                    df = df.rename(columns={df.columns[0]: "date"})
                if "close" not in df.columns:
                    for c in reversed(df.columns):
                        if df[c].dtype in [np.float64, np.int64]:
                            df = df.rename(columns={c: "close"})
                            break
                df["date"] = _parse_yf_date(df["date"])
                df["index_name"] = name
                df = df[["date", "index_name", "close"]].copy()
                all_frames.append(df)
                print(f"  [US] {name}: {len(df)} rows")
        if not all_frames:
            return pd.DataFrame()
        return pd.concat(all_frames, ignore_index=True)

    def fetch_all(self, stock_ids=None, period="5y", start_date="2021-01-01"):
        if stock_ids is None:
            stock_ids = list(self.TW_TICKERS.keys())
        print("=" * 60)
        print(f"  台股數據補抓 (載入已有 + FinMind)")
        print(f"  股票: {len(stock_ids)} 檔")
        print("=" * 60)
        data = {}
        print("\n[1/5] OHLCV (載入已有)...")
        data["price_ohlcv"] = self.fetch_ohlcv(stock_ids, period)
        print("\n[2/5] 法人買賣超 (FinMind)...")
        data["inst_flow"] = self.fetch_inst_flow(stock_ids, start_date)
        print("\n[3/5] 融資融券 (FinMind)...")
        data["margin"] = self.fetch_margin(stock_ids, start_date)
        print("\n[4/5] 期貨法人OI (FinMind)...")
        data["futures_oi"] = self.fetch_futures_oi(["TX", "MTX"], start_date)
        print("\n[5/5] 美股指數 (載入已有)...")
        data["us_indices"] = self.fetch_us_indices(period)
        print("\n" + "=" * 60)
        print("  拉取數據摘要:")
        for k, v in data.items():
            if len(v) > 0 and "date" in v.columns:
                print(f"  {k}: {len(v)} rows, {v['date'].min().date()} ~ {v['date'].max().date()}")
            else:
                print(f"  {k}: EMPTY")
        print("=" * 60)
        return data

    def save_all(self, data, path=None):
        path = path or str(DATA_DIR)
        import os
        os.makedirs(path, exist_ok=True)
        for k, v in data.items():
            if len(v) > 0:
                fpath = f"{path}/{k}.csv"
                v.to_csv(fpath, index=False)
                print(f"  Saved {k}: {fpath}")


if __name__ == "__main__":
    fetcher = TWStockDataFetcher(rate_limit_delay=2.0)
    all_stocks = ["2330","2308","2412","2311","2454","2382","3008","3034","3711",
                  "2303","1301","1303","1326","1101","2002","2882","2886","2891","2884","2881"]
    print("=" * 60)
    print("Kaggle 環境檢查")
    print("=" * 60)
    print(f"抓取股票：{len(all_stocks)} 檔")
    data = fetcher.fetch_all(stock_ids=all_stocks, period="5y", start_date="2021-01-01")
    fetcher.save_all(data, path=str(DATA_DIR))
    import shutil
    shutil.make_archive("/kaggle/working/twstock_v6_data", "zip", str(DATA_DIR))
    print("完成！")
    for f in sorted(DATA_DIR.iterdir()):
        print(f"  {f.name}: {f.stat().st_size:,} bytes")