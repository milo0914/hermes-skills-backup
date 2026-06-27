# Live Signal Bot 移植記錄 (2026-06-25, 更新 2026-06-26 v1.2)

## 背景
將 Kaggle notebook 中的實盤訊號計算邏輯移植為獨立 cron 腳本，實現每交易日自動推播台股訊號到 LINE。

## 原始版本問題 (live_signal_bot.py)
1. **致命**: `LINE_NOTIFY_TOKEN` 變數從未定義（L241 引用，L28 定義的是 `LINE_CHANNEL_ACCESS_TOKEN`），Notify API 已於 2025/4 停用
2. **依賴缺失**: `from input_file_0 import TWFeatureEngineer` 在獨立 .py 中不存在
3. **排程衝突**: `schedule.every().day.at("15:30")` + `while True` 佔用進程
4. **Token 硬編碼**: LINE Channel Access Token 直接寫在代碼中
5. **策略不足**: 僅 mid_cap_tech + traditional 兩個 regime

## 修復方案 (live_signal_bot_cron.py)
| 問題 | 修復 |
|------|------|
| Notify API 停用 | 改用 LINE Messaging API `send_line_message()` |
| import input_file_0 | TWFeatureEngineer + robust_normalize 直接內嵌 |
| schedule + while True | 單次執行模式，由 cron 定時觸發 |
| 硬編碼 token | 改讀 `LINE_CHANNEL_ACCESS_TOKEN` + `LINE_USER_ID` 環境變數 |
| 2 regime | 擴展到 4 regime（從 best_strategy_per_regime.json 讀取） |

## Cron 設定
- **Job ID**: `325fe94329b2`
- **名稱**: `live-signal-bot`
- **排程**: `30 15 * * 1-5`（週一至週五 15:30 CST）
- **環境變數**: `/data/.hermes/.env` 中 `LINE_CHANNEL_ACCESS_TOKEN` + `LINE_USER_ID`
- **注意**: `hermes config set` 寫到 config.yaml，Cron Python 腳本讀 .env。必須確保 .env 中有兩個 LINE 變數。

## 訊號計算流程
1. FinMind REST API 抓取 90 天 OHLCV + 期貨 OI + 美股指數
2. `TWFeatureEngineer.compute_features()` → 22 因子 Z-score (window=60, MAD-based)
3. `StackVM.execute(formula_tokens)` → 原始信號值
4. `np.tanh(signal[-1])` → [-1, 1] 壓縮
5. 閾值分類: >0.3 看多, <-0.3 看空, 其餘觀望

## 已訓練完成公式 (來源: 原始 live_signal_bot.py L72/L77)

### mid_cap_tech (15 tokens)
```
[11, 18, 27, 1, 31, 27, 30, 28, 27, 23, 21, 31, 31, 22, 23]
```
解碼: `(ABSORPTION SUB ((ABS(TX_MTX_SPREAD) SUB ABS(SIGN(OUTLIER(ABS(EMA(LIQ_SCORE)))))) ADD EMA(EMA(DOWJONES_CLOSE))))`

### traditional (14 tokens)
```
[16, 17, 31, 16, 33, 23, 18, 33, 32, 32, 24, 17, 33, 29]
```
解碼: `GATE(MAX3(MTX_RETAIL_OI)>0?TX_INST_NET_OI:((EMA(MTX_RETAIL_OI) SUB MAX3(TX_INST_NET_OI)) MUL LAG(LAG(MAX3(TX_MTX_SPREAD)))))`

### large_cap (未訓練, fallback)
```
[1]  # LIQ_SCORE
```

### financial (未訓練, fallback)
```
[14]  # CLOSE_POS
```

## 踩坑 1: JSON 覆蓋 DEFAULT_STRATEGIES

`load_strategies()` 邏輯: 先設 DEFAULT_STRATEGIES，再用 JSON 覆蓋。若 JSON 中存的是失敗訓練結果（如 v6.23 的 `[20]` = SP500_CLOSE），會把正確的已訓練公式蓋掉。

**修正**: 必須同時更新 `best_strategy_per_regime.json` 中的 `formula_tokens`，不能只改 Python DEFAULT。
- v6.23 JSON 原始: `{"mid_cap_tech": {"best_formula": [20], "val_ic": 0.1816}}`
- 修正後: `{"mid_cap_tech": {"formula_tokens": [11,18,27,...], "val_ic": 0.1816}, "traditional": {"formula_tokens": [16,17,31,...], "val_ic": 0.156}}`

