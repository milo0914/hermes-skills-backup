# FinMind REST API Workaround (2026-06-14)

## Problem
FinMind Python package requires `pydantic>=1.6.1,<2.0.0` but Kaggle environment has pydantic v2 pre-installed. Installing FinMind via pip fails with `metadata-generation-failed` due to version conflicts:
- `pydantic>=1.6.1,<2.0.0` vs Kaggle's pydantic v2
- `ipython>=7.16.1,<8.0.0` vs Kaggle's ipython v8+
- `aiohttp>=3.7.4.post0,<4.0.0` vs Kaggle's aiohttp v4+

## Solution: Direct REST API Wrapper
Replace `pip install FinMind` with a minimal `requests`-based wrapper class:

```python
class FinMindAPI:
    BASE_URL = "https://api.finmindtrade.com/api/v4/data"
    
    def __init__(self, token=None):
        self.token = token
        self.session = requests.Session()
    
    def fetch(self, dataset: str, data_id: str, start_date: str):
        params = {"dataset": dataset, "data_id": data_id, "start_date": start_date}
        if self.token:
            params["token"] = self.token
        resp = self.session.get(self.BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("msg") != "success":
            raise RuntimeError(f"FinMind API error: {data.get('msg')}")
        return pd.DataFrame(data.get("data", []))
```

## Datasets Used
| Dataset | data_id | 用途 |
|---------|---------|------|
| TaiwanStockInstitutionalInvestorsBuySell | stock_id (e.g. "2330") | 法人買賣超 |
| TaiwanStockMarginPurchaseShortSale | stock_id | 融資融券 |
| TaiwanFuturesInstitutionalInvestors | futures_id (e.g. "TX") | 期貨 OI |

## Integration Pattern
In data fetcher class:
```python
@property
def finmind(self):
    if not hasattr(self, "_finmind_api"):
        self._finmind_api = FinMindAPI()
    return self._finmind_api

def _finmind_fetch(self, dataset: str, data_id: str, start_date: str):
    return self.finmind.fetch(dataset, data_id, start_date)

def fetch_inst_flow(self, stock_id: str, start_date: str):
    return self._finmind_fetch("TaiwanStockInstitutionalInvestorsBuySell", stock_id, start_date)

def fetch_margin(self, stock_id: str, start_date: str):
    return self._finmind_fetch("TaiwanStockMarginPurchaseShortSale", stock_id, start_date)

def fetch_futures_oi(self, futures_id: str, start_date: str):
    return self._finmind_fetch("TaiwanFuturesInstitutionalInvestors", futures_id, start_date)
```

## Key Benefits
- Zero dependency conflicts — only needs `requests` (already in Kaggle)
- Works in any Python environment without pip install
- Token optional (public API has rate limits, token increases quota)
- Direct control over timeout, retry logic, error handling

## Files Modified
- `/home/appuser/twstock_kernel/twstock-v6-0-data-fetch-20-stocks-5y-v2.py` (v4.4) — complete rewrite using FinMindAPI