"""
台股 AI Dig Money 系統 - 每日盤後掃描腳本
適用於 cron job 自動執行
輸出：通過四階段篩選的交易信號
"""
import sys
import json
import argparse
from datetime import datetime, timedelta


def main():
    parser = argparse.ArgumentParser(description="台股 AI Dig Money 每日掃描")
    parser.add_argument("--stocks", nargs="+", default=None,
                       help="股票代碼列表 (預設: 台灣50)")
    parser.add_argument("--capital", type=float, default=1_000_000,
                       help="總資金 (預設: 100萬)")
    parser.add_argument("--output", type=str, default="/tmp/dig_money_signals.json",
                       help="輸出 JSON 路徑")
    parser.add_argument("--demo", action="store_true",
                       help="使用示範資料 (不需 twstock)")
    args = parser.parse_args()

    # 動態 import
    sys.path.insert(0, "/data/.hermes/skills/research/twstock-alpha-gpt/scripts")
    from ai_dig_money_core import TWDataLoader, AIDigMoneyPipeline
    from twstock_alpha_engine import TWFeatureEngineer, TWBacktest, FormulaDecoder

    print("=" * 60)
    print(f"  台股 AI Dig Money - 每日盤後掃描")
    print(f"  日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # 1. 載入資料
    print("\n[Step 1] 載入台股資料...")
    if args.demo:
        loader = TWDataLoader(stock_list=args.stocks, days=120)
    else:
        try:
            import twstock
            loader = TWDataLoader(stock_list=args.stocks, days=120)
        except ImportError:
            print("  twstock 未安裝，使用示範資料")
            loader = TWDataLoader(stock_list=args.stocks, days=120)

    df = loader.load()
    print(f"  載入 {df['stock_id'].nunique()} 檔，{len(df)} 筆日K")

    # 2. 計算因子
    print("\n[Step 2] 計算 16 維因子...")
    feat_df = TWFeatureEngineer.compute_features(df)
    n_features = len([c for c in feat_df.columns if c not in
                      ["date", "stock_id", "open", "high", "low", "close", "volume"]])
    print(f"  完成：{n_features} 個因子欄位")

    # 3. 四階段篩選
    print("\n[Step 3] 執行四階段篩選...")
    pipeline = AIDigMoneyPipeline()
    signals = pipeline.run(feat_df)

    # 4. 輸出結果
    print("\n[Step 4] 輸出信號...")
    output = {
        "scan_date": datetime.now().isoformat(),
        "total_stocks_scanned": df["stock_id"].nunique(),
        "signals_count": len(signals),
        "signals": [],
    }

    for s in signals:
        output["signals"].append({
            "stock_id": s.stock_id,
            "composite_score": round(s.composite_score, 2),
            "risk_grade": s.risk_grade.value,
            "entry_price": round(s.entry_price, 2),
            "stop_loss": round(s.stop_loss, 2),
            "target_price": round(s.target_price, 2),
            "stage1_score": round(s.stage1_score, 2),
            "stage2_score": round(s.stage2_score, 2),
            "stage3_score": round(s.stage3_score, 2),
            "cvd_status": s.cvd_status,
            "absorption_detected": s.absorption_detected,
            "five_day_high_break": s.five_day_high_break,
            "vol_breakout": s.vol_breakout,
            "alpha_formula": s.alpha_formula,
        })

    # 寫入 JSON
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"  結果已寫入: {args.output}")

    # 終端輸出摘要
    print(f"\n{'='*60}")
    print(f"  掃描完成！{len(signals)} 檔通過四階段篩選")
    print(f"{'='*60}")
    for i, s in enumerate(signals[:10], 1):
        print(f"  [{i}] {s.stock_id} | 分數:{s.composite_score:.1f} | "
              f"等級:{s.risk_grade.value} | "
              f"進場:{s.entry_price:.1f} 止損:{s.stop_loss:.1f} "
              f"目標:{s.target_price:.1f}")

    if not signals:
        print("  今日無符合條件的標的，空手等待。")

    return output


if __name__ == "__main__":
    main()
