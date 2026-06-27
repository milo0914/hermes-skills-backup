---
name: twstock-alpha-gpt
description: 台股 AI Dig Money 系統 — AlphaGPT 因子挖掘 + Marcus 三重過濾 + Wenty 量價。包含 Dataset v6.0 架構、adapt_finmind_data 雙格式支援修復、端到端驗證方法。
---

# TWStock AlphaGPT Skill

## 系統概述
台股 AI Dig Money 系統，使用 GRPO 強化學習進行因子挖掘。支援 AlphaGPT 因子模型訓練、Marcus 三重過濾、Wenty 量價策略。

## Dataset 架構 (v6.0 Dataset v2)
5 個 CSV 檔案，20 檔股票 × 5 年資料 (2021-01-04 ~ 2026-06-11)：

| 檔案 | 筆數 | 重要欄位 | 格式 |
|------|------|----------|------|
| price_ohlcv.csv | 24,385 | date, stock_id, open, high, low, close, volume | 長格式 (19 stocks, 2311 delisted) |
| inst_flow.csv | 26,360 | date, stock_id, Foreign_Investor, Dealer_self, Investment_Trust, Dealer_Hedging, Foreign_Dealer_Self, total_net | 預先 pivot 格式（非長格式） |
| margin.csv | 26,360 | date, stock_id, margin_balance, margin_buy, ... | 已對應欄位格式 |
| futures_oi.csv | 2,674 | date, futures_id, Foreign_Investor_net_oi, ..., inst_net_oi, retail_net_oi | 長格式 (TX+MTX, 各 1,337 rows) |
| us_indices.csv | 3,765 | date, index_name, close, mom5 | 長格式 (Nasdaq/SP500/DowJones) |

### adapt_finmind_data 已知問題 (v6.0 Dataset v2)
**症狀**：`futures_oi_df = None` 導致期貨因子全為 0 → GRPO 無法學習 TX_INST_NET_OI / MTX_RETAIL_OI / TX_MTX_SPREAD

**根因**：adapt_finmind_data 的 futures 載入邏輯檢查 `if "oi" in raw.columns`（舊格式欄位），但 Dataset v2 的欄位是 `inst_net_oi`/`retail_net_oi`（長格式），條件不成立 → 跳過載入。

**已修復** (v6.0 dsfix, 2026-06-13)：grpo-v33-dsfix.py 中包含完整修復版本。詳見 `references/adapt-finmind-data-dual-format-fix-2026-06-13.md`。
1. futures 載入改為雙格式支援：新長格式 (`futures_id` + `inst_net_oi`) 優先，若不符則 fallback 舊格式 (`oi`) + 60/40 近似
2. OHLCV 載入改為多檔名掃描 (`price_ohlcv.csv`, `twstock_daily.csv`, `ohlcv.csv`)
3. inst 載入支援預先 pivot 格式 (`Foreign_Investor` 等欄位已存在時直接 rename)
4. margin 載入支援已對應格式 (`margin_balance` 欄位存在時直接使用)
5. 每個載入路徑都有格式偵測 + print log

### API 對照表 (FinMind → Dataset v2 欄位)

| FinMind Dataset | Dataset v2 欄位 | 來源 CSV |
|-----------------|------------------|----------|
| TaiwanStockInfo | stock_id | price_ohlcv.csv |
| TaiwanStockPrice | open/high/low/close/volume | price_ohlcv.csv |
| TaiwanStockInstitutionalInvestorsBuySell | Foreign_Investor / Dealer_self / Investment_Trust / total_net | inst_flow.csv |
| TaiwanStockMarginPurchaseShortSale | margin_balance / margin_buy / short_balance | margin.csv |
| TaiwanFuturesInstitutionalInvestors | inst_net_oi / retail_net_oi | futures_oi.csv |
| US stock indices | close (Nasdaq/SP500/DowJones) | us_indices.csv |

## 系統元件

### TWFeatureEngineer.compute_features
- 輸入: OHLCV df + inst_df + margin_df + futures_oi_df + us_indices_df
- 輸出: 22 個正規化因子 (含期貨 OI + 美股)
- 期貨 merge: pivot TX/MTX wide，再 merge via `tx_inst_net_oi` / `mtx_retail_net_oi`
- 法人 merge: inst_df (total_net) per stock_id merge via `inst_flow_raw`
- 融資 merge: margin_df (margin_change / margin_balance) per stock_id merge via `margin_press_raw`
- 美股 merge: pivot wide per index，再 merge via `nasdaq_close_raw` / etc.
- 所有特徵正規化 (zscore, rolling 60 days)
- 回傳: result_frames 用 keep_cols 過濾 (date + stock_id + 22 FEATURE_NAMES)