## 踩坑 2: .env vs config.yaml

`hermes config set LINE_USER_ID xxx` 寫入 config.yaml，但 Cron 執行 `os.environ.get("LINE_USER_ID")` 讀 .env。若 .env 中缺 LINE_USER_ID，LINE 推播會因 `to` 欄位為空而回 400。

**修正**: 手動將 `LINE_USER_ID` 追加到 `/data/.hermes/.env`。

## 踩坑 3: FinMind API 欄位名 vs Dataset v2 完全不同 (2026-06-26 發現並修正)

FinMind REST API 回傳的 TaiwanFuturesInstitutionalInvestors 欄位名與 Kaggle 訓練用 Dataset v2 (futures_oi.csv) 完全不同。

### FinMind API 實際回傳欄位 (2026-06-26 實測)
```
futures_id, date, institutional_investors, long_deal_volume, long_deal_amount,
short_deal_volume, short_deal_amount, long_open_interest_balance_volume,
long_open_interest_balance_amount, short_open_interest_balance_volume,
short_open_interest_balance_amount
```

### Dataset v2 (futures_oi.csv) 欄位 (Kaggle 訓練用，已預處理)
```
date, futures_id, Foreign_Investor_net_oi, ..., inst_net_oi, retail_net_oi
```

### 關鍵差異對照
| 用途 | FinMind API | Dataset v2 | cron 腳本需做的轉換 |
|------|-------------|------------|---------------------|
| 篩選外資 | `institutional_investors == "外資"` | 已預先篩選為 `Foreign_Investor_net_oi` | `df[df["institutional_investors"] == "外資"]` |
| 外資多頭 OI | `long_open_interest_balance_volume` | `inst_net_oi` (已計算) | 自行計算: `long_oi - short_oi` |
| 外資空頭 OI | `short_open_interest_balance_volume` | `retail_net_oi` (近似) | 自行計算: `-(long_oi - short_oi)` |
| 篩選 filter 欄 | `institutional_investors` | `name` | ⚠️ 舊版 cron 寫 `raw["name"]=="外資及陸資"` 但 API 回傳 `institutional_investors` 且值為 `"外資"` |

### Bug 清單 (v1.1→v1.2, 2026-06-26)
1. **rename bug** (已修 v1.1): L198 `inst_net_oid` → 改為 `inst_net_oi`
2. **取值方式 bug** (已修 v1.1): L203-205 `g.get(key, 0)` → 改為 `g[key].fillna(0)` 對齊 V7
3. **filter 欄位名 bug** (已修 v1.2): `raw["name"] == "外資及陸資"` → 改為 `raw["institutional_investors"] == "外資"`，保留 `name` fallback
4. **OI 欄位名 bug** (已修 v1.2): `foreign["long_oi"]` → 改為 `foreign["long_open_interest_balance_volume"]`，保留 `long_oi` fallback

Bug #3/#4 導致 `futures_records` 為空 → `futures_oi_df = None` → TX_INST_NET_OI / MTX_RETAIL_OI / TX_MTX_SPREAD 全部為 0 → traditional 公式 0.00 [觀望]。

### 正確的 get_live_features 期貨籌碼前處理 (v1.2)
```python
futures_records = []
for raw, f_id in [(tx_raw, "TX"), (mtx_raw, "MTX")]:
    if not raw.empty:
        # FinMind API v4: institutional_investors 欄位，值為 "外資" (非 "外資及陸資")
        if "institutional_investors" in raw.columns:
            foreign = raw[raw["institutional_investors"] == "外資"].copy()
        elif "name" in raw.columns:
            foreign = raw[raw["name"] == "外資及陸資"].copy()
        else:
            foreign = raw.copy()
        foreign["futures_id"] = f_id
        # FinMind API v4: long_open_interest_balance_volume / short_open_interest_balance_volume
        lname = "long_open_interest_balance_volume"
        sname = "short_open_interest_balance_volume"
        if lname in foreign.columns and sname in foreign.columns:
            foreign["inst_net_oi"] = foreign[lname].fillna(0) - foreign[sname].fillna(0)
            foreign["retail_net_oi"] = -foreign["inst_net_oi"]
        elif "long_oi" in foreign.columns and "short_oi" in foreign.columns:
            foreign["inst_net_oi"] = foreign["long_oi"].fillna(0) - foreign["short_oi"].fillna(0)
            foreign["retail_net_oi"] = -foreign["inst_net_oi"]
        else:
            foreign["inst_net_oi"] = 0
            foreign["retail_net_oi"] = 0
        futures_records.append(foreign[["date", "futures_id", "inst_net_oi", "retail_net_oi"]])
futures_oi_df = pd.concat(futures_records) if futures_records else None
```

