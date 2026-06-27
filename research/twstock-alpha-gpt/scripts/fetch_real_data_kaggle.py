#!/usr/bin/env python3
"""
真實台股數據準備腳本 (Kaggle Kernel)

下載 OHLCV + 三大法人 + 融資融券 + 期貨OI + 美股指數，
輸出為 CSV 供 GRPO 訓練 kernel 使用。

執行環境: Kaggle (需 internet=True, GPU=False)
輸出: twstock_daily.csv, inst_data.csv, futures_oi.csv, us_indices.csv
      → 上傳為 Kaggle Dataset 供訓練 kernel 掛載

用法 (Kaggle kernel):
    1. 建立 script 模式 kernel，設定 internet=True, GPU=False
    2. 執行此腳本
    3. 從 /kaggle/working/ 下載輸出
    4. kaggle datasets create -p /path/to/output/ 將結果建為 Dataset
    5. 在訓練 kernel 的 kernel-metadata.json 中引用此 Dataset
"""
import os
import sys
import json
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# === 1. 安裝依賴 ===
print("[1/5] Installing dependencies...")
os.system("pip install -q twstock finmind yfinance")

# === 2. OHLCV 數據 ===
print("[2/5] Downloading OHLCV data...")
import twstock

STOCK_IDS = ["2330", "2454", "2382", "2308", "2412",  # 半導體/電子
             "1301", "1303", "1326",                    # 傳產
             "2882", "2886", "2891"]                    # 金融

ohlcv_records = []
for sid in STOCK_IDS:
    try:
        stock = twstock.Stock(sid)
        months_needed = 6
        data = []
        now = datetime.now()
        for m_offset in range(months_needed):
            total_month = now.year * 12 + (now.month - 1) - m_offset
            y = total_month // 12
            m = (total_month % 12) + 1
            try:
                monthly = stock.fetch(y, m)
                data.extend(monthly)
            except Exception:
                continue
        for d in data:
            ohlcv_records.append({
                "date": d.date,
                "stock_id": sid,
                "open": d.open,
                "high": d.high,
                "low": d.low,
                "close": d.close,
                "volume": d.capacity,
            })
        print(f"  {sid}: {len(data)} records")
        time.sleep(1)
    except Exception as e:
        print(f"  {sid}: ERROR - {e}")

df_ohlcv = pd.DataFrame(ohlcv_records)
if not df_ohlcv.empty:
    df_ohlcv = df_ohlcv.sort_values(["stock_id", "date"]).reset_index(drop=True)
print(f"  OHLCV total: {len(df_ohlcv)} rows, {df_ohlcv['stock_id'].nunique()} stocks")

# === 3. 三大法人買賣超數據 ===
print("[3/5] Downloading institutional investor data (FinMind)...")
try:
    from FinMind.data import DataLoader
    dl = DataLoader()

    inst_records = []
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')

    for sid in STOCK_IDS:
        try:
            df_inst = dl.taiwan_stock_institutional_investors(
                stock_id=sid,
                start_date=start_date,
                end_date=end_date
            )
            if len(df_inst) > 0:
                for date, group in df_inst.groupby('date'):
                    row = {'date': date, 'stock_id': sid}
                    for _, r in group.iterrows():
                        itype = r['institutional_investors']
                        # FinMind 欄位名稱因版本而異
                        buy_col = 'buy' if 'buy' in df_inst.columns else 'long_buy'
                        sell_col = 'sell' if 'sell' in df_inst.columns else 'long_sell'
                        net_val = r.get(buy_col, 0) - r.get(sell_col, 0)
                        if '外資' in itype:
                            row['foreign_net'] = net_val
                        elif '投信' in itype:
                            row['trust_net'] = net_val
                        elif '自營商' in itype and '避險' not in itype:
                            row['dealer_self_net'] = net_val
                    if 'foreign_net' not in row:
                        row['foreign_net'] = 0
                    if 'trust_net' not in row:
                        row['trust_net'] = 0
                    if 'dealer_self_net' not in row:
                        row['dealer_self_net'] = 0
                    row['total_net'] = row['foreign_net'] + row['trust_net'] + row['dealer_self_net']
                    inst_records.append(row)
            print(f"  {sid}: {len(df_inst)} records")
            time.sleep(0.5)
        except Exception as e:
            print(f"  {sid}: ERROR - {e}")

    df_inst_final = pd.DataFrame(inst_records)
except Exception as e:
    print(f"  FinMind error: {e}")
    df_inst_final = pd.DataFrame()

print(f"  Institutional data: {len(df_inst_final)} rows")

