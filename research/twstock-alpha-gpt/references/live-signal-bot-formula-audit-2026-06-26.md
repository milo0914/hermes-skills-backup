# Live Signal Bot 公式計算審計 (2026-06-26)

## 問題
mid_cap_tech 和 traditional 的訊號結果全部都是大負數 (tanh < -0.9)，需要確認公式計算過程是否有問題。

## 審計結論：3 層原因

### 第 1 層：期貨 BUG (技術問題，已由踩坑3修復)

Cron 腳本 v1.0 用 `raw["name"] == "外資及陸資"` 過濾，但 FinMind API 回傳 `institutional_investors` + `"外資"` —— 詳見踩坑3。

**影響**：修復前 TX_INST_NET_OI / MTX_RETAIL_OI / TX_MTX_SPREAD 全 = 0。

**但修復後結果反而更空！** 因為正確的期貨數據（外資 TX 淨 OI ≈ -76000）Z-score 後為 -1.615，被 mid_cap_tech 和 traditional 公式引用。

### 第 2 層：EMA 算子係數非標準 (設計缺陷)

StackVM 中的 EMA 算子定義為：
```python
res = 0.8 * a + 0.6 * np.roll(a, 1)
```

**問題**：係數和 = 0.8 + 0.6 = **1.4**，不是標準 EMA 的 1.0。

標準 EMA 格式：`α * a + (1-α) * roll(a,1)`，其中 α ∈ (0,1)，係數和 = α + (1-α) = 1.0。

此算子是**放大器**：
- 穩態時 EMA(x) ≈ 1.4 × |x|
- 嵌套時 EMA(EMA(x)) ≈ 1.96 × |x|

**實測** (DOWJONES_CLOSE Z-score = +1.4406)：
- EMA(+1.4406) = +1.9893 (預期標準 EMA ≈ +1.44)
- EMA(+1.9893) = +2.7210 (預期標準 ≈ +1.99)
- 放大倍率: 2.7210 / 1.4406 = **1.89×**

### 第 3 層：公式結構在多頭市場恆偏空 (市場原因 + 設計交互)

#### mid_cap_tech 公式結構
```
結果 = ABSORPTION - (ABS(TX_MTX_SPREAD) - 小項 + EMA(EMA(DOWJONES_CLOSE)))
         ↑ 永遠 ≥ 0      ↑ 永遠 ≥ 0              ↑ 多頭時正值且被放大
```

分解計算 (2317 鴻海, 2026-06-26)：

| 步驟 | 運算 | Z-score 値 |
|------|------|-----------|
| 0 | PUSH ABSORPTION | +1.2692 |
| 1 | PUSH TX_MTX_SPREAD | -1.6196 |
| 2 | ABS(TX_MTX_SPREAD) | +1.6196 |
| 3 | PUSH LIQ_SCORE | +0.0000 |
| 4 | EMA(LIQ_SCORE) | +0.0000 |
| 5-8 | ABS(SIGN(OUTLIER(ABS(...)))) | +0.0000 |
| 9 | 1.6196 - 0.0000 | +1.6196 |
| 10 | PUSH DOWJONES_CLOSE | +1.4406 |
| 11 | EMA(DOWJONES_CLOSE) | +1.9893 |
| 12 | EMA(EMA(DOWJONES_CLOSE)) | +2.7210 |
| 13 | 1.6196 + 2.7210 | +4.3406 |
| 14 | 1.2692 - 4.3406 | **-3.0713** |
| | tanh(-3.0713) | **-0.9957 → 強力看空** |

**結構性問題**：
- ABSORPTION Z-score ~1.27 (bounded)
- EMA(EMA(DOWJONES)) 在多頭中 ~2.72 (放大器)
- 右邊 = 4.34 >> 左邊 = 1.27 → **恆為大負數**
- 當道瓊 Z=0 時: 右邊 ≈ 1.62, 左邊 ≈ 1.27, 結果 ≈ -0.35 (略偏空)
- **牛市越強，訊號越空** ← 與直覺相反

