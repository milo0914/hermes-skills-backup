#!/usr/bin/env python3
"""
診斷 pandas groupby 迴圈中 DataFrame view bug 的通用腳本。

症狀：compute_features(df_with_N_stocks) 回傳只有最後一檔股票的結果。
根因：g[keep_cols] 回傳 view（非 copy），append 後下一個迭代覆蓋 g，
     導致 list 中所有 frame 指向同一個（最後一個）DataFrame。

使用方式：
  python3 diagnose_groupby_view_bug.py <source_file.py> <function_name> <test_data_rows>

範例：
  python3 diagnose_groupby_view_bug.py grpo_regime_training_kaggle.py compute_features 120
"""

import sys, importlib, tempfile, os, types
import pandas as pd
import numpy as np

def generate_test_data(n_rows=120, n_stocks=4):
    """生成 4 檔股票的測試 DataFrame"""
    stock_ids = ["2330", "2454", "1301", "2882"]
    dates = pd.bdate_range("2025-01-01", periods=n_rows // n_stocks)
    rows = []
    for sid in stock_ids:
        for d in dates:
            rows.append({
                "date": d, "stock_id": sid,
                "open": 100 + np.random.randn() * 5,
                "high": 105 + np.random.randn() * 5,
                "low": 95 + np.random.randn() * 5,
                "close": 100 + np.random.randn() * 5,
                "volume": 10000 + int(np.random.randn() * 3000),
            })
    df = pd.DataFrame(rows)
    # 產生空的 inst/margin/futures/us_indices
    inst_df = pd.DataFrame(columns=["date", "stock_id", "foreign_net", "trust_net", "dealer_self_net", "total_net"])
    margin_df = pd.DataFrame(columns=["date", "stock_id", "margin_balance", "short_balance"])
    futures_oi_df = pd.DataFrame(columns=["date", "tx_inst_net_oi", "mtx_retail_oi"])
    us_indices_df = pd.DataFrame(columns=["date", "nasdaq_close", "sp500_close", "dowjones_close"])
    return df, inst_df, margin_df, futures_oi_df, us_indices_df


def diagnose(source_file, function_name="compute_features"):
    """載入 compute_features 並測試 groupby 迴圈是否只保留最後一檔"""
    # 生成測試數據
    df, inst_df, margin_df, futures_oi_df, us_indices_df = generate_test_data()
    n_input_stocks = df["stock_id"].nunique()
    input_stocks = sorted(df["stock_id"].unique())

    print(f"輸入: {len(df)} rows, {n_input_stocks} stocks: {input_stocks}")

    # 動態載入函數
    # 方法: monkey-patch globals 然後 exec
    with open(source_file) as f:
        code = f.read()

    # 建立隔離 namespace
    ns = {}
    try:
        exec(compile(code, source_file, "exec"), ns)
    except Exception as e:
        print(f"編譯失敗: {e}")
        return False

    func = ns.get(function_name)
    if func is None:
        # 可能是 class method
        for name, obj in ns.items():
            if isinstance(obj, type):
                for attr_name in dir(obj):
                    if attr_name == function_name:
                        print(f"找到 {name}.{function_name}")
                        # 需要實例化
                        try:
                            instance = obj()
                            func = getattr(instance, function_name)
                        except:
                            pass
        if func is None:
            print(f"找不到函數 {function_name}")
            return False

    # 呼叫函數
    try:
        if function_name == "compute_features":
            # 嘗不同簽名
            import inspect
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            if "futures_oi_df" in params:
                result = func(df, inst_df=inst_df, margin_df=margin_df,
                             futures_oi_df=futures_oi_df, us_indices_df=us_indices_df)
            elif "inst_df" in params:
                result = func(df, inst_df=inst_df, margin_df=margin_df)
            else:
                result = func(df)
        else:
            result = func(df)
    except Exception as e:
        print(f"執行失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 檢查結果
    if isinstance(result, pd.DataFrame):
        output_stocks = sorted(result["stock_id"].unique()) if "stock_id" in result.columns else ["?"]
        n_output = len(result)
        n_output_stocks = len(output_stocks)
    else:
        print(f"回傳類型非 DataFrame: {type(result)}")
        return False

    print(f"輸出: {n_output} rows, {n_output_stocks} stocks: {output_stocks}")

    if n_output_stocks < n_input_stocks:
        missing = set(input_stocks) - set(output_stocks)
        print(f"\n*** BUG 確認: {n_input_stocks} → {n_output_stocks} 檔, 丟失: {missing} ***")
        print("根因: groupby 迴圈中 g[keep_cols] 回傳 view 而非 copy")
        print("修復: result_frames.append(g[keep_cols].copy())")
        return False
    else:
        print(f"\n✓ 所有 {n_input_stocks} 檔股票都保留在輸出中")
        return True


def check_append_pattern(source_file):
    """掃描檔案中 groupby + append 模式，標記潛在 view bug"""
    with open(source_file) as f:
        lines = f.readlines()

    in_groupby = False
    groupby_line = 0
    issues = []

    for i, line in enumerate(lines, 1):
        if "groupby" in line and "for" in line:
            in_groupby = True
            groupby_line = i
        if in_groupby and (".append(" in line or "append(" in line):
            # 檢查是否有 .copy()
            if ".copy()" not in line and "append(g[" in line:
                issues.append((i, groupby_line, line.rstrip()))
        # 簡單追蹤：如果縮排回到 groupby 層級以下，結束追蹤
        if in_groupby and line.strip() and not line.startswith(" " * 8):
            if not line.strip().startswith("#") and not line.strip().startswith("for"):
                in_groupby = False

    if issues:
        print(f"\n潛在 view bug 位置:")
        for line_no, gb_line, content in issues:
            print(f"  L{line_no} (groupby at L{gb_line}): {content}")
            print(f"    → 修復: 加 .copy()")
    else:
        print("\n未發現潛在 view bug（但仍有可能是 method chain 中的 view）")

    return len(issues) == 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    source_file = sys.argv[1]
    func_name = sys.argv[2] if len(sys.argv) > 2 else "compute_features"

    print(f"=== 診斷 {source_file} 的 {func_name} ===\n")

    # Step 1: 掃描程式碼模式
    print("--- Step 1: 靜態掃描 append 模式 ---")
    pattern_ok = check_append_pattern(source_file)

    # Step 2: 實際執行測試
    print(f"\n--- Step 2: 實際執行測試 ---")
    exec_ok = diagnose(source_file, func_name)

    if exec_ok:
        print("\n✓ 無 view bug")
    else:
        print("\n✗ view bug 確認，需加 .copy()")
