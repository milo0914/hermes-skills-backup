# v1.3 一致性審計與修正記錄 (2026-06-27)

## 審計背景
V7 訓練結果 val_ic 非常高，以 V7 為正確基準，對 Bot 腳本進行一致性審計與修正。

## 發現的問題與修正

### 1. retail_net_oi 定義不一致 (v1.2 已修正)
- **V7 定義**: `retail_net_oi = total_net_oi - inst_net_oi` (總量扣除外資)
- **Bot 舊版**: `retail_net_oi = -inst_net_oi` (外資取反)
- **數值差異**: TX 外資 -76391 時，舊BOT=+76391，V7正確=+65888，差 -10503
- **MTX 更顯著**: 舊BOT=+268，V7正確=-6794（正負號都不同）
- **修正方式**: 加總 FinMind API 三投資者(外資/投信/自營商) long-short 得 total_net_oi

### 2. robust_normalize NaN bug (v1.3 修正)
- **症狀**: ATR、CVD_PROXY、VOL_BREAKOUT、FIVE_DAY_HIGH 等因子的 Z-score 全部為 0
- **根因**: `np.median` 在輸入含 NaN 時回傳 NaN → `mad > 1e-8` 為 False → 強制設 0
- **觸發條件**: ATR rolling(14) 前 13 天 NaN、CVD_PROXY rolling(20) 前 19 天 NaN 等
- **修正**: `np.median` → `np.nanmedian`，並在 compute_features 中先 fillna(0) 再傳入
- **驗證**: ATR: 全零→+0.387、CVD_PROXY: 全零→-1.040、VOL_BREAKOUT: 全零→+0.936

### 3. 抓取天數不足 (v1.2 已修正)
- 舊版抓 90 天，robust_normalize window=60 需至少 120 天 warmup
- 修正：120 天

## 欄位名稱一致性確認

### FinMind API v4 → Bot 腳本欄位對照
| FinMind API 欄位 | Bot 內部欄位 | 適配位置 |
|-----------------|-------------|---------|
| Trading_Volume | volume | L375 rename |
| max | high | L375 rename |
| min | low | L375 rename |
| institutional_investors | (用於篩選外資) | L395 |
| long_open_interest_balance_volume | (計算 net_oi) | L397/L403 |
| short_open_interest_balance_volume | (計算 net_oi) | L397/L405 |
| Close (USStockPrice) | close | L448 rename |

### V7 ipynb vs Bot compute_features 一致性
| 項目 | V7 | Bot v1.3 | 一致 |
|------|-----|----------|------|
| robust_normalize window | 60 | 60 | ✅ |
| robust_normalize clip | 5.0 | 5.0 | ✅ |
| robust_normalize MAD factor | 1.4826 | 1.4826 | ✅ |
| robust_normalize NaN 處理 | nanmedian | nanmedian | ✅ (v1.3) |
| DECAY 係數 | 0.8*a + 0.6*roll(a,1) | 0.8*a + 0.6*roll(a,1) | ✅ |
| retail_net_oi | total - inst | total - inst | ✅ (v1.2) |
| 美股 shift(1) | shift(1) | shift(1) | ✅ |
| ATR 週期 | rolling(14) | rolling(14) | ✅ |

### 仍已知不一致的項目
| 項目 | V7 | Bot v1.3 | 影響 |
|------|-----|----------|------|
| INST_FLOW | 從 CSV 讀取 total_net | None→fillna(0)→全零 | V8 公式未使用，不影響訊號 |
| MARGIN_PRESS | 從 CSV 讀取 | None→fillna(0)→全零 | V8 公式未使用，不影響訊號 |
| adapt_finmind_data 60% fallback | total_oi * 0.6 估算外資 | API 直接計算精確值 | 量值差異但方向一致 |

## V8 公式修正後 Signal 結果 (2026-06-27)

### mid_cap_tech: `(TX_INST_NET_OI ADD ABS(...ATR...))`
| 股票 | Signal | 判定 |
|------|--------|------|
| 聯電(2303) | -0.845 | 看空 |
| 鴻海(2317) | -0.239 | 觀望 |
| 廣達(2382) | -0.476 | 看空 |
| 聯發科(2454) | -0.027 | 觀望 |
| 宏達電(3008) | +0.368 | 看多 |
| 聯詠(3034) | +1.000 | 看多 |
| 日月光投控(3711) | +0.502 | 看多 |

V8 vs V7: 3/7 看多 + 2/7 觀望 + 2/7 看空 (V7 舊版 7/7 全看空)，分散度大幅改善。

### traditional: `(TX_INST_NET_OI ADD (ABS(MTX_RETAIL_OI × ...) SUB MAX3(EMA(CVD_PROXY))))`
| 股票 | Signal | 判定 |
|------|--------|------|
| 台塑(1301) | -0.999 | 看空 |
| 台泥(1101) | -0.986 | 看空 |
| 中鋼(2002) | -1.000 | 看空 |

traditional 仍偏空，主因：外資淨 OI 為負(-1.615)且 CVD_PROXY 偏負，兩項都壓低 signal。

## 修正後版本號
- v1.1: 期貨籌碼 rename bug 修正
- v1.2: retail_net_oi 定義修正 + V8 公式更新 + 90→120 天
- v1.3: robust_normalize NaN bug 修正 (np.median→np.nanmedian)

## 下一步建議
1. INST_FLOW/MARGIN_PRESS 資料源整合 (消除 train-inference skew)
2. traditional 公式偏空問題可能需要重新訓練
3. EMA 係數 0.8+0.6=1.4 在訓練和推論都一致，但需關注放大效應
