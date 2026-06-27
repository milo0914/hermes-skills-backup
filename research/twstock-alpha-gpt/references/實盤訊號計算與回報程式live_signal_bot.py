"""💡 程式碼運作原理解析：
STRATEGIES 字典：這是您與 AI 訓練結果的橋樑。您只需要把 best_strategy_per_regime.json 裡面的 formula_tokens 數字陣列貼進來，虛擬機就能完美還原 AI 的邏輯。
get_live_features 函數：
它會自動往前推 90 天（確保扣除假日後，有足夠的 60 個交易日）。
透過 FinMind REST API 抓取現貨、期貨、美股資料（避開了 Kaggle 上 pip install finmind 的套件衝突問題）。
餵給 TWFeatureEngineer，算出與訓練時一模一樣的 Z-score 正規化特徵。
StackVM.execute：將算好的 60 天特徵陣列丟入虛擬機，算出這 60 天的訊號。
signal_array[-1]：我們只取陣列的最後一筆，這就是「今天」的最新訊號！並套用 np.tanh 將其壓縮到 -1 到 1 之間，方便您判讀。
您只要把這支程式放在電腦上跑，每天下午 15:30，您的 Line 就會準時收到 AI 幫您算好的最新多空訊號了！"""

import time
import requests
import schedule
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# ==========================================
# 1. 系統設定與公式載入
# ==========================================
import requests
import json

# ==========================================
# 1. 系統設定與 LINE Messaging API
# ==========================================
# 請填入您剛剛在 LINE Developers 後台取得的兩把鑰匙
LINE_CHANNEL_ACCESS_TOKEN = "HMpxZlFIjfyXqhqdMmTcqbZgFE3kgxGUxuD5d7nR1zLzMA3V7wmbDWCu8tp5xV3NA0MDSzTS2AJ9kqZ4E5nQ8xms2CNCvVZjgg0xogt32h3fhK7HUpC6qDlRw4xMX3jVhlggBt8KwzheinFiWERy5QdB04t89/1O/w1cDnyilFU="
LINE_USER_ID = "U68fc2231c9c0deadca04b6d8e8c0daef"

