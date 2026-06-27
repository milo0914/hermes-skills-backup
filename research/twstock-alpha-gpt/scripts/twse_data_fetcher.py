"""
台股歷史資料下載器 — TWSE 官方 API 程式化抓取

數據來源：
1. TWSE 官方 API (https://www.twse.com.tw/rwd/zh/...)
   - T86: 三大法人買賣超 (selectType=ALL, ~11,638 筆/日)
   - MI_MARGN: 融資融券餘額 (selectType=STOCK, ~1,018 筆/日)
   - TWT38U: 外資+投信+自營商買賣超 (~1,210 筆/日)
   - TWT44U: 投信買賣超 (~245 筆/日)
   - BFI82U: 三大法人匯總金額
2. yfinance: OHLCV 日 K 資料 (備用)
3. twstock: OHLCV 日 K 資料 (主力)

用法：
    fetcher = TWSEDataFetcher()
    # 抓取單日法人資料
    inst_df = fetcher.fetch_inst_daily('20250523')
    # 抓取單日融資融券
    margin_df = fetcher.fetch_margin_daily('20250523')
    # 批次抓取歷史區間
    inst_hist = fetcher.fetch_inst_range('20250101', '20250531')
    # 合併 OHLCV + 法人 + 融資融券
    full_df = fetcher.fetch_full_history(['2330','2454','1301','2882'], days=250)
"""

import json
import time
import io
import warnings
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
 import yfinance as yf
 HAS_YFINANCE = True
except ImportError:
 HAS_YFINANCE = False

try:
 import twstock
 HAS_TWSTOCK = True
except ImportError:
 HAS_TWSTOCK = False

try:
 from FinMind.data import DataLoader as FinMindLoader
 HAS_FINMIND = True
except ImportError:
 HAS_FINMIND = False