### GRPO 訓練流程
1. adapt_finmind_data(data_path) → 5 DataFrames
2. TWFeatureEngineer.compute_features → 22 維 feat tensor
3. GRPORewardCalculator → reward (spearman IC)
4. GRPOAlphaTrainer → REINFORCE loss

### GRPO v6.10 增強功能 (2026-06-15)
v6.10 版本在 v6.9 基礎上增加四項短期增強，專注於提升 reward 計算的穩定性和可觀測性：

1. **勝利orized IC 選項**
   - 新增 GRPOConfig 參數: `winsorize_ic: bool = False`
   - 當啟用時，在計算 IC 前對 signal 和 returns 進行 5%-95% 勝orization
   - 使用 `np.clip(x, np.percentile(x, 5), np.percentile(x, 95))` 防止極端值異常影響 IC 計算
   - 有助於減少異常損益對因子評價的影響

2. **Sortino ratio 作為 Sharpe 的替代選項**
   - 新增 GRPOConfig 參數: `use_sortino: bool = False` 和 `sortino_target: float = 0.0`
   - 當 `use_sortino` 為True時，使用 Sortino ratio 而非標準 Sharpe ratio
   - Sortino ratio 只考慮下行波動: `excess_ret = port_ret - sortino_target`
   - `downside_deviation = np.sqrt(np.mean(np.minimum(excess_ret, 0) ** 2))`
   - 適合對下行風險敏感的投資策略

3. **增加 diversity penalty 係數**
   - 將 `diversity_penalty` 從 3.0 增加到 4.5
   - 進一步加強多樣性懲罰，減少群組內公式過於相似的問題
   - 在訓練循環中，當公式相似度 > 0.85 時施加懲罰

4. **增強訓練日誌顯示個別 reward 元件**
   - 修訓練循環在 `compute_group_rewards` 後計算並存儲個別元件均值：
     - `result["ic_mean"]`, `result["sharpe_mean"]`, `result["mdd_mean"]`, 
     - `result["turnover_mean"]`, `result["diversity_mean"]`
   - 訓練日誌印出增強為顯示每個元具體貢獻：
     - `f" IC={result[\"ic_mean\"]:.3f} Sharpe={result[\"sharpe_mean\"]:.3f} "`
     - `f"MDD={result[\"mdd_mean\"]:.3f} Turn={result[\"turnover_mean\"]:.3f} "`
     - `f"Div={result[\"diversity_mean\"]:.3f}"`
   - 有助於監控各 reward 元件對最終決策的影響程度

## 端到端驗證命令
```bash
cd /home/appuser
python3 -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('m', 'grpo-v33-dsfix.py')
mod = importlib.util.module_from_spec(spec)
sys.modules['m'] = mod; spec.loader.exec_module(mod)
data_path = '/home/appuser/twstock_kernel_out/twstock_v6_data'
df, i_df, m_df, f_df, u_df = mod.adapt_finmind_data(data_path)
feat = mod.TWFeatureEngineer.compute_features(df, i_df, m_df, f_df, u_df)
print(f'Features: {len(feat)} rows, {feat[\"stock_id\"].nunique()} stocks')
for c in ['TX_INST_NET_OI','MTX_RETAIL_OI','TX_MTX_SPREAD','NASDAQ_CLOSE','SP500_CLOSE','DOWJONES_CLOSE']:
    s = feat[c]; print(f'{c:20s}: non-zero={(s!=0).sum():>6}, NaN={s.isna().sum():>4}, min={s.min():+.2f}, max={s.max():+.2f}')
"
```

