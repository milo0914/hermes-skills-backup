# -*- coding: utf-8 -*-
"""
TWStock Real Data Fetcher — Kaggle CPU 版本
v6.0 / 2026-06-11
執行環境：Kaggle Notebook (CPU mode)
"""

import os
import time
import numpy as np
import pandas as pd
from typing import Dict, List

print("=" * 60)
print("TWStock Data Fetcher v6.0 - Kaggle CPU Mode")
print("=" * 60)

# 安裝依賴
print("\n[安裝依賴]")
os.system("pip install FinMind yfinance -q")

from FinMind.data import DataLoader

# 初始化
fm = DataLoader()
TW_TICKERS = {
    "2330": "2330.TW", "2308": "2308.TW", "2412": "2412.TW", "2311": "2311.TW",
    "2454": "2454.TW", "2382": "2382.TW", "3008": "3008.TW", "3034": "3034.TW",
    "3711": "3711.TW", "2303": "2303.TW", "1301": "1301.TW", "1303": "1303.TW",
    "1326": "1326.TW", "1101": "1101.TW", "2002": "2002.TW", "2882": "2882.TW",
    "2886": "2886.TW", "2891": "2891.TW", "2884": "2884.TW", "2881": "2881.TW",
}
US_INDEX = {"Nasdaq": "^IXIC", "SP500": "^GSPC", "DowJones": "^DJI"}

def fetch_ohlcv(stock_ids, period="5y"):
    import yfinance as yf
    all_df = []
    for sid in stock_ids:
        ticker = TW_TICKERS.get(sid, f"{sid}.TW")
        try:
            time.sleep(2)
            df = yf.download(ticker, period=period, progress=False)
            if len(df) > 0:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
                df = df.reset_index()
                df = df.rename(columns={df.columns[0]: "date"})
                df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
                df["stock_id"] = sid
                cols = ["date", "stock_id", "Open", "High", "Low", "Close", "Volume"]
                df = df[[c for c in cols if c in df.columns]]
                df = df.rename(columns={c.lower(): c for c in df.columns if c != "date"})
                all_df.append(df)
                print(f"  OHLCV {sid}: {len(df)} rows")
        except Exception as e:
            print(f"  OHLCV {sid}: ERROR {e}")
    return pd.concat(all_df, ignore_index=True) if all_df else pd.DataFrame()

def fetch_inst_flow(stock_ids, start_date="2021-01-01"):
    all_df = []
    for sid in stock_ids:
        try:
            df = fm.taiwan_stock_institutional_investors(stock_id=sid, start_date=start_date)
            if len(df) > 0:
                df["date"] = pd.to_datetime(df["date"])
                df["net_buy"] = df["buy"] - df["sell"]
                piv = df.pivot_table(index="date", columns="name", values="net_buy", aggfunc="sum").reset_index()
                piv.columns.name = None
                piv["total_net"] = piv[[c for c in piv.columns if c != "date"]].sum(axis=1)
                piv["stock_id"] = sid
                all_df.append(piv)
                print(f"  Inst {sid}: {len(piv)} rows")
        except Exception as e:
            print(f"  Inst {sid}: ERROR {e}")
    return pd.concat(all_df, ignore_index=True) if all_df else pd.DataFrame()

def fetch_margin(stock_ids, start_date="2021-01-01"):
    all_df = []
    for sid in stock_ids:
        try:
            df = fm.taiwan_stock_margin_purchase_short_sale(stock_id=sid, start_date=start_date)
            if len(df) > 0:
                df["date"] = pd.to_datetime(df["date"])
                df = df[["date", "stock_id", "MarginPurchaseTodayBalance"]].copy()
                df = df.rename(columns={"MarginPurchaseTodayBalance": "margin_balance"})
                all_df.append(df)
                print(f"  Margin {sid}: {len(df)} rows")
        except Exception as e:
            print(f"  Margin {sid}: ERROR {e}")
    return pd.concat(all_df, ignore_index=True) if all_df else pd.DataFrame()