### 修復後驗證結果 (2026-06-26 00:55)
- **mid_cap_tech**: 從全 +1.00 [看多] → -1.00 [看空]（期貨數據進來後訊號翻轉，外資 TX 淨 OI=-81051）
- **traditional**: 從全 0.00 [觀望] → -0.96 [看空]（GATE 公式正確計算，MTX_RETAIL_OI=1615, TX_INST_NET_OI=-81051）
- **large_cap/financial**: 不受期貨 bug 影響，行為一致

### 根因教訓
Kaggle 訓練用 Dataset v2 的 futures_oi.csv 是**預先處理過的**：已篩選外資、已計算 inst_net_oi。FinMind API 回傳**原始三法人數據**。從 Kaggle notebook 移植到 REST API 環境時，不能只改計算邏輯（TWFeatureEngineer/StackVM），還必須**重新實作整個前處理邏輯**。否則即使公式 100% 對齊，實際計算時期貨籌碼數據全是 0 也是枉然。

驗證方法：在 `compute_features()` 後印出特徵的非零數量 `feat[c].non-zero count` 和 min/max，確認期貨籌碼因子非恆零。

## 踩坑 4: .env 缺 LINE_CHANNEL_ACCESS_TOKEN (2026-06-26 發現)

`LINE_USER_ID` 存在於系統環境變數（/proc/1/environ），但 `LINE_CHANNEL_ACCESS_TOKEN` **完全不存在**於 `.env` 也無 env 注入。

腳本行為：`LINE_CHANNEL_ACCESS_TOKEN` 為空 → `send_line_message()` 走 `if not LINE_CHANNEL_ACCESS_TOKEN: print("[本地印出]")` 分支，**不拋錯不報警**，容易漏查。

**排查方式**：
```bash
grep LINE /data/.hermes/.env
# 應出現兩行：LINE_CHANNEL_ACCESS_TOKEN=... 和 LINE_USER_ID=...
```

**修正**：需用戶提供 LINE Channel Access Token，追加到 .env：
```bash
echo 'LINE_CHANNEL_ACCESS_TOKEN=xxx' >> /data/.hermes/.env
```

**驗證**：
```bash
set -a; source /data/.hermes/.env; python3 scripts/live_signal_bot_cron.py
# 輸出應含「LINE 訊息發送成功！」而非「[本地印出]」
```

## 踩坑 5: Cron deliver=origin 手動觸發 400 (2026-06-26 發現)

Cron job `live-signal-bot` 設定 `deliver=origin`，手動 `cronjob run` 時回報 `no delivery target resolved for deliver=origin`。這是因為手動觸發沒有對應的聊天目標（origin session）。

**不影響排程自動執行**（排程時有對應 session 上下文）。

**手動測試 LINE 推播的正確方式**：直接用 terminal 執行腳本，確保 .env 已 source：
```bash
set -a; source /data/.hermes/.env; python3 /data/.hermes/skills/research/twstock-alpha-gpt/scripts/live_signal_bot_cron.py
```

## v1.1 腳本 rename bug 修復驗證 (2026-06-26)

Skill 目錄內的 `scripts/live_signal_bot_cron.py` v1.1 已確認包含以下修復：
- L198: `inst_net_oi`（非 `inst_net_oid`）
- L200-202: 正確的 rename（`tx_inst_net_oi`/`mtx_inst_net_oi`）而非舊版 typo
- L205-207: `g[key].fillna(0)` 取代 `g.get(key, 0)`
- L389-394: `institutional_investors == "外資"` 優先，`name == "外資及陸資"` fallback
- L397-405: `long_open_interest_balance_volume` 優先，`long_oi` fallback

三處一致性確認：
1. Python DEFAULT_STRATEGIES tokens ✅
2. best_strategy_per_regime.json formula_tokens ✅
3. SKILL.md 文件記載 ✅
