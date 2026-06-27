#!/usr/bin/env python3
"""
TWSE STOCK_DAY OHLCV Fetcher
當 yfinance (429 rate limit) 和 FinMind (402 quota exceeded) 都不可用時，
TWSE 官方 STOCK_DAY API 是可靠的 OHLCV 備源。

Usage:
    python3 fetch_twse_ohlcv.py 2317 --start 2021-01-04 --end 2026-06-12
    python3 fetch_twse_ohlcv.py 2317 2330 2454 --output price_2317.csv
"""

import argparse
import pandas as pd
import requests
import time
import sys

BASE_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"


def convert_twse_date(d: str) -> str:
    """Convert ROC date '115/06/01' to '2026-06-01'"""
    parts = d.split('/')
    y = int(parts[0]) + 1911
    return f'{y}-{parts[1]}-{parts[2]}'


def parse_price(s: str) -> float:
    """Parse TWSE price string (handles commas and '--')"""
    try:
        return float(s.replace(',', ''))
    except (ValueError, AttributeError):
        return 0.0


def fetch_month(stock_id: str, year: int, month: int, delay: float = 1.0) -> list:
    """Fetch a single month of OHLCV data. Returns list of rows (10 cols)."""
    url = BASE_URL
    params = {
        "response": "json",
        "date": f"{year:04d}{month:02d}01",
        "stockNo": stock_id,
    }
    try:
        resp = requests.get(url, params=params, timeout=30,
                          headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            data = resp.json()
            if data.get("stat") == "OK":
                return data.get("data", [])
    except Exception as e:
        print(f"  {year}/{month:02d}: {e}", file=sys.stderr)
    time.sleep(delay)
    return []


def fetch_ohlcv(stock_id: str, start_year: int = 2021, end_year: int = 2026,
                end_month: int = 6, delay: float = 0.8) -> pd.DataFrame:
    """Fetch OHLCV for a stock from TWSE, returning price_ohlcv.csv format."""
    all_rows = []
    total_months = 0

    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            if year == end_year and month > end_month:
                break
            total_months += 1
            rows = fetch_month(stock_id, year, month, delay)
            if rows:
                all_rows.extend(rows)
            # Progress indicator
            if total_months % 12 == 0:
                print(f"  Processed {total_months} months, {len(all_rows)} rows so far...",
                      file=sys.stderr)

    if not all_rows:
        print(f"No data found for {stock_id}", file=sys.stderr)
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    # 10 columns: 日期, 成交股數, 成交金額, 開盤價, 最高價, 最低價, 收盤價, 漲跌價差, 成交筆數, 註記
    df['date'] = df[0].apply(convert_twse_date)
    df_ohlcv = pd.DataFrame({
        'date': df['date'],
        'stock_id': int(stock_id),
        'open': df[3].apply(parse_price),
        'high': df[4].apply(parse_price),
        'low': df[5].apply(parse_price),
        'close': df[6].apply(parse_price),
        'volume': df[1].apply(parse_price),
    }).sort_values('date').reset_index(drop=True)

    return df_ohlcv


def main():
    parser = argparse.ArgumentParser(description="TWSE OHLCV Fetcher")
    parser.add_argument("stock_ids", nargs="+", help="Stock IDs (e.g. 2317 2330)")
    parser.add_argument("--start", default="2021-01-04", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default="2026-06-12", help="End date YYYY-MM-DD")
    parser.add_argument("--output", "-o", default=None, help="Output CSV path")
    parser.add_argument("--delay", type=float, default=0.8, help="Delay between requests (seconds)")
    args = parser.parse_args()

    # Parse years
    start_yr = int(args.start[:4])
    end_yr = int(args.end[:4])
    end_mo = int(args.end[5:7])

    for sid in args.stock_ids:
        print(f"Fetching {sid} ({start_yr}-{end_yr}/{end_mo})...", file=sys.stderr)
        df = fetch_ohlcv(sid, start_yr, end_yr, end_mo, args.delay)
        if len(df) > 0:
            print(f"  Got {len(df)} rows, {df.date.min()} ~ {df.date.max()}", file=sys.stderr)
            out_path = args.output or f"price_{sid}.csv"
            df.to_csv(out_path, index=False)
            print(f"  Saved to {out_path}", file=sys.stderr)
        else:
            print(f"  No data for {sid}", file=sys.stderr)


if __name__ == "__main__":
    main()