def send_line_message(message):
    """使用 LINE Messaging API 發送推播訊息"""
    if not LINE_CHANNEL_ACCESS_TOKEN or LINE_CHANNEL_ACCESS_TOKEN == "請填入您的_Channel_Access_Token":
        print(f"[本地印出]\n{message}")
        return
    
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    
    # Messaging API 的資料格式 (JSON)
    data = {
        "to": LINE_USER_ID,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    
    try:
        resp = requests.post(url, headers=headers, json=data)
        if resp.status_code == 200:
            print("✅ LINE 訊息發送成功！")
        else:
            print(f"❌ LINE 發送失敗: 狀態碼 {resp.status_code}, 錯誤訊息: {resp.text}")
    except Exception as e:
        print(f"❌ LINE 發送發生例外錯誤: {e}")

# 測試發送 (您可以單獨執行這行來測試是否設定成功)
# send_line_message("測試：AI Dig Money 機器人已成功連線！")

# 💡 請打開您訓練完的 best_strategy_per_regime.json
# 將 mid_cap_tech 和 traditional 的 "formula_tokens" 陣列複製貼到這裡：
STRATEGIES = {
    "mid_cap_tech": {
        "stocks": ["2303", "2317", "2382", "2454", "3008", "3034", "3711"], # 您想監控的科技股 TSMSC、鴻海、廣達、聯發科
        # 範例 Token，請替換為您 JSON 檔中的真實陣列
        "tokens": [11, 18, 27, 1, 31, 27, 30, 28, 27, 23, 21, 31, 31, 22, 23] 
    },
    "traditional": {
        "stocks": ["1301", "1101", "2002"], # 您想監控的傳產股 台塑、台泥、中鋼
        # 範例 Token，請替換為您 JSON 檔中的真實陣列
        "tokens": [16, 17, 31, 16, 33, 23, 18, 33, 32, 32, 24, 17, 33, 29]
    }
}

FEATURE_NAMES = (
    "RET", "LIQ_SCORE", "PRESSURE", "FOMO", "DEV", "LOG_VOL",
    "INST_FLOW", "MARGIN_PRESS", "FIVE_DAY_HIGH", "VOL_BREAKOUT",
    "CVD_PROXY", "ABSORPTION", "SURF_ENTRY", "ATR", "CLOSE_POS", "MOM_REV",
    "TX_INST_NET_OI", "MTX_RETAIL_OI", "TX_MTX_SPREAD",
    "NASDAQ_CLOSE", "SP500_CLOSE", "DOWJONES_CLOSE",
)

# ==========================================
# 2. StackVM 虛擬機 (用於執行公式)
# ==========================================
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
                if len(stack) < [2, 2, 2, 2, 1, 1, 1, 3, 1, 1, 1, 1][op_idx]: return None
                if op_idx in [4, 5, 6, 8, 9, 10, 11]: # Unary
                    a = stack.pop()
                    if op_idx == 4: res = -a
                    elif op_idx == 5: res = np.abs(a)
                    elif op_idx == 6: res = np.sign(a)
                    elif op_idx == 8: res = np.where(np.abs((a - np.mean(a)) / (np.std(a) + 1e-6)) > 3, np.sign(a), 0)
                    elif op_idx == 9: res = 0.8 * a + 0.6 * np.roll(a, 1)
                    elif op_idx == 10: res = np.roll(a, 1)
                    elif op_idx == 11: res = np.maximum(np.maximum(a, np.roll(a, 1)), np.roll(a, 2))
                    stack.append(self._safe_math(res))
                elif op_idx in [0, 1, 2, 3]: # Binary
                    b, a = stack.pop(), stack.pop()
                    if op_idx == 0: res = a + b
                    elif op_idx == 1: res = a - b
                    elif op_idx == 2: res = a * b
                    elif op_idx == 3: res = a / np.where(np.abs(b) < 1e-5, 1e-5, b)
                    stack.append(self._safe_math(res))
                elif op_idx == 7: # Ternary (GATE)
                    c, b, a = stack.pop(), stack.pop(), stack.pop()
                    stack.append(self._safe_math(np.where(c > 0, a, b)))
        return stack[0] if len(stack) == 1 else None

# ==========================================
# 3. 資料抓取與特徵工程 (FinMind API)
# ==========================================
def fetch_finmind_data(dataset, data_id, start_date):
    """使用 FinMind REST API 抓取資料 (避開 pip install 衝突)"""
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": dataset, "data_id": data_id, "start_date": start_date}
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("msg") == "success":
            return pd.DataFrame(data.get("data", []))
    except Exception as e:
        print(f"抓取 {dataset} {data_id} 失敗: {e}")
    return pd.DataFrame()

def get_live_features(stock_list):
    """抓取過去 90 天資料，確保有足夠的 60 個交易日算 Z-score"""
    start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    
    # 1. 抓取 OHLCV
    df_list = []
    for stock_id in stock_list:
        raw = fetch_finmind_data("TaiwanStockPrice", stock_id, start_date)
        if not raw.empty:
            raw = raw.rename(columns={"Trading_Volume": "volume", "max": "high", "min": "low"})
            raw["stock_id"] = stock_id
            df_list.append(raw)
    if not df_list: return None
    df = pd.concat(df_list, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])

    # 2. 抓取期貨籌碼 (大台 TX, 小台 MTX)
    # 實戰中需將 FinMind 的外資/投信/自營商加總，此處簡化為直接抓取
    tx_raw = fetch_finmind_data("TaiwanFuturesInstitutionalInvestors", "TX", start_date)
    mtx_raw = fetch_finmind_data("TaiwanFuturesInstitutionalInvestors", "MTX", start_date)
    
    futures_records = []
    for raw, f_id in [(tx_raw, "TX"), (mtx_raw, "MTX")]:
        if not raw.empty:
            # 簡化處理：將外資淨未平倉當作法人代表
            foreign = raw[raw["name"] == "外資及陸資"].copy()
            foreign["futures_id"] = f_id
            foreign["inst_net_oi"] = foreign["long_oi"] - foreign["short_oi"]
            foreign["retail_net_oi"] = -foreign["inst_net_oi"] # 簡化：散戶為法人對手盤
            futures_records.append(foreign[["date", "futures_id", "inst_net_oi", "retail_net_oi"]])
    futures_oi_df = pd.concat(futures_records) if futures_records else None

    # 3. 抓取美股指數
    us_records = []
    for idx_id, idx_name in [("^DJI", "DowJones"), ("^GSPC", "SP500"), ("^IXIC", "Nasdaq")]:
        raw = fetch_finmind_data("USStockPrice", idx_id, start_date)
        if not raw.empty:
            raw["index_name"] = idx_name
            raw["close"] = raw["Close"]
            us_records.append(raw[["date", "index_name", "close"]])
    us_indices_df = pd.concat(us_records) if us_records else None

    # 4. 呼叫特徵工程 (計算 Z-score)
    # 這裡為了簡潔，直接套用您原本的 TWFeatureEngineer.compute_features 邏輯
    # (請確保您原本的 TWFeatureEngineer 類別有被 import 或貼在上方)
    from input_file_0 import TWFeatureEngineer # 假設您的特徵工程存在同目錄
    feat_df = TWFeatureEngineer.compute_features(df, None, None, futures_oi_df, us_indices_df)
    return feat_df