# === 4. 期貨OI數據 ===
print("[4/5] Downloading futures OI data (FinMind)...")
try:
    from FinMind.data import DataLoader
    dl = DataLoader()

    futures_records = []
    start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')

    for fid in ['TX', 'MTX']:
        try:
            df_foi = dl.taiwan_futures_institutional_investors(
                futures_id=fid,
                start_date=start_date,
                end_date=end_date
            )
            if len(df_foi) > 0:
                # 注意: institutional_investors 欄位是中文!
                for date, group in df_foi.groupby('date'):
                    row = {'date': date, 'futures_id': fid}
                    inst_net = 0
                    for _, r in group.iterrows():
                        itype = r['institutional_investors']
                        long_oi = r.get('long_open_interest', r.get('long', 0))
                        short_oi = r.get('short_open_interest', r.get('short', 0))
                        net_oi = long_oi - short_oi
                        if '外資' in itype or '投信' in itype or '自營商' in itype:
                            inst_net += net_oi
                    row['inst_net_oi'] = inst_net
                    row['retail_net_oi'] = -inst_net  # 散戶 = 反向
                    futures_records.append(row)
            print(f"  {fid}: {len(df_foi)} records")
            time.sleep(0.5)
        except Exception as e:
            print(f"  {fid}: ERROR - {e}")

    df_futures = pd.DataFrame(futures_records)
except Exception as e:
    print(f"  Futures OI error: {e}")
    df_futures = pd.DataFrame()

print(f"  Futures OI: {len(df_futures)} rows")

# === 5. 美股指數數據 ===
print("[5/5] Downloading US indices data (yfinance)...")
import yfinance as yf

indices_config = {
    'Nasdaq': '^IXIC',
    'SP500': '^GSPC',
    'DowJones': '^DJI',
}

us_records = []
for name, ticker in indices_config.items():
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period='6mo')
        if len(hist) > 0:
            hist = hist.reset_index()
            for _, r in hist.iterrows():
                date_val = r['Date']
                if hasattr(date_val, 'date'):
                    date_val = date_val.date()
                # 轉為 tz-naive date
                if hasattr(date_val, 'strftime'):
                    date_val = date_val.strftime('%Y-%m-%d')
                us_records.append({
                    'date': date_val,
                    'index_name': name,
                    'open': r['Open'],
                    'high': r['High'],
                    'low': r['Low'],
                    'close': r['Close'],
                    'volume': r['Volume'],
                })
        print(f"  {name}: {len(hist)} records")
        time.sleep(1)
    except Exception as e:
        print(f"  {name}: ERROR - {e}")

df_us = pd.DataFrame(us_records)
print(f"  US indices: {len(df_us)} rows")

# === 儲存輸出 ===
output_dir = "/kaggle/working/" if os.path.isdir("/kaggle/working/") else "/tmp/real_data_output/"
os.makedirs(output_dir, exist_ok=True)

df_ohlcv.to_csv(os.path.join(output_dir, "twstock_daily.csv"), index=False)
if len(df_inst_final) > 0:
    df_inst_final.to_csv(os.path.join(output_dir, "inst_data.csv"), index=False)
if len(df_futures) > 0:
    df_futures.to_csv(os.path.join(output_dir, "futures_oi.csv"), index=False)
if len(df_us) > 0:
    df_us.to_csv(os.path.join(output_dir, "us_indices.csv"), index=False)

# Summary
summary = {
    "created_at": datetime.now().isoformat(),
    "ohlcv_rows": len(df_ohlcv),
    "ohlcv_stocks": df_ohlcv['stock_id'].nunique() if not df_ohlcv.empty else 0,
    "inst_rows": len(df_inst_final),
    "futures_rows": len(df_futures),
    "us_indices_rows": len(df_us),
}
with open(os.path.join(output_dir, "data_summary.json"), "w") as f:
    json.dump(summary, f, indent=2)

# dataset-metadata.json for Kaggle Dataset creation
ds_meta = {
    "title": "twstock-grpo-real-training-data",
    "id": "mhhuang14/twstock-grpo-real-training-data",
    "licenses": [{"name": "CC0-1.0"}]
}
with open(os.path.join(output_dir, "dataset-metadata.json"), "w") as f:
    json.dump(ds_meta, f, indent=2)

print(f"\n=== Data Preparation Complete ===")
print(f"OHLCV: {summary['ohlcv_rows']} rows ({summary['ohlcv_stocks']} stocks)")
print(f"Institutional: {summary['inst_rows']} rows")
print(f"Futures OI: {summary['futures_rows']} rows")
print(f"US indices: {summary['us_indices_rows']} rows")
print(f"Output: {output_dir}")
print(f"\nNext steps:")
print(f"  1. Download output from Kaggle")
print(f"  2. kaggle datasets create -p {output_dir}")
print(f"  3. Update training kernel's kernel-metadata.json dataset_sources")