#### traditional 公式結構
```
GATE(MAX3(MTX_RETAIL_OI)>0 ? TX_INST_NET_OI : ((EMA(MTX_RETAIL_OI) - MAX3(TX_INST_NET_OI)) × LAG(LAG(MAX3(TX_MTX_SPREAD)))))
```

分解計算 (1301 台塑, 2026-06-26)：

| 步驟 | 運算 | Z-score 値 |
|------|------|-----------|
| 0 | PUSH TX_INST_NET_OI | -1.6150 |
| 1 | PUSH MTX_RETAIL_OI | +0.6090 |
| 2 | EMA(MTX_RETAIL_OI) | +0.4581 |
| 3-4 | MAX3(TX_INST_NET_OI) | -1.6150 |
| 5 | 0.4581 - (-1.6150) | +2.0731 |
| 6-7 | MAX3(TX_MTX_SPREAD) | -1.6196 |
| 8-9 | LAG(LAG(-1.6196)) | -1.4142 |
| 10 | +2.0731 × -1.4142 | -2.9318 |
| 11-12 | MAX3(MTX_RETAIL_OI) = +0.609 > 0 | 選 TX_INST_NET_OI |
| 13 | GATE → -1.6150 | -1.6150 |
| | tanh(-1.615) | **-0.9239 → 看空** |

**結構性問題**：
- GATE TRUE 分支 = TX_INST_NET_OI (目前外資偏空，Z ≈ -1.6)
- GATE FALSE 分支 = 正數 × 負數 = 負數 (TX_MTX_SPREAD 為負)
- **兩分支都偏空**，因為外資持續做多台指期空單

### 對照：BROKEN (期貨=0) vs CORRECT (期貨正常)

| Regime | Stock | BROKEN tanh | CORRECT tanh | 差異 |
|--------|-------|-------------|--------------|------|
| mid_cap_tech | 2317 鴻海 | -0.8960 | -0.9957 | -0.10 |
| traditional | 1301 台塑 | +0.0000 (觀望) | -0.9239 (看空) | -0.92 |

注意：traditional 在 BROKEN 模式下全為 0 (觀望)，修復後變成看空。這符合市場真實狀況（外資偏空），但用戶之前看到的「觀望」其實是因為數據缺失導致的假象。

## ABSORPTION 特徵特性

ABSORPTION = (high - close) / (high - low) × volume
- **永遠 ≥ 0**（因為 high ≥ close 且 volume ≥ 0）
- 唯有 close == high 時 = 0
- Z-score 正規化後通常在 [-2, +2] 範圍
- 作為公式的「被減數」，永遠無法超越一個被放大的正數

## 美股指數 Z-score 特性

當前道瓊持續創高（~51900），近 60 日 median ≈ 49669，MAD ≈ 1009。
→ Z-score ≈ (51920 - 49669) / (1.4826 × 1009) ≈ +1.50
→ 經 EMA 雙重放大後 ≈ +2.72

**當美股處於多頭趨勢時，DOWJONES_CLOSE Z-score 恆正且被 EMA 放大器放大**，使得任何「減去 EMA(EMA(DOWJONES))」的公式結構都會產生大負數。

## 建議修復方向

1. **立即修復**：確認 cron 腳本已套用踩坑3的 filter/欄位名修正（v1.2）
2. **短期**：修改 EMA 算子係數為標準格式（如 0.4 + 0.6 = 1.0），需重新訓練所有公式
3. **中期**：重新訓練時加入約束條件，避免 EMA 嵌套超過 1 層
4. **長期**：考慮在 reward function 中加入訊號分布均衡性懲罰（避免公式結構性偏多/偏空）

## 數據來源
- FinMind API (2026-06-26 17:30 實測)
- 2317 鴻海 OHLCV: 61 交易日
- TX 外資: 61 筆, 末值 inst_net_oi = -76391
- MTX 外資: 61 筆, 末值 inst_net_oi = -268
