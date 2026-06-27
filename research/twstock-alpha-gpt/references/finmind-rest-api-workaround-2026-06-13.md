# FinMind REST API Workaround for Kaggle pydantic Conflict (2026-06-13)

## 問題
`pip install FinMind` 在 Kaggle 環境失敗：
```
metadata-generation-failed: pydantic>=1.6.1,<2.0.0 conflicts with installed pydantic 2.x
ipython>=7.16.1,<8.0.0 conflicts
aiohttp>=3.7.4.post0,<4.0.0 conflicts
```
Kaggle 預裝 pydantic v2，但 FinMind pyproject.toml 鎖定 pydantic<2.0.0。

## 解決方案：直接呼叫 FinMind REST API v4

### API 端點
```
GET https://api.finmindtrade.com/api/v4/data
Params: dataset, data_id, start_date, (token 可選)
```

### 封裝類別
```python
class FinMindAPI:
    """FinMind REST API v4 wrapper — 避開 pydantic 衝突"""
    
    BASE_URL = "https://api.finmindtrade.com/api/v4/data"
    
    def __init__(self, token: str = None):
        self.token = token
        self.session = requests.Session()
        if token:
            self.session.params.update({"token": token})
    
    def fetch(self, dataset: str, data_id: str = None, start_date: str = None) -> pd.DataFrame:
        params = {"dataset": dataset}
        if data_id:
            params["data_id"] = data_id
        if start_date:
            params["start_date"] = start_date
        
        resp = self.session.get(self.BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("msg") != "success":
            raise RuntimeError(f"FinMind API error: {data.get('msg')}")
        
        df = pd.DataFrame(data["data"])
        if df.empty:
            return pd.DataFrame()
        
        # 標準化欄位名
        df.columns = [c.lower() for c in df.columns]
        return df

    # 便利方法
    def taiwan_stock_institutional_investors(self, stock_id: str, start_date: str) -> pd.DataFrame:
        return self.fetch("TaiwanStockInstitutionalInvestorsBuySell", stock_id, start_date)
    
    def taiwan_stock_margin_purchase_short_sale(self, stock_id: str, start_date: str) -> pd.DataFrame:
        return self.fetch("TaiwanStockMarginPurchaseShortSale", stock_id, start_date)
    
    def taiwan_futures_institutional_investors(self, futures_id: str, start_date: str) -> pd.DataFrame:
        return self.fetch("TaiwanFuturesInstitutionalInvestors", futures_id, start_date)
```

### 在 Kernel 中使用
```python
# 替代 pip install FinMind
self._finmind_api = FinMindAPI()  # 無需 token 也可用 (有 rate limit)

# 原本：self.finmind.taiwan_stock_institutional_investors(stock_id=sid, start_date=start_date)
# 改為：
def _finmind_fetch(self, dataset: str, data_id: str, start_date: str) -> pd.DataFrame:
    return self._finmind_api.fetch(dataset, data_id, start_date)

# 呼叫
inst_df = self._finmind_fetch("TaiwanStockInstitutionalInvestorsBuySell", sid, start_date)
margin_df = self._finmind_fetch("TaiwanStockMarginPurchaseShortSale", sid, start_date)
futures_df = self._finmind_fetch("TaiwanFuturesInstitutionalInvestors", fid, start_date)
```

## 優點
- ✅ 完全避開套件安裝衝突
- ✅ 無額外依賴 (只需 `requests`，Kaggle 內建)
- ✅ 直接存取最新 API 版本
- ✅ 可控制 timeout、retry、rate limit

## 缺點
- ⚠️ 無 SDK 的自動重試/快取邏輯，需自行實作
- ⚠️ Rate limit：無 token 時約 300 req/hr，有 token 約 1000 req/hr
- ⚠️ 需自行處理分頁 (API 回傳全量，單請求上限約 10 萬筆)

## 相關 Kernel
- `mhhuang14/twstock-v6-0-data-fetch-20-stocks-5y-v3` (v4.4, FinMindAPI wrapper)
- 已成功跑完 20 股 × 5 年資料抓取

## 維護提醒
若 FinMind API v4 變更，只需更新 `FinMindAPI.fetch()` 參數映射，不影響上層邏輯。