## 參考文檔
- `references/finmind-rest-api-workaround-2026-06-14.md` — FinMind REST API 取代 pip install 避免 pydantic 衝突
- `references/kaggle-kernel-version-management-2026-06-14.md` — Kernel 三層版號管理 + auto-scan 掛載模式
- `references/adapt-finmind-data-dual-format-fix-2026-06-13.md` — Dataset v2 雙格式支援修復
- `references/kaggle-dataset-auto-scan-pattern-2026-06-13.md` — Kaggle dataset 自動掃描模式
- `references/grpo-advantage-collapse-fix-pattern-2026-06-13.md` — GRPO advantage collapse 修復模式
- `references/grpo-v61-regime-bugs-found-2026-06-14.md` — GRPO v6.1/v6.2 regime bugs 分析與修復方案
- `references/end-to-end-data-pipeline-2026-06-14.md` — 端到端資料管線驗證
- `references/grpo-v62-to-v68-evolution-2026-06-14.md` — **GRPO v6.2→v6.8 完整演進歷程、版本對照、已知 Bug、檔案對照**
- `references/dataset-v2-push-2026-06-14.md` — **Kaggle Dataset v2 推送記錄 (2026-06-14 完成)**
- `references/physical-file-index-2026-06-14.md` — **本地所有實體檔案快速索引 (notebook、data、metadata、scripts、Kaggle slug)**
- `references/grpo-factor-evaluation-rubric.md` — **GRPO 因子評估 Rubric: IC 水準分級、IC Gap 判讀、Multi-Objective Reward 分解公式、22 因子定義速查表、v6.10 四 regime 訓練結果摘要、常見問題診斷表**
- `references/todo-and-notebook-practices.md` — **AI Dig Money 系統 - TODO 與 Notebook 實務慣例: 四管道結構 (data_pipe, filter_pipe, grpo_training_pipe, report_pipe)、Notebook 更新慣例 (版本號、GPU 相容性)、續接期望**
- `references/live-signal-bot-migration-2026-06-25.md` — **實盤訊號機器人移植記錄: LINE Notify→Messaging API、input_file_0 依賴移除、cron 設定、訊號計算流程**
- `references/live-signal-bot-formula-audit-2026-06-26.md` — **公式計算審計: EMA 1.4× 放大器、結構性偏空根因分析、完整 StackVM trace 數值列式**
- `references/v7-vs-bot-finmind-field-comparison-2026-06-26.md` — **V7 ipynb vs Bot 腳本 FinMind 欄位名比對: retail_net_oi 定義差異、60% fallback 估算 vs 精確 API**
- `references/v13-consistency-audit-and-fixes-2026-06-27.md` — **v1.3 一致性審計: robust_normalize NaN bug 修正、V7 vs Bot 欄位對照、V8 Signal 重算驗證**
## GRPO v6.x Version History (from `twstock-grpo-v6-changelog`)

Complete development history for GRPO Regime-Aware Factor Training v5.9→v6.23, including version evolution, training results, and debug sessions.

**Key versions:**
- v6.19: Composite score full fix — 8 audit defects resolved, first version with operator formulas (best_ops=1)
- v6.23: Composite score root fix — 4 bug root causes (min_formula_len hard filter, exploration restart without cooldown, _best_toks misaim, reward-composite misweight)
- See references for per-version changelogs, debug session logs, and kernel-metadata templates

**Operational workflow:** Download previous log → analyze metrics → plan fixes → build notebook → verify (py_compile + JSON inspect) → push → monitor → iterate.

**Critical checklist per iteration:** version strings updated, source=str (not list), machine_shape="Gpu", composite traverses full group, early stop references composite-best, re-seed templates ≥ min_formula_len.

**Detailed changelog references:** `references/grpo-v6-changelog/CHANGELOG_v6.9.md` through `v623-debug-session.md`
**Kernel-metadata templates:** `references/grpo-v6-changelog/kernel-metadata-v6.19.json`
**Per-version notebooks:** `references/grpo-v6-changelog/twstock-grpo-*.ipynb`

## 實盤訊號機器人 (live_signal_bot_cron.py)

### 架構
- **腳本位置**: `scripts/live_signal_bot_cron.py`
- **Cron job**: `live-signal-bot` (id: `325fe94329b2`), 週一至週五 15:30 CST
- **認證**: 環境變數 `LINE_CHANNEL_ACCESS_TOKEN` + `LINE_USER_ID`（存於 `/data/.hermes/.env`）
- **策略來源**: `scripts/best_strategy_per_regime.json`（訓練成功後自動更新）

### 功能
1. 從 FinMind REST API 抓取 120 天 OHLCV + 期貨 OI + 美股指數
2. 呼叫內嵌 `TWFeatureEngineer.compute_features()` 計算 22 因子 Z-score（v1.3: 修正 NaN 處理）
3. 使用 `StackVM.execute()` 執行 AI 訓練出的公式 tokens
4. `np.tanh(signal[-1])` 壓縮到 [-1, 1]，分為看多(>0.3)/觀望/看空(<-0.3)
5. 透過 LINE Messaging API push 訊息