# ==========================================
# 4. 每日排程主程式
# ==========================================
def daily_job():
    today_str = datetime.now().strftime("%Y-%m-%d")
    msg_buffer = [f"\n📊 【AI Dig Money 實盤訊號】 {today_str}"]
    
    try:
        # 收集所有需要監控的股票
        all_stocks = list(set(STRATEGIES["mid_cap_tech"]["stocks"] + STRATEGIES["traditional"]["stocks"]))
        
        print(f"[{today_str}] 正在抓取過去 90 天資料並計算 Z-score...")
        feat_df = get_live_features(all_stocks)
        
        if feat_df is None or feat_df.empty:
            raise ValueError("無法抓取最新行情資料！")

        vm = StackVM()
        
        for regime, config in STRATEGIES.items():
            msg_buffer.append(f"\n🎯 板塊: {regime.upper()}")
            tokens = config["tokens"]
            
            for stock_id in config["stocks"]:
                # 取出該檔股票的資料
                stock_data = feat_df[feat_df["stock_id"] == stock_id].sort_values("date")
                if stock_data.empty: continue
                
                # 將特徵轉為 Tensor (Shape: [N_FEATURES, N_DAYS])
                feat_cols = [stock_data[f].values if f in stock_data.columns else np.zeros(len(stock_data)) for f in FEATURE_NAMES]
                feat_tensor = np.nan_to_num(np.array(feat_cols, dtype=np.float32))
                
                # 執行 AI 公式
                signal_array = vm.execute(tokens, feat_tensor)
                
                if signal_array is not None and len(signal_array) > 0:
                    # 取出「最後一天 (今天)」的訊號，並用 tanh 壓縮到 [-1, 1]
                    today_signal = np.tanh(signal_array[-1])
                    
                    # 判斷多空
                    action = "🟢 強烈看多" if today_signal > 0.5 else "🔴 強烈看空" if today_signal < -0.5 else "⚪ 觀望"
                    msg_buffer.append(f"  - {stock_id}: 訊號 {today_signal:+.2f} ({action})")
                else:
                    msg_buffer.append(f"  - {stock_id}: 訊號計算失敗")

        # 發送 Line 通知
        final_msg = "\n".join(msg_buffer)
        print(final_msg)
        
        if LINE_NOTIFY_TOKEN != "請填入您的_Line_Notify_Token":
            requests.post("https://notify-api.line.me/api/notify", 
                          headers={"Authorization": f"Bearer {LINE_NOTIFY_TOKEN}"}, 
                          data={"message": final_msg})
            
    except Exception as e:
        print(f"執行失敗: {e}")

if __name__ == "__main__":
    print("🚀 AI Dig Money 實盤訊號機器人已啟動！")
    print("設定為每天下午 15:30 自動執行 (等待期交所籌碼公佈)...")
    
    # 設定每天 15:30 執行
    schedule.every().day.at("15:30").do(daily_job)
    
    # 測試用：啟動時先立刻跑一次
    daily_job() 
    
    while True:
        schedule.run_pending()
        time.sleep(60)