# -*- coding: utf-8 -*-
"""
TWStock Real Data Fetcher — 台股真實數據拉取模組
v4.2 / 2026-06-09

數據源:
- OHLCV: yfinance (台股 .TW) — 處理 MultiIndex columns
- 法人買賣超: FinMind taiwan_stock_institutional_investors
- 融資融券: FinMind taiwan_stock_margin_purchase_short_sale
- 期貨法人OI: FinMind taiwan_futures_institutional_investors (TX/MTX)
  → institutional_investors 欄位為中文（外資/投信/自營商/避險）
  → 需中文→英文映射後計算 net OI = long_open_interest - short_open_interest
- 美股指數: yfinance (^IXIC, ^GSPC, ^DJI)

用法:
 from fetch_real_data import TWStockDataFetcher
 fetcher = TWStockDataFetcher()
 data = fetcher.fetch_all(stock_ids=["2330","2454","1301","2882"], period="2y")
"""

import time
import numpy as np
import pandas as pd
from typing import Dict, List, Optional


def _flatten_yf_columns(df: pd.DataFrame) -> pd.DataFrame:
    """yfinance v1.4+ returns MultiIndex columns. Flatten to simple."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df


def _parse_yf_date(series: pd.Series) -> pd.Series:
    """Parse yfinance date column, handling timezone-aware timestamps."""
    dt = pd.to_datetime(series, utc=True)
    try:
        dt = dt.dt.tz_localize(None)
    except TypeError:
        pass  # already tz-naive
    return dt


class TWStockDataFetcher:
    """台股真實數據拉取器 — 整合 yfinance + FinMind"""

    TW_TICKERS = {
        # === LARGE_CAP (4檔) ===
        "2330": "2330.TW",  # 台積電
        "2308": "2308.TW",  # 台達電
        "2412": "2412.TW",  # 中華電
        "2311": "2311.TW",  # 鴻海
        # === MID_CAP_TECH (6檔) ===
        "2454": "2454.TW",  # 聯發科
        "2382": "2382.TW",  # 廣達
        "3008": "3008.TW",  # 大立光
        "3034": "3034.TW",  # 聯詠
        "3711": "3711.TW",  # 日月光
        "2303": "2303.TW",  # 聯電
        # === TRADITIONAL (5檔) ===
        "1301": "1301.TW",  # 台塑
        "1303": "1303.TW",  # 南亞
        "1326": "1326.TW",  # 台化
        "1101": "1101.TW",  # 台泥
        "2002": "2002.TW",  # 中鋼
        # === FINANCIAL (5檔) ===
        "2882": "2882.TW",  # 國泰金
        "2886": "2886.TW",  # 兆豐金
        "2891": "2891.TW",  # 中信金
        "2884": "2884.TW",  # 玉山金
        "2881": "2881.TW",  # 富邦金
    }

    US_INDEX_TICKERS = {
        "Nasdaq": "^IXIC",
        "SP500": "^GSPC",
        "DowJones": "^DJI",
    }

    # FinMind 期貨 institutional_investors 欄位中文→英文映射
    FUTURES_INST_MAP = {
        "外資": "Foreign_Investor",
        "投信": "Investment_Trust",
        "自營商": "Dealer_self",
        "避險": "Dealer_Hedging",
    }

    def __init__(self, rate_limit_delay: float = 3.0, max_retries: int = 3):
        self.delay = rate_limit_delay
        self.max_retries = max_retries
        self._finmind_dl = None

    @property
    def finmind(self):
        if self._finmind_dl is None:
            from FinMind.data import DataLoader
            self._finmind_dl = DataLoader()
        return self._finmind_dl

    def _yf_download_with_retry(self, ticker: str, period: str = "2y",
                                interval: str = "1d") -> pd.DataFrame:
        """yfinance download with retry for rate limiting."""
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

    # ----------------------------------------------------------
    # 1. 台股 OHLCV (yfinance)
    # ----------------------------------------------------------
    def fetch_ohlcv(self, stock_ids: List[str], period: str = "2y") -> pd.DataFrame:
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
                    if cl == "date" or cl == "price":
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

    # ----------------------------------------------------------
    # 2. 法人買賣超 (FinMind)
    # ----------------------------------------------------------
    def fetch_inst_flow(self, stock_ids: List[str], start_date: str = "2024-01-01") -> pd.DataFrame:
        all_frames = []
        for sid in stock_ids:
            try:
                df = self.finmind.taiwan_stock_institutional_investors(
                    stock_id=sid, start_date=start_date
                )
                if len(df) > 0:
                    df["date"] = pd.to_datetime(df["date"])
                    df["net_buy"] = df["buy"] - df["sell"]
                    pivoted = df.pivot_table(
                        index="date", columns="name", values="net_buy", aggfunc="sum"
                    ).reset_index()
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

    # ----------------------------------------------------------
    # 3. 融資融券 (FinMind)
    # ----------------------------------------------------------
    def fetch_margin(self, stock_ids: List[str], start_date: str = "2024-01-01") -> pd.DataFrame:
        all_frames = []
        for sid in stock_ids:
            try:
                df = self.finmind.taiwan_stock_margin_purchase_short_sale(
                    stock_id=sid, start_date=start_date
                )
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

    # ----------------------------------------------------------
    # 4. 期貨法人 OI (FinMind)
    #    FinMind 回傳 institutional_investors 為中文（外資/投信/自營商/避險）
    #    需映射為英文 column，計算 net_oi = long_open_interest - short_open_interest
    # ----------------------------------------------------------
    def fetch_futures_oi(self, futures_ids: List[str] = None,
                         start_date: str = "2024-01-01") -> pd.DataFrame:
        if futures_ids is None:
            futures_ids = ["TX", "MTX"]

        all_frames = []
        for fid in futures_ids:
            try:
                df = self.finmind.taiwan_futures_institutional_investors(
                    futures_id=fid, start_date=start_date
                )
                if len(df) > 0:
                    df["date"] = pd.to_datetime(df["date"])
                    df["futures_id"] = fid
                    # 計算每列淨 OI = 多方未平倉 - 空方未平倉
                    df["net_oi"] = (
                        df["long_open_interest_balance_volume"]
                        - df["short_open_interest_balance_volume"]
                    )
                    all_frames.append(df)
                    print(f"  [FuturesOI] {fid}: {len(df)} raw rows, "
                          f"inst types: {df['institutional_investors'].unique().tolist()}")
            except Exception as e:
                print(f"  [FuturesOI] {fid}: ERROR - {e}")

        if not all_frames:
            return pd.DataFrame()

        raw = pd.concat(all_frames, ignore_index=True)

        # Aggregate: per date + futures_id, 中文→英文映射
        agg_rows = []
        for (fid, date), grp in raw.groupby(["futures_id", "date"]):
            row = {"date": date, "futures_id": fid}
            for cn_name, en_name in self.FUTURES_INST_MAP.items():
                inst_grp = grp[grp["institutional_investors"] == cn_name]
                if len(inst_grp) > 0:
                    row[f"{en_name}_net_oi"] = inst_grp["net_oi"].iloc[0]
                else:
                    row[f"{en_name}_net_oi"] = 0

            # 計算所有法人的淨 OI 總和
            total_inst_net_oi = (
                row.get("Foreign_Investor_net_oi", 0) +
                row.get("Investment_Trust_net_oi", 0) +
                row.get("Dealer_self_net_oi", 0) +
                row.get("Dealer_Hedging_net_oi", 0)
            )

            # TX: inst_net_oi = 外資淨多 OI（法人偏多指標）
            #     retail_net_oi = 總 OI - 法人 OI（散戶 = -法人，零和）
            if fid == "TX":
                row["inst_net_oi"] = row.get("Foreign_Investor_net_oi", 0)
                # 總 OI = 所有法人的淨 OI 總和（零和市場假設）
                row["retail_net_oi"] = -total_inst_net_oi

            # MTX: retail_net_oi = 自營商淨 OI（散戶代理指標）
            #       inst_net_oi = 總 OI - 散戶 OI
            if fid == "MTX":
                row["retail_net_oi"] = row.get("Dealer_self_net_oi", 0)
                row["inst_net_oi"] = -row["retail_net_oi"]  # 總 OI - 散戶 = -散戶（零和）

            agg_rows.append(row)

        result = pd.DataFrame(agg_rows)
        print(f"  [FuturesOI] aggregated: {len(result)} rows")
        # Verify
        tx = result[result["futures_id"] == "TX"]
        mtx = result[result["futures_id"] == "MTX"]
        if len(tx) > 0:
            nz = (tx["inst_net_oi"].fillna(0) != 0).sum()
            print(f"  [FuturesOI] TX inst_net_oi non-zero: {nz}/{len(tx)}")
        if len(mtx) > 0:
            nz = (mtx["retail_net_oi"].fillna(0) != 0).sum()
            print(f"  [FuturesOI] MTX retail_net_oi non-zero: {nz}/{len(mtx)}")
        return result

    # ----------------------------------------------------------
    # 5. 美股指數 (yfinance)
    # ----------------------------------------------------------
    def fetch_us_indices(self, period: str = "2y") -> pd.DataFrame:
        all_frames = []
        for name, ticker in self.US_INDEX_TICKERS.items():
            data = self._yf_download_with_retry(ticker, period)
            if len(data) > 0:
                data = _flatten_yf_columns(data)
                df = data.reset_index()
                col_map = {}
                for c in df.columns:
                    cl = c.lower().strip()
                    if cl == "date" or cl == "price":
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

    # ----------------------------------------------------------
    # 6. 一次拉取全部
    # ----------------------------------------------------------
    def fetch_all(self, stock_ids: List[str] = None,
                  period: str = "5y",
                  start_date: str = "2021-01-01") -> Dict[str, pd.DataFrame]:
        if stock_ids is None:
            stock_ids = list(self.TW_TICKERS.keys())

        print("=" * 60)
        print(f"  台股數據拉取: {stock_ids}")
        print(f"  期間: {period} / {start_date}+")
        print("=" * 60)

        data = {}

        print("\n[1/5] OHLCV...")
        data["price_ohlcv"] = self.fetch_ohlcv(stock_ids, period)

        print("\n[2/5] 法人買賣超...")
        data["inst_flow"] = self.fetch_inst_flow(stock_ids, start_date)

        print("\n[3/5] 融資融券...")
        data["margin"] = self.fetch_margin(stock_ids, start_date)

        print("\n[4/5] 期貨法人OI...")
        data["futures_oi"] = self.fetch_futures_oi(["TX", "MTX"], start_date)

        print("\n[5/5] 美股指數...")
        data["us_indices"] = self.fetch_us_indices(period)

        # Summary
        print("\n" + "=" * 60)
        print("  拉取數據摘要:")
        for k, v in data.items():
            if len(v) > 0 and "date" in v.columns:
                print(f"  {k}: {len(v)} rows, {v['date'].min().date()} ~ {v['date'].max().date()}")
            else:
                print(f"  {k}: EMPTY")
        print("=" * 60)

        # --- v6.0: 數據質量驗證報告 ---
        print("\n" + "=" * 60)
        print("  數據質量驗證報告:")
        print("=" * 60)

        # 1. OHLCV 覆蓋率
        price_df = data.get("price_ohlcv", pd.DataFrame())
        if len(price_df) > 0 and "stock_id" in price_df.columns:
            for sid in stock_ids:
                sid_df = price_df[price_df["stock_id"] == sid]
                print(f"  OHLCV {sid}: {len(sid_df)} 筆")

        # 2. 法人資料覆蓋率
        inst_df = data.get("inst_flow", pd.DataFrame())
        if len(inst_df) > 0 and "stock_id" in inst_df.columns:
            for sid in stock_ids:
                sid_df = inst_df[inst_df["stock_id"] == sid]
                print(f"  Inst  {sid}: {len(sid_df)} 筆")

        # 3. 期貨 OI 覆蓋率
        futures_df = data.get("futures_oi", pd.DataFrame())
        if len(futures_df) > 0:
            for fid in futures_df["futures_id"].unique():
                fid_df = futures_df[futures_df["futures_id"] == fid]
                print(f"  FutOI {fid}: {len(fid_df)} 筆")

        # 4. 美股指數覆蓋率
        us_df = data.get("us_indices", pd.DataFrame())
        if len(us_df) > 0 and "index_name" in us_df.columns:
            for idx_name in us_df["index_name"].unique():
                idx_df = us_df[us_df["index_name"] == idx_name]
                print(f"  USIdx {idx_name}: {len(idx_df)} 筆")

        print("=" * 60)

        return data

    # ----------------------------------------------------------
    # 7. 存檔 / 讀檔
    # ----------------------------------------------------------
    def save_all(self, data: Dict[str, pd.DataFrame], path: str = "/tmp/twstock_real_data"):
        import os
        os.makedirs(path, exist_ok=True)
        for k, v in data.items():
            if len(v) > 0:
                fpath = f"{path}/{k}.csv"
                v.to_csv(fpath, index=False)
                print(f"  Saved {k}: {fpath}")

    def load_all(self, path: str = "/tmp/twstock_real_data") -> Dict[str, pd.DataFrame]:
        import os
        data = {}
        for name in ["price_ohlcv", "inst_flow", "margin", "futures_oi", "us_indices"]:
            fpath = f"{path}/{name}.csv"
            if os.path.exists(fpath):
                data[name] = pd.read_csv(fpath, parse_dates=["date"])
                print(f"  Loaded {name}: {len(data[name])} rows")
            else:
                data[name] = pd.DataFrame()
        return data


if __name__ == "__main__":
    import os
    print("=" * 60)
    print("Kaggle 環境檢查")
    print("=" * 60)
    fetcher = TWStockDataFetcher(rate_limit_delay=2.0)
    all_stocks = ["2330","2308","2412","2311","2454","2382","3008","3034","3711","2303","1301","1303","1326","1101","2002","2882","2886","2891","2884","2881"]
    print(f"抓取股票：{len(all_stocks)} 檔")
    data = fetcher.fetch_all(stock_ids=all_stocks, period="5y", start_date="2021-01-01")
    output_dir = "/kaggle/working/twstock_v6_data"
    os.makedirs(output_dir, exist_ok=True)
    fetcher.save_all(data, path=output_dir)
    import shutil
    shutil.make_archive("/kaggle/working/twstock_v6_data", "zip", output_dir)
    print("完成！")
    for f in os.listdir("/kaggle/working/"):
        print(f"  {f}")