### 4 個 Regime 與監控股票
| Regime | 股票 | 已訓練完成公式 tokens | 解碼後公式 | 備註 |
|--------|------|----------------------|-----------|------|
| mid_cap_tech | 2303, 2317, 2382, 2454, 3008, 3034, 3711 | [16, 20, 13, 33, 28, 32, 28, 22, 12, 27, 22, 13, 22, 27, 22] | (TX_INST_NET_OI ADD ABS(((SP500_CLOSE ADD SIGN(LAG(SIGN(MAX3(ATR))))) ADD ABS(SURF_ENTRY)) ADD ATR)) | V8 訓練 |
| traditional | 1301, 1101, 2002 | [16, 17, 17, 33, 31, 27, 31, 27, 24, 27, 10, 31, 33, 23, 22] | (TX_INST_NET_OI ADD (ABS((MTX_RETAIL_OI MUL ABS(EMA(ABS(EMA(MAX3(MTX_RETAIL_OI))))))) SUB MAX3(EMA(CVD_PROXY)))) | V8 訓練 |
| large_cap | 2330, 2308, 2412, 1303, 1326 | [1] (LIQ_SCORE fallback) | LIQ_SCORE | 待訓練 |
| financial | 2882, 2886, 2891, 2881, 2884 | [14] (CLOSE_POS fallback) | CLOSE_POS | 待訓練 |

### v1.3 修正摘要 (2026-06-27)
- **NaN bug**：`robust_normalize` 使用 `np.median` 在含 NaN 輸入時回傳 NaN → 大量特徵 Z-score 全歸零。改用 `np.nanmedian` + `fillna(0)` 前處理。
- **受影響特徵**：ATR、CVD_PROXY、VOL_BREAKOUT、MOM_REV、FIVE_DAY_HIGH 等（所有含 rolling warmup NaN 的因子）。
- **驗證結果**：ATR 從全零→+0.387(鴻海)、CVD_PROXY 從全零→-1.040、VOL_BREAKOUT 從全零→+0.936。
- **仍為零的因子**：INST_FLOW（未抓取法人資料）、MARGIN_PRESS（未抓取融資融券資料）、SURF_ENTRY（設計上極少觸發=1.0）。
- **已記錄待改善**：INST_FLOW/MARGIN_PRESS train-inference skew（Pitfall #27）。
- **v1.4 防彈版升級** — 6 項改善：(1) len<window 回傳 np.zeros_like（防 NaN 洩漏 StackVM）；(2) result 初始化 np.zeros_like；（3）逐值檢查 np.isnan(arr[i]) 不依賴事後兜底；（4）warmup 期逐值檢查；（5）np.errstate(all='ignore') 壓制警告；（6）保留 n_valid 嚴格門檻。7 項單元測試全通。

### 注意事項
- **JSON 優先覆蓋 DEFAULT**：`load_strategies()` 會從 `best_strategy_per_regime.json` 覆蓋 DEFAULT_STRATEGIES 的 tokens。若 JSON 內容是舊訓練的退化結果（如 v6.23 的 `[20]`），會蓋掉正確的已訓練完成公式。更新公式時必須同時修改 JSON 檔，不能只改 Python DEFAULT。
- **美股 API 限制**：FinMind `USStockPrice` 對 `^DJI`/`^GSPC`/`^IXIC` 可能回傳空，此時美股因子=0
- **週末不執行**：腳本內建 `weekday >= 5` 檢查
- **.env vs config.yaml**：Cron 環境變數從 `.env` 載入（`/data/.hermes/.env`）。`hermes config set` 寫到 `config.yaml`，Cron 的 Python 腳本用 `os.environ.get()` 讀不到。必須確保 `.env` 中同時有 `LINE_CHANNEL_ACCESS_TOKEN` 和 `LINE_USER_ID`。
- **.env 可能缺 LINE_CHANNEL_ACCESS_TOKEN**：`LINE_USER_ID` 可能已存在於系統環境（如 /proc/1/environ），但 `LINE_CHANNEL_ACCESS_TOKEN` 不在任何地方。腳本行為是：若 `LINE_CHANNEL_ACCESS_TOKEN` 為空，走 `[本地印不]` fallback 分支，不拋錯。**排查步驟**：(1) `grep LINE /data/.hermes/.env` 確認兩個變數都存在；(2) 若缺，`echo 'LINE_CHANNEL_ACCESS_TOKEN=xxx' >> /data/.hermes/.env`；(3) 驗證：`set -a; source /data/.hermes/.env; python3 scripts/live_signal_bot_cron.py`，看輸出是「LINE 訊息發送成功」還是「[本地印不]」。
- **Cron deliver=origin 手動觸發會 400**：Cron job `live-signal-bot` 設定 `deliver=origin`，手動 `cronjob run` 會成功執行腳本但回報 `no delivery target resolved for deliver=origin`（因無對應聊天目標）。不影響排程自動執行，但手動測試 LINE 推播應改用 terminal 直接執行腳本（配合 `source .env`）。
- **Cron prompt 已包含 source .env 步驟**：2026-06-26 更新後，cron prompt 明確要求：(1) `set -a; source /data/.hermes/.env; set +a`；(2) 驗證環境變數已載入；(3) 若缺則自動補寫；(4) 執行腳本；(5) 確認輸出有「LINE 訊息發送成功」。此步驟確保 Space 重建後 cron 仍能正確推播 LINE。
- **HF Space 重建後 .env 會丟失 LINE creds**：恢復來源為 `references/實盤訊號計算與回報程式live_signal_bot.py` 第 28-29 行硬編碼值。Cron prompt 已內建自動恢復機制（步驟 3）。