def fetch_futures_oi(futures_ids=["TX", "MTX"], start_date="2021-01-01"):
    all_df = []
    for fid in futures_ids:
        try:
            df = fm.taiwan_futures_institutional_investors(futures_id=fid, start_date=start_date)
            if len(df) > 0:
                df["date"] = pd.to_datetime(df["date"])
                df["futures_id"] = fid
                df["net_oi"] = df["long_open_interest_balance_volume"] - df["short_open_interest_balance_volume"]
                all_df.append(df)
                print(f"  FutOI {fid}: {len(df)} rows")
        except Exception as e:
            print(f"  FutOI {fid}: ERROR {e}")
    if not all_df:
        return pd.DataFrame()
    raw = pd.concat(all_df, ignore_index=True)
    agg = []
    for (fid, date), grp in raw.groupby(["futures_id", "date"]):
        row = {"date": date, "futures_id": fid}
        for cn in ["外資", "投信", "自營商", "避險"]:
            sub = grp[grp["institutional_investors"] == cn]
            row[f"{cn}_net_oi"] = sub["net_oi"].iloc[0] if len(sub) > 0 else 0
        total = sum(row.get(k, 0) for k in row if "net_oi" in k and k not in ["retail_net_oi", "inst_net_oi"])
        if fid == "TX":
            row["inst_net_oi"] = row.get("外資_net_oi", 0)
            row["retail_net_oi"] = -total
        elif fid == "MTX":
            row["retail_net_oi"] = row.get("自營商_net_oi", 0)
            row["inst_net_oi"] = -row["retail_net_oi"]
        agg.append(row)
    result = pd.DataFrame(agg)
    print(f"  FutOI aggregated: {len(result)} rows")
    return result

def fetch_us_indices(period="5y"):
    import yfinance as yf
    all_df = []
    for name, ticker in US_INDEX.items():
        try:
            time.sleep(2)
            df = yf.download(ticker, period=period, progress=False)
            if len(df) > 0:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
                df = df.reset_index()
                df = df.rename(columns={df.columns[0]: "date"})
                df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
                df["index_name"] = name
                if "Close" in df.columns:
                    df = df[["date", "index_name", "Close"]]
                    df = df.rename(columns={"Close": "close"})
                all_df.append(df)
                print(f"  US {name}: {len(df)} rows")
        except Exception as e:
            print(f"  US {name}: ERROR {e}")
    return pd.concat(all_df, ignore_index=True) if all_df else pd.DataFrame()

# 主程式
print("\n[開始抓取數據]")
stock_ids = list(TW_TICKERS.keys())
data = {}

print("\n[1/5] OHLCV...")
data["price_ohlcv"] = fetch_ohlcv(stock_ids, "5y")

print("\n[2/5] 法人買賣超...")
data["inst_flow"] = fetch_inst_flow(stock_ids, "2021-01-01")

print("\n[3/5] 融資融券...")
data["margin"] = fetch_margin(stock_ids, "2021-01-01")

print("\n[4/5] 期貨法人 OI...")
data["futures_oi"] = fetch_futures_oi(["TX", "MTX"], "2021-01-01")

print("\n[5/5] 美股指數...")
data["us_indices"] = fetch_us_indices("5y")

# 儲存
print("\n[儲存數據]")
out_dir = "/kaggle/working/twstock_v6_data"
os.makedirs(out_dir, exist_ok=True)
for name, df in data.items():
    if len(df) > 0:
        path = f"{out_dir}/{name}.csv"
        df.to_csv(path, index=False)
        print(f"  Saved {name}: {len(df)} rows → {path}")

# 驗證報告
print("\n" + "=" * 60)
print("數據質量驗證報告:")
print("=" * 60)
for name, df in data.items():
    print(f"  {name}: {len(df)} rows")
print("=" * 60)
print("\n完成！")
