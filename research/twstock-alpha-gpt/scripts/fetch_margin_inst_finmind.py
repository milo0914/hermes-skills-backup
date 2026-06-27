#!/usr/bin/env python3
"""
FinMind Margin + Inst Flow Fetcher for single stock
當股票從現有 dataset 中缺失 margin/inst_flow 資料時，用此腳本獨立補抓。

Usage:
    python3 fetch_margin_inst_finmind.py 2317 --start 2021-01-04
    python3 fetch_margin_inst_finmind.py 2317 --merge --margin-csv margin.csv --inst-csv inst_flow.csv
"""

import argparse
import pandas as pd
import requests
import sys
import time
import warnings

BASE = "https://api.finmindtrade.com/api/v4/data"
MAX_PAGES = 30  # Safety limit (each page ~1300 rows for daily data)


def fetch_dataset(dataset: str, data_id: str, start_date: str,
                  max_pages: int = MAX_PAGES) -> list:
    """Paginated fetch from FinMind REST API"""
    all_rows = []
    for page in range(1, max_pages + 1):
        params = {
            "dataset": dataset,
            "data_id": data_id,
            "start_date": start_date,
            "page": page,
        }
        try:
            resp = requests.get(BASE, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if not data:
                    break
                all_rows.extend(data)
            elif resp.status_code == 402:
                warnings.warn(f"FinMind API daily quota exceeded at page {page}")
                break
            else:
                warnings.warn(f"FinMind API {resp.status_code}: {resp.text[:100]}")
                break
        except Exception as e:
            warnings.warn(f"Page {page}: {e}")
            break
        time.sleep(1)
    return all_rows


def parse_margin(margin_data: list) -> pd.DataFrame:
    """Convert FinMind margin raw data to merged format."""
    df = pd.DataFrame(margin_data)
    if df.empty:
        return df

    df['stock_id'] = df['stock_id'].astype(int)
    m = pd.DataFrame()
    m['date'] = df['date']
    m['stock_id'] = df['stock_id']
    m['margin_buy'] = df['MarginPurchaseBuy']
    m['margin_sell'] = df['MarginPurchaseSell']
    m['margin_cash_repay'] = df['MarginPurchaseCashRepayment']
    m['margin_change'] = df['MarginPurchaseTodayBalance'] - df['MarginPurchaseYesterdayBalance']
    m['margin_balance'] = df['MarginPurchaseTodayBalance']
    m['short_buy'] = df['ShortSaleBuy']
    m['short_sell'] = df['ShortSaleSell']
    m['short_cash_repay'] = df['ShortSaleCashRepayment']
    m['short_change'] = df['ShortSaleTodayBalance'] - df['ShortSaleYesterdayBalance']
    m['short_balance'] = df['ShortSaleTodayBalance']
    return m


def parse_inst_flow(inst_data: list) -> pd.DataFrame:
    """Convert FinMind inst flow raw data to merged format (pivot by name)."""
    df = pd.DataFrame(inst_data)
    if df.empty:
        return df

    df['stock_id'] = df['stock_id'].astype(int)
    df['net'] = df['buy'] - df['sell']

    pivot = df.pivot_table(
        index=['date', 'stock_id'],
        columns='name',
        values='net',
        aggfunc='first'
    ).reset_index()
    pivot.columns.name = None
    pivot.columns = [str(c) for c in pivot.columns]

    # Target columns
    target_cols = ['date', 'stock_id', 'Dealer_Hedging', 'Dealer_self',
                   'Foreign_Dealer_Self', 'Foreign_Investor', 'Investment_Trust']

    # Calculate total_net
    net_cols = [c for c in pivot.columns if c not in ('date', 'stock_id')]
    pivot['total_net'] = pivot[net_cols].sum(axis=1)

    for col in target_cols:
        if col not in pivot.columns:
            pivot[col] = 0.0

    return pivot[['date', 'stock_id', 'Dealer_Hedging', 'Dealer_self',
                   'Foreign_Dealer_Self', 'Foreign_Investor',
                   'Investment_Trust', 'total_net']]


def main():
    parser = argparse.ArgumentParser(description="FinMind Margin+Inst Flow Fetcher")
    parser.add_argument("stock_id", help="Stock ID (e.g. 2317)")
    parser.add_argument("--start", default="2021-01-04", help="Start date YYYY-MM-DD")
    parser.add_argument("--merge", action="store_true", help="Merge with existing CSVs")
    parser.add_argument("--margin-csv", default=None, help="Path to existing margin.csv")
    parser.add_argument("--inst-csv", default=None, help="Path to existing inst_flow.csv")
    parser.add_argument("--output-dir", default=".", help="Output directory")
    args = parser.parse_args()

    # --- Fetch Margin ---
    print(f"Fetching margin for {args.stock_id}...", file=sys.stderr)
    margin_raw = fetch_dataset("TaiwanStockMarginPurchaseShortSale",
                               args.stock_id, args.start)
    if margin_raw:
        df_margin = parse_margin(margin_raw)
        print(f"  Margin: {len(df_margin)} rows, {df_margin.date.min()} ~ {df_margin.date.max()}",
              file=sys.stderr)
        df_margin.to_csv(f"{args.output_dir}/margin_{args.stock_id}.csv", index=False)
        print(f"  Saved: margin_{args.stock_id}.csv", file=sys.stderr)
    else:
        print(f"  No margin data for {args.stock_id}", file=sys.stderr)
        df_margin = pd.DataFrame()

    # --- Fetch Inst Flow ---
    print(f"Fetching inst_flow for {args.stock_id}...", file=sys.stderr)
    inst_raw = fetch_dataset("TaiwanStockInstitutionalInvestorsBuySell",
                              args.stock_id, args.start)
    if inst_raw:
        df_inst = parse_inst_flow(inst_raw)
        print(f"  Inst Flow: {len(df_inst)} rows, {df_inst.date.min()} ~ {df_inst.date.max()}",
              file=sys.stderr)
        df_inst.to_csv(f"{args.output_dir}/inst_{args.stock_id}.csv", index=False)
        print(f"  Saved: inst_{args.stock_id}.csv", file=sys.stderr)
    else:
        print(f"  No inst flow data for {args.stock_id}", file=sys.stderr)
        df_inst = pd.DataFrame()

    # --- Merge if requested ---
    if args.merge and args.margin_csv:
        existing = pd.read_csv(args.margin_csv)
        existing['stock_id'] = existing['stock_id'].astype(int)
        combined = pd.concat([existing, df_margin], ignore_index=True)
        combined = combined.drop_duplicates(subset=['date', 'stock_id'])
        combined = combined.sort_values(['stock_id', 'date'])
        combined.to_csv(args.margin_csv, index=False)
        print(f"  Merged margin: {len(combined)} rows, {args.stock_id}={len(combined[combined.stock_id==int(args.stock_id)])}",
              file=sys.stderr)

    if args.merge and args.inst_csv:
        existing = pd.read_csv(args.inst_csv)
        existing['stock_id'] = existing['stock_id'].astype(int)
        common_cols = list(set(df_inst.columns) & set(existing.columns))
        combined = pd.concat([existing[common_cols], df_inst[common_cols]], ignore_index=True)
        combined = combined.drop_duplicates(subset=['date', 'stock_id'])
        combined = combined.sort_values(['stock_id', 'date'])
        combined.to_csv(args.inst_csv, index=False)
        print(f"  Merged inst_flow: {len(combined)} rows, {args.stock_id}={len(combined[combined.stock_id==int(args.stock_id)])}",
              file=sys.stderr)


if __name__ == "__main__":
    main()