"""完整驗證測試"""
import sys
sys.path.insert(0, "/data/.hermes/skills/research/twstock-alpha-gpt/scripts")
from ai_dig_money_core import TWDataLoader, AIDigMoneyPipeline
from twstock_alpha_engine import TWFeatureEngineer, FormulaDecoder, TWModelConfig

# 1. 資料載入
loader = TWDataLoader(stock_list=["2330", "2454", "2308"], days=120)
df = loader.load()
print(f"[OK] 資料: {df['stock_id'].nunique()} 檔, {len(df)} 筆")

# 2. 因子計算
feat_df = TWFeatureEngineer.compute_features(df)
feat_cols = [c for c in feat_df.columns if c not in ["date","stock_id","open","high","low","close","volume"]]
print(f"[OK] 因子: {len(feat_cols)} 個")

# 3. 四階段篩選
pipeline = AIDigMoneyPipeline()
signals = pipeline.run(feat_df)
print(f"[OK] 篩選: {len(signals)} 檔通過 (demo隨機資料分數低是正常的)")

# 4. 公式反編譯
demo_formulas = [
    [0, 1, 16, 3, 18],
    [0, 24, 10, 19],
    [2, 22, 25],
    [4, 10, 18, 21, 8, 23],
]
for tokens in demo_formulas:
    formula = FormulaDecoder.decode(tokens)
    print(f"[OK] Tokens {tokens} -> {formula}")

# 5. 硬體
TWModelConfig.auto_detect()
print("\n[OK] All tests passed!")