class TWSEDataFetcher:
    """TWSE 官方 API 歷史資料下載器
    
    已驗證可用端點：
    - T86 (三大法人買賣超): /rwd/zh/fund/T86?date=YYYYMMDD&response=json&selectType=ALL
    - MI_MARGN (融資融券): /rwd/zh/marginTrading/MI_MARGN?date=YYYYMMDD&response=json&selectType=STOCK
    """
    
    BASE_URL = "https://www.twse.com.tw/rwd/zh"
    REQUEST_DELAY = 0.5  # TWSE 請求間隔 (秒)，避免被 ban
    MAX_RETRIES = 3
    
    def __init__(self, request_delay: float = 0.5):
        self.session = requests.Session() if HAS_REQUESTS else None
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            'Accept': 'application/json',
        })
        self.request_delay = request_delay
        self._cache = {}  # 簡易記憶體快取
    
    # ============================================================
    # 1. 三大法人買賣超 (T86)
    # ============================================================
    
    def fetch_inst_daily(self, date_str: str, 
                         stock_filter: List[str] = None) -> Optional[pd.DataFrame]:
        """抓取單日三大法人買賣超
        
        Args:
            date_str: YYYYMMDD 格式
            stock_filter: 只保留特定股票代碼 (None = 全部)
        
        Returns:
            DataFrame: [date, stock_id, stock_name, foreign_buy, foreign_sell, 
                        foreign_net, trust_buy, trust_sell, trust_net,
                        dealer_self_buy, dealer_self_sell, dealer_self_net,
                        dealer_hedge_buy, dealer_hedge_sell, dealer_hedge_net,
                        total_net]
            單位：股
        """
        if not HAS_REQUESTS:
            print("[TWSEDataFetcher] requests 未安裝")
            return None
        
        cache_key = f"inst_{date_str}"
        if cache_key in self._cache:
            df = self._cache[cache_key]
            if stock_filter:
                df = df[df['stock_id'].isin(stock_filter)]
            return df
        
        url = f"{self.BASE_URL}/fund/T86"
        params = {'date': date_str, 'response': 'json', 'selectType': 'ALL'}
        
        for attempt in range(self.MAX_RETRIES):
            try:
                r = self.session.get(url, params=params, timeout=15)
                data = r.json()
                
                if data.get('stat') != 'OK':
                    # 非交易日或無資料
                    return None
                
                rows = data.get('data', [])
                if len(rows) < 10:
                    # 可能是 partial data (default selectType)
                    # 嘗試重新抓取
                    if attempt == 0:
                        time.sleep(1)
                        continue
                    return None
                
                records = []
                for row in rows:
                    try:
                        records.append({
                            'date': date_str,
                            'stock_id': row[0].strip(),
                            'stock_name': row[1].strip(),
                            'foreign_buy': self._parse_int(row[2]),
                            'foreign_sell': self._parse_int(row[3]),
                            'foreign_net': self._parse_int(row[4]),
                            'foreign_ib_buy': self._parse_int(row[5]),
                            'foreign_ib_sell': self._parse_int(row[6]),
                            'foreign_ib_net': self._parse_int(row[7]),
                            'trust_buy': self._parse_int(row[8]),
                            'trust_sell': self._parse_int(row[9]),
                            'trust_net': self._parse_int(row[10]),
                            'dealer_self_buy': self._parse_int(row[12]),
                            'dealer_self_sell': self._parse_int(row[13]),
                            'dealer_self_net': self._parse_int(row[14]),
                            'dealer_hedge_buy': self._parse_int(row[15]),
                            'dealer_hedge_sell': self._parse_int(row[16]),
                            'dealer_hedge_net': self._parse_int(row[17]),
                            'total_net': self._parse_int(row[18]),
                        })
                    except (IndexError, ValueError) as e:
                        continue
                
                df = pd.DataFrame(records)
                df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
                
                self._cache[cache_key] = df
                
                if stock_filter:
                    df = df[df['stock_id'].isin(stock_filter)]
                
                return df
                
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(2)
                else:
                    print(f"[TWSEDataFetcher] T86 抓取失敗 {date_str}: {e}")
                    return None
        
        return None
    
    def fetch_inst_range(self, start_date: str, end_date: str,
                         stock_filter: List[str] = None,
                         show_progress: bool = True) -> pd.DataFrame:
        """抓取日期區間的三大法人買賣超
        
        Args:
            start_date: YYYYMMDD
            end_date: YYYYMMDD
            stock_filter: 只保留特定股票
            show_progress: 是否顯示進度
        """
        start = datetime.strptime(start_date, '%Y%m%d')
        end = datetime.strptime(end_date, '%Y%m%d')
        
        all_dfs = []
        current = start
        success_days = 0
        total_days = 0
        
        while current <= end:
            # 跳過週末
            if current.weekday() < 5:
                date_str = current.strftime('%Y%m%d')
                total_days += 1
                
                df = self.fetch_inst_daily(date_str, stock_filter=stock_filter)
                if df is not None and len(df) > 0:
                    all_dfs.append(df)
                    success_days += 1
                
                if show_progress and total_days % 10 == 0:
                    print(f"  法人資料: {success_days}/{total_days} 天成功, "
                          f"最新={date_str}")
                
                time.sleep(self.request_delay)
            
            current += timedelta(days=1)
        
        if not all_dfs:
            print(f"[TWSEDataFetcher] 法人資料全部抓取失敗 ({start_date}~{end_date})")
            return pd.DataFrame()
        
        result = pd.concat(all_dfs, ignore_index=True)
        result = result.sort_values(['stock_id', 'date']).reset_index(drop=True)
        
        if show_progress:
            print(f"  法人資料完成: {success_days} 天, {len(result)} 筆")
        
        return result
    
    # ============================================================
    # 2. 融資融券 (MI_MARGN)
    # ============================================================
    
    def fetch_margin_daily(self, date_str: str,
                           stock_filter: List[str] = None) -> Optional[pd.DataFrame]:
        """抓取單日融資融券餘額
        
        Returns:
            DataFrame: [date, stock_id, stock_name,
                        margin_buy, margin_sell, margin_repay,
                        margin_prev_bal, margin_balance, margin_limit,
                        short_buy, short_sell, short_repay,
                        short_prev_bal, short_balance, short_limit,
                        offset, note]
        """
        if not HAS_REQUESTS:
            return None
        
        cache_key = f"margin_{date_str}"
        if cache_key in self._cache:
            df = self._cache[cache_key]
            if stock_filter:
                df = df[df['stock_id'].isin(stock_filter)]
            return df
        
        url = f"{self.BASE_URL}/marginTrading/MI_MARGN"
        params = {'date': date_str, 'response': 'json', 'selectType': 'STOCK'}
        
        for attempt in range(self.MAX_RETRIES):
            try:
                r = self.session.get(url, params=params, timeout=15)
                data = r.json()
                
                if data.get('stat') != 'OK':
                    return None
                
                tables = data.get('tables', [])
                # 個股資料在 table[1]
                if len(tables) < 2 or 'data' not in tables[1]:
                    return None
                
                rows = tables[1].get('data', [])
                fields = tables[1].get('fields', [])
                
                records = []
                for row in rows:
                    try:
                        records.append({
                            'date': date_str,
                            'stock_id': row[0].strip(),
                            'stock_name': row[1].strip(),
                            'margin_buy': self._parse_int(row[2]),
                            'margin_sell': self._parse_int(row[3]),
                            'margin_repay': self._parse_int(row[4]),
                            'margin_prev_bal': self._parse_int(row[5]),
                            'margin_balance': self._parse_int(row[6]),
                            'margin_limit': self._parse_int(row[7]),
                            'short_buy': self._parse_int(row[8]),
                            'short_sell': self._parse_int(row[9]),
                            'short_repay': self._parse_int(row[10]),
                            'short_prev_bal': self._parse_int(row[11]),
                            'short_balance': self._parse_int(row[12]),
                            'short_limit': self._parse_int(row[13]),
                            'offset': self._parse_int(row[14]) if len(row) > 14 else 0,
                            'note': row[15].strip() if len(row) > 15 else '',
                        })
                    except (IndexError, ValueError):
                        continue
                
                df = pd.DataFrame(records)
                df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
                
                self._cache[cache_key] = df
                
                if stock_filter:
                    df = df[df['stock_id'].isin(stock_filter)]
                
                return df
                
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(2)
                else:
                    print(f"[TWSEDataFetcher] MI_MARGN 抓取失敗 {date_str}: {e}")
                    return None
        
        return None
    
    def fetch_margin_range(self, start_date: str, end_date: str,
                           stock_filter: List[str] = None,
                           show_progress: bool = True) -> pd.DataFrame:
        """抓取日期區間的融資融券餘額"""
        start = datetime.strptime(start_date, '%Y%m%d')
        end = datetime.strptime(end_date, '%Y%m%d')
        
        all_dfs = []
        current = start
        success_days = 0
        total_days = 0
        
        while current <= end:
            if current.weekday() < 5:
                date_str = current.strftime('%Y%m%d')
                total_days += 1
                
                df = self.fetch_margin_daily(date_str, stock_filter=stock_filter)
                if df is not None and len(df) > 0:
                    all_dfs.append(df)
                    success_days += 1
                
                if show_progress and total_days % 10 == 0:
                    print(f"  融資融券: {success_days}/{total_days} 天成功")
                
                time.sleep(self.request_delay)
            
            current += timedelta(days=1)
        
        if not all_dfs:
            return pd.DataFrame()
        
        result = pd.concat(all_dfs, ignore_index=True)
        result = result.sort_values(['stock_id', 'date']).reset_index(drop=True)
        
        if show_progress:
            print(f"  融資融券完成: {success_days} 天, {len(result)} 筆")
        
        return result
    
    # ============================================================
    # 3. OHLCV 日 K 資料
    # ============================================================
    
    def fetch_ohlcv_yfinance(self, stock_list: List[str], 
                              period: str = "1y") -> pd.DataFrame:
        """使用 yfinance 抓取 OHLCV
        
        Args:
            stock_list: 台股代碼 (e.g., ['2330', '2454'])
            period: yfinance 期間 (1d/5d/1mo/3mo/6mo/1y/2y/5y/max)
        """
        if not HAS_YFINANCE:
            print("[TWSEDataFetcher] yfinance 未安裝")
            return pd.DataFrame()
        
        all_dfs = []
        for sid in stock_list:
            try:
                ticker = yf.Ticker(f"{sid}.TW")
                hist = ticker.history(period=period)
                if len(hist) == 0:
                    continue
                
                hist = hist.reset_index()
                hist['stock_id'] = sid
                # Standardize column names
                col_map = {
                    'Date': 'date', 'Open': 'open', 'High': 'high',
                    'Low': 'low', 'Close': 'close', 'Volume': 'volume',
                }
                hist = hist.rename(columns=col_map)
                hist = hist[['date', 'stock_id', 'open', 'high', 'low', 'close', 'volume']]
                
                # volume 轉張 (yfinance 給的是股數)
                hist['volume'] = hist['volume'] // 1000
                
                all_dfs.append(hist)
                time.sleep(0.3)
            except Exception as e:
                print(f"  [SKIP] {sid}: {e}")
                continue
        
        if not all_dfs:
            return pd.DataFrame()
        
        result = pd.concat(all_dfs, ignore_index=True)
        result = result.sort_values(['stock_id', 'date']).reset_index(drop=True)
        return result
    
    def fetch_ohlcv_twstock(self, stock_list: List[str], 
                             days: int = 250) -> pd.DataFrame:
        """使用 twstock 抓取 OHLCV (月度批次)
        
        Args:
            stock_list: 台股代碼
            days: 回溯天數
        """
        if not HAS_TWSTOCK:
            print("[TWSEDataFetcher] twstock 未安裝")
            return pd.DataFrame()
        
        all_dfs = []
        for sid in stock_list:
            try:
                stock = twstock.Stock(sid)
                months_needed = (days // 22) + 2
                now = datetime.now()
                data = []
                
                for m_offset in range(months_needed):
                    total_month = now.year * 12 + (now.month - 1) - m_offset
                    y = total_month // 12
                    m = (total_month % 12) + 1
                    try:
                        monthly = stock.fetch(y, m)
                        data.extend(monthly)
                    except Exception:
                        continue
                
                records = []
                for d in data:
                    records.append({
                        'date': d.date,
                        'stock_id': sid,
                        'open': d.open,
                        'high': d.high,
                        'low': d.low,
                        'close': d.close,
                        'volume': d.capacity,  # 單位：張
                    })
                
                if records:
                    all_dfs.append(pd.DataFrame(records))
                    
            except Exception as e:
                print(f"  [SKIP] {sid}: {e}")
                continue
        
        if not all_dfs:
            return pd.DataFrame()
        
        result = pd.concat(all_dfs, ignore_index=True)

        result = result.sort_values(['stock_id', 'date']).reset_index(drop=True)
        return result

    # ============================================================
    # 3b. 期貨三大法人未平倉量 (FinMind)
    # ============================================================

    def fetch_futures_oi(self, start_date: str = None, end_date: str = None,
                         days: int = 120,
                         futures_ids: List[str] = None,
                         show_progress: bool = True) -> pd.DataFrame:
        """抓取期貨三大法人未平倉量 + 散戶未平倉量 (FinMind)

        資料來源: FinMind taiwan_futures_institutional_investors
        期貨代碼: TX=大台, MTX=小台

        Args:
            start_date: 起始日期 (YYYY-MM-DD or YYYYMMDD)
            end_date: 結束日期
            days: 若未指定日期，往前推天數
            futures_ids: 期貨代碼清單，預設 ['TX', 'MTX']

        Returns:
            DataFrame with columns:
            [date, futures_id, foreign_long_oi, foreign_short_oi,
             trust_long_oi, trust_short_oi,
             dealer_long_oi, dealer_short_oi,
             inst_net_oi, retail_net_oi]
        """
        if futures_ids is None:
            futures_ids = ['TX', 'MTX']

        if not HAS_FINMIND:
            if show_progress:
                print("  [警告] FinMind 未安裝，無法取得期貨 OI 資料")
            return pd.DataFrame()

        # 日期處理
        if end_date is None:
            end_dt = datetime.now()
        else:
            end_dt = datetime.strptime(end_date.replace('-', ''), '%Y%m%d')

        if start_date is None:
            start_dt = end_dt - timedelta(days=days)
        else:
            start_dt = datetime.strptime(start_date.replace('-', ''), '%Y%m%d')

        start_str = start_dt.strftime('%Y-%m-%d')
        end_str = end_dt.strftime('%Y-%m-%d')

        dl = FinMindLoader()
        all_dfs = []

        for fid in futures_ids:
            if show_progress:
                print(f"  下載 {fid} 期貨法人 OI ({start_str} ~ {end_str})...")

            try:
                df = dl.taiwan_futures_institutional_investors(
                    futures_id=fid,
                    start_date=start_str,
                    end_date=end_str,
                )
            except Exception as e:
                if show_progress:
                    print(f"    {fid} 下載失敗: {e}")
                continue

            if df is None or len(df) == 0:
                if show_progress:
                    print(f"    {fid}: 無資料")
                continue

            # 樞紐: date x institutional_investor → long/short OI
            pivot_long = df.pivot_table(
                index='date', columns='institutional_investors',
                values='long_open_interest_balance_volume', aggfunc='sum')
            pivot_short = df.pivot_table(
                index='date', columns='institutional_investors',
                values='short_open_interest_balance_volume', aggfunc='sum')

            # 確保三大法人欄位存在
            for col in ['外資', '投信', '自營商']:
                if col not in pivot_long.columns:
                    pivot_long[col] = 0
                if col not in pivot_short.columns:
                    pivot_short[col] = 0

            # 重建為整齊格式
            out = pd.DataFrame()
            out['date'] = pivot_long.index
            out['futures_id'] = fid
            out['foreign_long_oi'] = pivot_long['外資'].values
            out['foreign_short_oi'] = pivot_short['外資'].values
            out['trust_long_oi'] = pivot_long['投信'].values
            out['trust_short_oi'] = pivot_short['投信'].values
            out['dealer_long_oi'] = pivot_long['自營商'].values
            out['dealer_short_oi'] = pivot_short['自營商'].values

            # 三大法人淨未平倉 = (多 - 空) 合計
            inst_total_long = pivot_long.sum(axis=1).values
            inst_total_short = pivot_short.sum(axis=1).values
            out['inst_net_oi'] = inst_total_long - inst_total_short

            # 散戶淨未平倉 = -三大法人淨未平倉 (零和市場)
            out['retail_net_oi'] = -out['inst_net_oi']

            # 散戶多/空 OI (需搭配 fetch_futures_daily 計算 total OI)
            out['retail_long_oi'] = 0
            out['retail_short_oi'] = 0

            all_dfs.append(out)

            if show_progress:
                print(f"    {fid}: {len(out)} 天")

        if not all_dfs:
            return pd.DataFrame()

        result = pd.concat(all_dfs, ignore_index=True)
        result['date'] = pd.to_datetime(result['date'])
        result = result.sort_values(['futures_id', 'date']).reset_index(drop=True)

        if show_progress:
            print(f"  期貨 OI 完成: {len(result)} 筆")
        return result

    def fetch_futures_daily(self, start_date: str = None, end_date: str = None,
                            days: int = 120,
                            futures_ids: List[str] = None,
                            show_progress: bool = True) -> pd.DataFrame:
        """抓取期貨日K + 未平倉量 (FinMind)

        用於計算散戶未平倉量 = total OI - 三大法人 OI

        Returns:
            DataFrame: [date, futures_id, contract_date, open, high, low, close,
                        volume, open_interest, trading_session]
        """
        if futures_ids is None:
            futures_ids = ['TX', 'MTX']

        if not HAS_FINMIND:
            return pd.DataFrame()

        if end_date is None:
            end_dt = datetime.now()
        else:
            end_dt = datetime.strptime(end_date.replace('-', ''), '%Y%m%d')

        if start_date is None:
            start_dt = end_dt - timedelta(days=days)
        else:
            start_dt = datetime.strptime(start_date.replace('-', ''), '%Y%m%d')

        start_str = start_dt.strftime('%Y-%m-%d')
        end_str = end_dt.strftime('%Y-%m-%d')

        dl = FinMindLoader()
        all_dfs = []

        for fid in futures_ids:
            try:
                df = dl.taiwan_futures_daily(
                    futures_id=fid,
                    start_date=start_str,
                    end_date=end_str,
                )
            except Exception as e:
                continue

            if df is None or len(df) == 0:
                continue

            # 只取近月契約 (最活躍) & 一般交易時段
            df_active = df[df['trading_session'] == '一般'].copy()
            if len(df_active) == 0:
                # fallback: 取每日期貨各契約 OI 合計
                df_agg = df.groupby('date').agg({
                    'open': 'first', 'max': 'max', 'min': 'min',
                    'close': 'last', 'volume': 'sum',
                    'open_interest': 'sum',
                }).reset_index()
                df_agg['futures_id'] = fid
                all_dfs.append(df_agg)
            else:
                all_dfs.append(df_active)

        if not all_dfs:
            return pd.DataFrame()

        result = pd.concat(all_dfs, ignore_index=True)
        if 'max' in result.columns:
            result = result.rename(columns={'max': 'high'})
        if 'min' in result.columns:
            result = result.rename(columns={'min': 'low'})
        result['date'] = pd.to_datetime(result['date'])
        return result.sort_values(['futures_id', 'date']).reset_index(drop=True)

    # ============================================================
    # 3c. 美股指數 (yfinance)
    # ============================================================

    def fetch_us_indices(self, period: str = "1y",
                         indices: Dict[str, str] = None,
                         show_progress: bool = True) -> pd.DataFrame:
        """抓取美股三大指數歷史資料 (yfinance)

        Args:
            period: yfinance 期間 ('1mo', '3mo', '6mo', '1y', '2y')
            indices: {顯示名: yfinance ticker}，預設三大指數

        Returns:
            DataFrame: [date, index_name, open, high, low, close, volume]
        """
        if indices is None:
            indices = {
                'Nasdaq': '^IXIC',
                'SP500': '^GSPC',
                'DowJones': '^DJI',
            }

        if not HAS_YFINANCE:
            if show_progress:
                print("  [警告] yfinance 未安裝，無法取得美股指數")
            return pd.DataFrame()

        all_dfs = []
        for name, ticker in indices.items():
            if show_progress:
                print(f"  下載 {name} ({ticker})...")

            for attempt in range(3):
                try:
                    t = yf.Ticker(ticker)
                    hist = t.history(period=period)
                    if len(hist) > 0:
                        hist = hist.reset_index()
                        hist['index_name'] = name
                        # 統一欄位名稱
                        col_map = {}
                        for old, new in [('Date', 'date'), ('Open', 'open'),
                                         ('High', 'high'), ('Low', 'low'),
                                         ('Close', 'close'), ('Volume', 'volume')]:
                            if old in hist.columns:
                                col_map[old] = new
                        hist = hist.rename(columns=col_map)

                        keep = ['date', 'index_name', 'open', 'high', 'low', 'close', 'volume']
                        hist = hist[[c for c in keep if c in hist.columns]].copy()
                        all_dfs.append(hist)
                        if show_progress:
                            last_close = float(hist['close'].iloc[-1])
                            print(f"    {name}: {len(hist)} 筆, close={last_close:.2f}")
                        break
                    else:
                        if show_progress:
                            print(f"    {name}: 無資料 (attempt {attempt+1})")
                        time.sleep(3 * (attempt + 1))
                except Exception as e:
                    if show_progress:
                        print(f"    {name}: ERROR {e} (attempt {attempt+1})")
                    time.sleep(5 * (attempt + 1))

        if not all_dfs:
            return pd.DataFrame()

        result = pd.concat(all_dfs, ignore_index=True)
        result['date'] = pd.to_datetime(result['date'])
        return result.sort_values(['index_name', 'date']).reset_index(drop=True)

    # ============================================================
    # 4. 整合：OHLCV + 法人 + 融資融券 + 期貨 + 美股
    # ============================================================
    def fetch_full_history(self, stock_list: List[str], 
                           days: int = 250,
                           use_yfinance: bool = True,
                           include_futures: bool = True,
                           include_us: bool = True,
                           show_progress: bool = True) -> Dict[str, pd.DataFrame]:
        """抓取完整歷史資料：OHLCV + 三大法人 + 融資融券 + 期貨 + 美股

        Returns:
            {
                'ohlcv': DataFrame,   # 日K
                'inst': DataFrame,    # 三大法人買賣超
                'margin': DataFrame,  # 融資融券
                'futures_oi': DataFrame,  # 期貨三大法人未平倉量 (optional)
                'us_indices': DataFrame, # 美股三大指數 (optional)
            }
        """
        if show_progress:
            print("=" * 60)
            print(f"  台股歷史資料下載 ({len(stock_list)} 檔, {days} 天)")
            print("=" * 60)

        # 1. OHLCV
        if show_progress:
            print("\n[1/5] 下載 OHLCV...")

        if use_yfinance and HAS_YFINANCE:
            period_map = {30: '1mo', 90: '3mo', 180: '6mo', 365: '1y', 730: '2y'}
            period = '1y'
            for d, p in sorted(period_map.items()):
                if days <= d:
                    period = p
                    break
            ohlcv = self.fetch_ohlcv_yfinance(stock_list, period=period)
        elif HAS_TWSTOCK:
            ohlcv = self.fetch_ohlcv_twstock(stock_list, days=days)
        else:
            ohlcv = pd.DataFrame()

        if show_progress and len(ohlcv) > 0:
            print(f"  OHLCV: {len(ohlcv)} 筆, {ohlcv['stock_id'].nunique()} 檔")

        # 2. 三大法人
        if show_progress:
            print("\n[2/5] 下載三大法人買賣超...")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        inst = self.fetch_inst_range(
            start_date.strftime('%Y%m%d'),
            end_date.strftime('%Y%m%d'),
            stock_filter=stock_list,
            show_progress=show_progress,
        )

        # 3. 融資融券
        if show_progress:
            print("\n[3/5] 下載融資融券...")

        margin = self.fetch_margin_range(
            start_date.strftime('%Y%m%d'),
            end_date.strftime('%Y%m%d'),
            stock_filter=stock_list,
            show_progress=show_progress,
        )

        # 4. 期貨三大法人未平倉量
        futures_oi = pd.DataFrame()
        if include_futures:
            if show_progress:
                print("\n[4/5] 下載期貨法人未平倉量...")
            futures_oi = self.fetch_futures_oi(
                days=days, show_progress=show_progress)

        # 5. 美股三大指數
        us_indices = pd.DataFrame()
        if include_us:
            if show_progress:
                print("\n[5/5] 下載美股三大指數...")
            us_indices = self.fetch_us_indices(
                period='1y', show_progress=show_progress)

        result = {
            'ohlcv': ohlcv,
            'inst': inst,
            'margin': margin,
            'futures_oi': futures_oi,
            'us_indices': us_indices,
        }

        if show_progress:
            print(f"\n--- 下載完成 ---")
            print(f"  OHLCV: {len(ohlcv)} 筆")
            print(f"  法人: {len(inst)} 筆")
            print(f"  融資融券: {len(margin)} 筆")
            print(f"  期貨OI: {len(futures_oi)} 筆")
            print(f"  美股: {len(us_indices)} 筆")

        return result
    
    # ============================================================
    # 5. 合併 OHLCV + 法人 + 融資融券 → 單一 DataFrame
    # ============================================================
    
    @staticmethod
    def merge_data(ohlcv: pd.DataFrame, 
                   inst: pd.DataFrame = None,
                   margin: pd.DataFrame = None,
                   futures_oi: pd.DataFrame = None,
                   us_indices: pd.DataFrame = None) -> pd.DataFrame:
        """合併 OHLCV + 法人 + 融資融券 + 期貨 + 美股為單一 DataFrame

        合併鍵: [date, stock_id]（期貨/美股按 date cross-join）
        """
        if len(ohlcv) == 0:
            return pd.DataFrame()

        df = ohlcv.copy()
        df['date'] = pd.to_datetime(df['date'])

        # 合併法人資料
        if inst is not None and len(inst) > 0:
            inst = inst.copy()
            inst['date'] = pd.to_datetime(inst['date'])
            inst_cols = ['date', 'stock_id', 'foreign_net', 'trust_net', 
                         'dealer_self_net', 'dealer_hedge_net', 'total_net']
            inst_merge = inst[[c for c in inst_cols if c in inst.columns]]
            rename_map = {
                'foreign_net': 'inst_foreign_net',
                'trust_net': 'inst_trust_net',
                'dealer_self_net': 'inst_dealer_self_net',
                'dealer_hedge_net': 'inst_dealer_hedge_net',
                'total_net': 'inst_total_net',
            }
            inst_merge = inst_merge.rename(columns=rename_map)
            df = df.merge(inst_merge, on=['date', 'stock_id'], how='left')

        # 合併融資融券
        if margin is not None and len(margin) > 0:
            margin = margin.copy()
            margin['date'] = pd.to_datetime(margin['date'])
            margin_cols = ['date', 'stock_id', 'margin_buy', 'margin_sell',
                           'margin_balance', 'short_buy', 'short_sell', 
                           'short_balance']
            margin_merge = margin[[c for c in margin_cols if c in margin.columns]]
            df = df.merge(margin_merge, on=['date', 'stock_id'], how='left')

        # 合併期貨 OI (按 date merge，不按 stock_id)
        if futures_oi is not None and len(futures_oi) > 0:
            foi = futures_oi.copy()
            foi['date'] = pd.to_datetime(foi['date'])
            # 為大台/小台分別建立欄位
            for fid in foi['futures_id'].unique():
                fid_data = foi[foi['futures_id'] == fid].copy()
                fid_data = fid_data.drop(columns=['futures_id'])
                # 加前綴避免衄位衝突
                prefix = f"tx_" if fid == 'TX' else f"mtx_"
                rename = {c: prefix + c for c in fid_data.columns if c != 'date'}
                fid_data = fid_data.rename(columns=rename)
                df = df.merge(fid_data, on='date', how='left')

        # 合併美股指數 (按 date merge，每個指數分欄位)
        if us_indices is not None and len(us_indices) > 0:
            us = us_indices.copy()
            us['date'] = pd.to_datetime(us['date'])
            for idx_name in us['index_name'].unique():
                idx_data = us[us['index_name'] == idx_name][['date', 'close']].copy()
                prefix = idx_name.lower() + "_"
                idx_data = idx_data.rename(columns={'close': prefix + 'close'})
                df = df.merge(idx_data, on='date', how='left')

        # 填充缺失值
        fill_cols = [c for c in df.columns if c not in ('date', 'stock_id', 'stock_name')]
        for c in fill_cols:
            if df[c].dtype in (np.float64, np.int64, float, int):
                df[c] = df[c].fillna(0)

        return df
    
    # ============================================================
    # 6. 生成 Kaggle 訓練資料集
    # ============================================================
    
    def generate_kaggle_dataset(self, stock_list: List[str], 
                                days: int = 500,
                                include_futures: bool = True,
                                include_us: bool = True,
                                output_dir: str = '/tmp/kaggle-dataset') -> str:
        """生成 Kaggle 訓練資料集 (含法人+融資融券+期貨+美股)

        輸出檔案:
            - twstock_daily.csv: OHLCV + 法人 + 融資融券 + 期貨 + 美股
            - inst_data.csv: 三大法人買賣超 (獨立檔)
            - margin_data.csv: 融資融券 (獨立檔)
            - futures_oi.csv: 期貨法人未平倉量 (獨立檔)
            - us_indices.csv: 美股三大指數 (獨立檔)
            - dataset-metadata.json: Kaggle dataset 配置

        Returns:
            output_dir
        """
        import os
        os.makedirs(output_dir, exist_ok=True)

        print(f"生成 Kaggle 資料集: {len(stock_list)} 檔, {days} 天")

        # 抓取完整資料
        data = self.fetch_full_history(
            stock_list, days=days, show_progress=True,
            include_futures=include_futures, include_us=include_us)

        ohlcv = data['ohlcv']
        inst = data['inst']
        margin = data['margin']
        futures_oi = data.get('futures_oi', pd.DataFrame())
        us_indices = data.get('us_indices', pd.DataFrame())

        # 合併為完整日K
        full_df = self.merge_data(ohlcv, inst, margin, futures_oi, us_indices)

        # 儲存 CSV
        ohlcv_path = os.path.join(output_dir, 'twstock_daily.csv')
        full_df.to_csv(ohlcv_path, index=False)
        print(f"  twstock_daily.csv: {len(full_df)} 筆")

        # 獨立法人資料
        if len(inst) > 0:
            inst_path = os.path.join(output_dir, 'inst_data.csv')
            inst.to_csv(inst_path, index=False)
            print(f"  inst_data.csv: {len(inst)} 筆")

        # 獨立融資融券
        if len(margin) > 0:
            margin_path = os.path.join(output_dir, 'margin_data.csv')
            margin.to_csv(margin_path, index=False)
            print(f"  margin_data.csv: {len(margin)} 筆")

        # 獨立期貨 OI
        if len(futures_oi) > 0:
            foi_path = os.path.join(output_dir, 'futures_oi.csv')
            futures_oi.to_csv(foi_path, index=False)
            print(f"  futures_oi.csv: {len(futures_oi)} 筆")

        # 獨立美股指數
        if len(us_indices) > 0:
            us_path = os.path.join(output_dir, 'us_indices.csv')
            us_indices.to_csv(us_path, index=False)
            print(f"  us_indices.csv: {len(us_indices)} 筆")
        
        # dataset-metadata.json
        metadata = {
            "title": "twstock-grpo-training-data-v2",
            "id": "mhhuang14/twstock-grpo-training-data-v2",
            "licenses": [{"name": "CC0-1.0"}],
        }
        meta_path = os.path.join(output_dir, 'dataset-metadata.json')
        with open(meta_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"\n資料集已儲存至: {output_dir}")
        return output_dir
    
    # ============================================================
    # 輔助方法
    # ============================================================
    
    @staticmethod
    def _parse_int(s) -> int:
        """解析 TWSE 格式的數字字串 (含千分位逗號)"""
        if isinstance(s, (int, float)):
            return int(s) if not np.isnan(s) else 0
        if isinstance(s, str):
            s = s.strip().replace(',', '').replace(' ', '')
            if s in ('', '-', 'N/A'):
                return 0
            try:
                return int(float(s))
            except ValueError:
                return 0
        return 0
    
    @staticmethod
    def get_trading_days(start_date: str, end_date: str) -> List[str]:
        """取得交易日清單 (排除週末，不排除國定假日)"""
        start = datetime.strptime(start_date, '%Y%m%d')
        end = datetime.strptime(end_date, '%Y%m%d')
        days = []
        current = start
        while current <= end:
            if current.weekday() < 5:
                days.append(current.strftime('%Y%m%d'))
            current += timedelta(days=1)
        return days


# ============================================================
# 快速測試
# ============================================================

if __name__ == "__main__":
    fetcher = TWSEDataFetcher()
    
    # 測試單日法人
    print("--- T86 三大法人 ---")
    df = fetcher.fetch_inst_daily('20250523', stock_filter=['2330', '2454', '1301', '2882'])
    if df is not None:
        print(df[['stock_id', 'stock_name', 'foreign_net', 'trust_net', 'total_net']])
    
    # 測試單日融資融券
    print("\n--- MI_MARGN 融資融券 ---")
    df2 = fetcher.fetch_margin_daily('20250523', stock_filter=['2330', '2454', '1301', '2882'])
    if df2 is not None:
        print(df2[['stock_id', 'stock_name', 'margin_balance', 'short_balance']])
    
    # 測試 yfinance
    print("\n--- yfinance OHLCV ---")
    df3 = fetcher.fetch_ohlcv_yfinance(['2330', '2454'], period='1mo')
    if len(df3) > 0:
        print(f"  {len(df3)} 筆, 最新 5 筆:")
        print(df3.tail(5))