## 已知 Pitfalls
1. **adapt_finmind_data 載入路徑**：每個資料表有兩種格式（新/舊），必須自動偵測。新格式含 futures_id + inst_net_oi / index_name + close / Foreign_Investor（預先 pivot）/ margin_balance（已對應）
2. **FinMind pip install 在 Kaggle 失敗**：pydantic v1/v2 衝突。**解法**：用 FinMind REST API 直接呼叫 (`https://api.finmindtrade.com/api/v4/data`)，只需 `requests`，零依賴衝突。詳見 `references/finmind-rest-api-workaround-2026-06-14.md`
3. **Kaggle Kernel 版號管理**：三層版號 (檔名 / 內部標題 / metadata.id) 必須同步。**metadata.id 為準**，每次 push 遞增。詳見 `references/kaggle-kernel-version-management-2026-06-14.md`
4. **Dataset 掛載路徑不固定**：`/kaggle/input/<owner>/<slug>/` 具體路徑會變。**解法**：auto-scan `/kaggle/input/` 下所有 CSV，多檔名 fallback。adapt_finmind_data v6.2+ 已內建此模式
5. **期貨 merge 需 pivot wide**：直接 merge futures_oi_df on date 會讓每檔股票的 rows 翻倍（TX+MTX 兩行）。必須先 pivot TX/MTX 成 tx_inst_net_oi / mtx_inst_net_oi 欄位再 merge
6. **美股時差**：shift(1) 處理台股 vs 美股交易日差異
7. **compute_features groupby 輸出**：若 result_frames 中 keep_cols 缺少 stock_id，輸出會少 stocks。確認 keep_cols 含 stock_id
8. **Dataset 更新**：每次 feature 架構變更後必須同步更新 Kaggle Dataset 版本
9. **檔案名對應**：Dataset v2 檔名為 price_ohlcv.csv / inst_flow.csv / margin.csv / futures_oi.csv / us_indices.csv，但 adapt_finmind_data 舊版期待 twstock_daily.csv / inst_data.csv / margin_data.csv。修復後自動偵測兩者
10. **inst 欄位大小寫**：inst_flow.csv 的欄位是 Foreign_Investor（大寫開頭），不是 foreign_net（小寫）。adapt_finmind_data 中 rename 映射必須匹配實際欄位名
11. **compute_features 必須同時修復**：即使 adapt_finmind_data 正確載入期貨 OI 資料，compute_features 內部可能仍硬編碼設為 0（Kaggle notebook v5.9 有此 bug）。必須在 groupby 迴圈內加入 pivot-merge 邏輯，從 futures_oi_df / us_indices_df 讀取真實值。不要假設 adapt_finmind_data 回傳對了 compute_features 就會自動使用 — 兩者是獨立函數。
12. **inst_flow 和 margin_press 同陷阱**：compute_features 內這兩欄也常被設為 0，須從 inst_df(total_net) 和 margin_df(margin_change/margin_balance) 逐 stock merge 真實資料。Merge 必須在 groupby 迴圈內（每個 stock_id 的 group 處理區塊中），不是在迴圈外統一 merge — 因每個 stock 的 date 列不同，外層 merge 會出錯。
13. **GPU 不可用時只訓練 tech regime**：Kaggle GPU quota 用完或 CPU 環境時，4 個 regime 同時訓練耗時過長。策略：只保留 MID_CAP_TECH regime 的股票 (stock_data_map filter)，其餘跳過。注意需在 main() 中、trainer 初始化前執行過濾，同時檢查 `GRPO_FORCE_CPU` env var。
14. **LINE Notify API 已於 2025/4 停用** — 舊版 `live_signal_bot.py` 使用 `https://notify-api.line.me/api/notify` endpoint 已完全下線，呼叫會回 403/404。必須改用 LINE Messaging API：`https://api.line.me/v2/bot/message/push`，需 Channel Access Token + User ID，而非 Notify Token。訊息格式為 JSON `{\\\"to\\\": USER_ID, \\\"messages\\\": [{\\\"type\\\":\\\"text\\\", \\\"text\\\":\\\"...\\\"}]}`，Header 用 `Authorization: Bearer {CHANNEL_ACCESS_TOKEN}`。
15. **Kaggle notebook `from input_file_0 import X` 在獨立 .py 中不可用** — Kaggle notebook 上傳的附屬 .py 模組在 kernel 環境中以 `input_file_0` 為模組名動態載入，但脫離 Kaggle 環境後此 import 會失敗。將 Kaggle notebook 移植為獨立 .py 腳本時，必須把 `from input_file_0 import TWFeatureEngineer` 等改為 **直接內嵌 class 定義**，或在同目錄放對應 .py 模組檔。同理 `from __main__ import X` 在某些環境也不可靠。
16. **best_strategy_per_regime.json 覆蓋 DEFAULT_STRATEGIES** — `load_strategies()` 以 JSON 為準覆蓋預設 tokens。若 JSON 存放的是失敗训练結果（如 v6.23 的 `[20]` = SP500_CLOSE），會蓋掉正確的已訓練完成公式。更新已訓練公式時，必須同時修改 JSON 檔中的 `formula_tokens`，不能只改 Python DEFAULT_STRATEGIES。
17. **Cron 環境變數必須寫 .env 非 config.yaml** — `hermes config set KEY VALUE` 寫到 `config.yaml`，但 Cron 執行 Python 腳本時用 `os.environ.get()` 讀 `.env`（`/data/.hermes/.env`）。若缺 `LINE_USER_ID`，LINE 推播會因 `to` 欄位為空而 400。確認 `.env` 中同時有 `LINE_CHANNEL_ACCESS_TOKEN` 和 `LINE_USER_ID`。常見問題：`LINE_USER_ID` 已在系統環境中（/proc/1/environ），但 `LINE_CHANNEL_ACCESS_TOKEN` 完全不存在於 .env 也無 env 注入，此時腳本靜默走 fallback 分支印出 `[本地印出]` 不拋錯，容易漏查。排查：`grep LINE /data/.hermes/.env` 確認兩個都要有。
18. **FinMind REST API 欄位名 ≠ Dataset v2 欄位名** — 從 Kaggle notebook 移植到 FinMind REST API 環境時，不能假設相同欄位名。**TaiwanFuturesInstitutionalInvestors**：Dataset v2 用 `inst_net_oi`/`retail_net_oi`（已計算+已篩選外資），FinMind API 回傳 `institutional_investors`（三法人）+ `long_open_interest_balance_volume`/`short_open_interest_balance_volume`（需自行篩選外資 + 計算 inst_net_oi）。filter 欄位：API 用 `"外資"` 非 `"外資及陸資"`。**TaiwanStockPrice**：Dataset v2 用 `volume`/`high`/`low`，FinMind API 回傳 `Trading_Volume`/`max`/`min`（需 rename）。移植時必須在 `get_live_features()` 中做完整欄位對照+轉換，詳見 `references/live-signal-bot-migration-2026-06-25.md` 「FinMind API 欄位名 vs Dataset v2」段。
19. **從 Kaggle notebook 移植代碼到獨立腳本時必須驗證端到端數據流** — 不能只比對計算公式（TWFeatureEngineer/StackVM）是否一致，還必須驗證**數據前處理**（API 欄位名、filter 條件、merge 邏輯）是否正確。否則即使公式 100% 對齊，實際計算時數據是 0 也是枉然。驗證方法：在 `compute_features()` 後印出 `feat[c].non-zero` 數量和 min/max，確認期貨籌碼因子非恆零。
20. **terminal 工具展開環境變數汙染 Python 字串替換** — 使用 `terminal(command='cat file.py')` 讀取檔案內容後做 Python string replace 時，若檔案中含有與當前環境變數同名的子字串（如 `os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")` 中的 `LINE_CHANNEL_ACCESS_TOKEN` 會被 terminal 展開成實際 token 值），導致替換結果破損。**解法**：(1) 使用 `open(filepath, 'rb')` 讀取原始 bytes 做替換、(2) 或寫臨時 Python 腳本 (`write_file` → `python3 /tmp/fix.py`) 處理替換、(3) 避免 `terminal` 輸出中含有敏感環境變數名的內容。
21. **Cron 執行 Python 腳本不會自動 source .env** — `hermes cron` 啟動的 Python 進程只繼承系統環境變數（/proc/1/environ），不自動載入 `/data/.hermes/.env`。若腳本用 `os.environ.get()` 讀取 .env 中的變數，Cron 執行時會讀到空值。**解法**：(1) Cron job prompt 中必須寫 `set -a; source /data/.hermes/.env; set +a; python3 script.py` 而非 `python3 script.py`；(2) 或改用 wrapper shell script：`#!/bin/bash\nset -a\nsource /data/.hermes/.env\nset +a\npython3 script.py`；(3) 驗證：`grep LINE /data/.hermes/.env` 確認兩個變數都有，再用 `set -a; source .env; python3 -c "import os; print(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN','')[:10])"` 確認 Python 能讀到。
19. **原始 live_signal_bot.py 含硬編碼 LINE credentials** — `references/實盤訊號計算與回報程式live_signal_bot.py` 仍保留第 28-29 行的硬編碼 `LINE_CHANNEL_ACCESS_TOKEN` 和 `LINE_USER_ID`。HF Space 重建後 .env 會丟失，此檔案可用作 credential 恢復來源。恢復步驟：(1) `grep LINE_CHANNEL_ACCESS_TOKEN references/實盤訊號計算與回報程式live_signal_bot.py`；(2) `echo 'LINE_CHANNEL_ACCESS_TOKEN=<提取的值>' >> /data/.hermes/.env`；(3) 同法恢復 `LINE_USER_ID`；(4) 驗證 `source .env` 後 Python 能讀到兩個值。
20. **StackVM EMA 算子係數和=1.4 不是標準 EMA** — `0.8 * a + 0.6 * roll(a,1)` 係數和 1.4 倍放大，嵌套 EMA(EMA(x)) 達 ~1.96× 放大。當 DOWJONES Z=+1.44 經雙重 EMA 後為 +2.72（而非 ~+1.44）。這使得 mid_cap_tech 公式中 `ABSORPTION - EMA(EMA(DOWJONES))` 在牛市中**恆為大負數**（左邊 ~1.27 永遠不夠抵消 ~4.34）。traditional 公式同理，GATE 兩分支都偏空。**根因**：EMA 放大 + 公式結構設計使得牛市越強訊號越空。詳見 `references/live-signal-bot-formula-audit-2026-06-26.md`。
21. **公式結構性偏空**：mid_cap_tech 的 `(ABSORPTION - (... + EMA(EMA(DOWJONES))))` 結構在美股多頭時恆為負（ABSORPTION bounded [-2,+2] vs EMA 雙重放大 unbounded）；traditional 的 GATE 兩個分支（TX_INST_NET_OI 或 價差×負spread）在外資偏空時都偏負。**需要重新訓練**（修正 EMA 係數）或調整公式結構。診斷方法：對最後一天特徵做完整 StackVM trace，比較每步驟值，確認是否某算子放大效果失控。詳見 `references/live-signal-bot-formula-audit-2026-06-26.md` 完整數值列式。
22. **retail_net_oi 定義已修正為對齊 V7** — V7 ipynb (L439): `retail_net_oi = total_oi - inst_net_oi`（總量扣除外資 = 散戶+投信+自營商），Bot 腳本舊版 L399: `retail_net_oi = -inst_net_oi`（外資取反）已於 v1.2 修正。修正方式：加總 FinMind API 回傳之三投資者（自營商/投信/外資）的 long-short 得 total_net_oi，再 `retail_net_oi = total_net_oi - inst_net_oi`。數值差異：TX 外資 -76391 時，舊BOT=+76391，V7正確=+65888，差約-10503；MTX 更顯著：舊BOT=+268，V7正確=-6794（正負號都不同）。詳見 `references/v7-vs-bot-finmind-field-comparison-2026-06-26.md`。
23. **V7 ipynb 的 adapt_finmind_data 有 60% fallback 估算外資** — 若 Kaggle CSV 只有 `oi` 欄而無 `inst_net_oi`，V7 會用 `total_oi * 0.6` 估算外資部位。而 Bot 腳本直接用 FinMind API 的 long-short 差值計算精確外資淨 OI。若訓練數據走的是 fallback 路徑，訓練時的 inst_net_oi 分布（估算值的 60% 水準）和推論時（精確值）不同，會造成 train-inference skew。檢查方法：查看 Kaggle Dataset 的 `futures_oi.csv` 是否有 `inst_net_oi` 欄。詳見 `references/v7-vs-bot-finmind-field-comparison-2026-06-26.md`。
24. **Bot v1.2 已修正 retail_net_oi 並更新 V8 公式** — 2026-06-27：(a) retail_net_oi 從 `-inst_net_oi` 改為 `total_net_oi - inst_net_oi`，加總三投資者(外資/投信/自營商) long-short 得 total；(b) mid_cap_tech 公式更新為 V8 tokens [16,20,13,33,28,32,28,22,12,27,22,13,22,27,22]，解碼 `(TX_INST_NET_OI ADD ABS(((SP500_CLOSE ADD SIGN(LAG(SIGN(MAX3(ATR))))) ADD ABS(SURF_ENTRY)) ADD ATR))`；(c) traditional 公式更新為 V8 tokens [16,17,17,33,31,27,31,27,24,27,10,31,33,23,22]，解碼 `(TX_INST_NET_OI ADD (ABS((MTX_RETAIL_OI MUL ABS(EMA(ABS(EMA(MAX3(MTX_RETAIL_OI))))))) SUB MAX3(EMA(CVD_PROXY))))`；(d) 抓取天數從 90→120 天以確保 robust_normalize(window=60) 有足夠 warmup 期。
25. **公式審計結論 (V7→V8 對比)** — V7 舊 mid_cap_tech 公式 `(ABSORPTION SUB (... ADD EMA(EMA(DOWJONES))))` 因 EMA 1.4× 係數放大導致結構性偏空（bounded ABSORPTION vs unbounded EMA 雙重放大，永遠大負數）。V8 新公式改用 TX_INST_NET_OI 為基底 + ADD 運算，消除 SUB 減法結構偏空問題。traditional V7 舊公式 GATE 兩分支都偏空，V8 新公式改為 `(TX_INST_NET_OI ADD (retail_OI 項 SUB CVD_PROXY 項))`，外資正部位時 ADD 直接貢獻正 signal，不再全依賴負向條件分支。V8 mid_cap_tech 實測：3/7 看多 + 2/7 觀望 + 2/7 看空（舊版 7/7 全看空），分散度大幅改善。
26. **robust_normalize NaN bug (v1.2，已於 v1.3→v1.4 修正)** — 舊版 `robust_normalize` 使用 `np.median` 計算滾動窗口的中位數和 MAD，但 `np.median` 在輸入含 NaN 時回傳 NaN，導致所有含 NaN 的特徵 Z-score 全部歸零。**影響特徵**：ATR（rolling(14) 前 13 天 NaN）、CVD_PROXY（rolling(20) 前 19 天 NaN + 部分零值）、VOL_BREAKOUT（rolling(5) 前 4 天 NaN）、MOM_REV（rolling(5) 前 4 天 NaN）、FIVE_DAY_HIGH（rolling(5) 前 4 天 NaN）、PRESSURE/FOMO/DEV/LIQ_SCORE 的前幾天 NaN 等。**v1.3 修正**：(a) 採用 `np.nanmedian` 替代 `np.median`；(b) 在 `compute_features` 中先對特徵做 `fillna(0)` 再傳入 `robust_normalize`，確保輸入無 NaN；(c) robust_normalize 內部增加 valid count 檢查，有效值少於 window/2 時輸出 0。**v1.4 防彈版**：(d) `len(arr)<window` 回傳 `np.zeros_like` 非 `return arr`（防 NaN 洩漏到 StackVM）；(e) `result` 初始化 `np.zeros_like` 非 `np.copy(arr)`；(f) 逐值檢查 `np.isnan(arr[i])` 不依賴事後 `result[np.isnan(result)]=0` 兜底；(g) warmup 期逐值檢查 arr[i] NaN；(h) `np.errstate(all='ignore')` 壓制 RuntimeWarning；(i) 保留 `n_valid >= max(window//2, 10)` 嚴格門檻。**驗證**：ATR 從全零變為 +0.387（鴻海）、7 項單元測試全通（正常/不足/含NaN/全零/None/中間NaN/全NaN，輸出永不包含 NaN 或 Inf）。
27. **INST_FLOW 和 MARGIN_PRESS 在 Bot 中恆為零** — 由於 `get_live_features()` 未抓取法人買賣超和融資融券資料（`inst_df=None, margin_df=None`），compute_features 中這兩個因子恆為 0。這意味 GRPO 訓練時可能用了非零的 INST_FLOW/MARGIN_PRESS，但 Bot 推論時它們是 0 → train-inference skew。改善方案：(a) 在 get_live_features 中增加 FinMind `TaiwanStockInstitutionalInvestorsBuySell` 和 `TaiwanStockMarginPurchaseShortSale` API 呼叫取真實值；(b) 或訓練時也設為 0 以消除 skew。當前 V8 公式不含這兩個因子所以不影響訊號，但未來公式若用到會有問題。
28. **SURF_ENTRY 幾乎全零是正確行為** — `surf_entry = 1.0 when |close - MA20|/MA20 < 0.01 else 0.0`，表示股價非常接近 20 日均線時為 1（只佔約 1-5% 的天數）。robust_normalize 後非零天變成極端值，其餘為 0。這是設計特性而非 bug，但需注意此因子在 StackVM 中常被 ABS 算子消除貢獻。