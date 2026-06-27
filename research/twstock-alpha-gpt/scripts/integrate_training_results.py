#!/usr/bin/env python3
"""
整合 Kaggle GRPO 訓練結果到本地 twstock-alpha-gpt 系統

用法:
    python3 integrate_training_results.py /path/to/kaggle/output/

輸入 (Kaggle kernel output):
    - best_strategy_per_regime.json: 每 regime 最佳因子公式
    - training_history.json: 訓練歷程 (loss, reward, IC)
    - walk_forward_results.json: Walk-forward 驗證結果 (如有)

輸出:
    - 更新 scripts/best_strategy.json (供本地推論使用)
    - 更新 scripts/training_report.json (訓練報告摘要)
    - 備份原始 Kaggle 輸出到 references/

此腳本由 twstock-alpha-gpt skill 的 TODO #14 使用：
Kaggle kernel 完成後，執行此腳本將訓練產物轉換為本地系統可消費的格式。
"""
import json
import os
import sys
import shutil
from datetime import datetime

SKILL_DIR = "/data/.hermes/skills/research/twstock-alpha-gpt"
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")
OUTPUT_FILES = [
    "best_strategy_per_regime.json",
    "training_history.json",
    "walk_forward_results.json",
]


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def convert_to_local_strategy(kaggle_strategy):
    """
    將 Kaggle best_strategy_per_regime.json 轉換為本地 best_strategy.json 格式

    Kaggle 格式:
        {"LARGE_CAP": {"best_formula": [tokens], "best_formula_str": "...", ...}}

    本地格式 (ai_dig_money_core.py phase2 消費):
        {"regimes": {"LARGE_CAP": {"formula_tokens": [...], ...}}, "metadata": {...}}
    """
    local = {
        "regimes": {},
        "metadata": {
            "trained_at": datetime.now().isoformat(),
            "kernel_slug": "",
            "vocab_size": 34,
            "n_features": 22,
            "all_feature_names": [
                "RET", "LIQ_SCORE", "PRESSURE", "FOMO", "DEV", "LOG_VOL",
                "INST_FLOW", "MARGIN_PRESS", "FIVE_DAY_HIGH", "VOL_BREAKOUT",
                "CVD_PROXY", "ABSORPTION", "SURF_ENTRY", "ATR", "CLOSE_POS", "MOM_REV",
                "TX_INST_NET_OI", "MTX_RETAIL_OI", "TX_MTX_SPREAD",
                "NASDAQ_CLOSE", "SP500_CLOSE", "DOWJONES_CLOSE",
            ],
        },
    }

    for regime_name, regime_data in kaggle_strategy.items():
        local["regimes"][regime_name] = {
            "formula_tokens": regime_data.get("best_formula", []),
            "formula_str": regime_data.get("best_formula_str", "UNKNOWN"),
            "ic": regime_data.get("best_ic", 0.0),
            "reward": regime_data.get("best_reward", 0.0),
            "train_steps": regime_data.get("train_steps", 0),
        }

    return local


def generate_training_report(kaggle_strategy, training_history):
    report = {
        "generated_at": datetime.now().isoformat(),
        "regime_summary": {},
        "training_diagnostics": {},
    }

    if kaggle_strategy:
        for regime_name, regime_data in kaggle_strategy.items():
            report["regime_summary"][regime_name] = {
                "best_formula": regime_data.get("best_formula_str", "N/A"),
                "best_ic": regime_data.get("best_ic", 0.0),
                "best_reward": regime_data.get("best_reward", 0.0),
                "train_steps": regime_data.get("train_steps", 0),
            }

    if training_history:
        for regime_name, history in training_history.items():
            steps = history.get("steps", [])
            losses = history.get("losses", [])
            rewards = history.get("rewards", [])
            ics = history.get("ics", [])
            report["training_diagnostics"][regime_name] = {
                "total_steps": len(steps),
                "final_loss": losses[-1] if losses else None,
                "final_reward": rewards[-1] if rewards else None,
                "final_ic": ics[-1] if ics else None,
                "max_reward": max(rewards) if rewards else None,
                "max_ic": max(ics) if ics else None,
                "loss_trend": "converging" if len(losses) > 10 and losses[-1] < losses[0] else "unknown",
            }

    return report


def validate_integration(local_strategy):
    issues = []
    if local_strategy["metadata"]["vocab_size"] != 34:
        issues.append(f"VOCAB_SIZE mismatch: expected 34, got {local_strategy['metadata']['vocab_size']}")
    if local_strategy["metadata"]["n_features"] != 22:
        issues.append(f"N_FEATURES mismatch: expected 22, got {local_strategy['metadata']['n_features']}")
    expected_regimes = ["LARGE_CAP", "MID_CAP_TECH", "TRADITIONAL", "FINANCIAL"]
    for regime in expected_regimes:
        if regime not in local_strategy["regimes"]:
            issues.append(f"Missing regime: {regime}")
        else:
            tokens = local_strategy["regimes"][regime].get("formula_tokens", [])
            if not tokens:
                issues.append(f"Empty formula for regime: {regime}")
    return issues


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 integrate_training_results.py /path/to/kaggle/output/")
        sys.exit(1)

    output_dir = sys.argv[1]
    print(f"=== Kaggle GRPO Training Results Integration ===")
    print(f"Input: {output_dir}")

    kaggle_strategy = load_json(os.path.join(output_dir, "best_strategy_per_regime.json"))
    training_history = load_json(os.path.join(output_dir, "training_history.json"))
    walk_forward = load_json(os.path.join(output_dir, "walk_forward_results.json"))

    if kaggle_strategy is None:
        print("[ERROR] best_strategy_per_regime.json not found — kernel may not be complete")
        sys.exit(1)

    print(f"[OK] best_strategy_per_regime.json: {len(kaggle_strategy)} regimes")
    if training_history:
        print(f"[OK] training_history.json: {len(training_history)} regimes")
    else:
        print("[WARN] training_history.json not found")
    if walk_forward:
        print(f"[OK] walk_forward_results.json: {len(walk_forward)} regimes")
    else:
        print("[INFO] walk_forward_results.json not found (optional)")

    local_strategy = convert_to_local_strategy(kaggle_strategy)
    print(f"\n[OK] Converted: {len(local_strategy['regimes'])} regimes")
    for regime_name, regime_data in local_strategy["regimes"].items():
        print(f"  {regime_name}: {regime_data['formula_str']} (IC={regime_data['ic']:.4f})")

    issues = validate_integration(local_strategy)
    if issues:
        print(f"\n[WARN] Validation issues ({len(issues)}):")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print(f"\n[OK] Validation passed")

    strategy_path = os.path.join(SCRIPTS_DIR, "best_strategy.json")
    report_path = os.path.join(SCRIPTS_DIR, "training_report.json")

    if os.path.exists(strategy_path):
        backup_path = strategy_path + f".bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
        shutil.copy2(strategy_path, backup_path)
        print(f"[OK] Backup: {backup_path}")

    save_json(local_strategy, strategy_path)
    print(f"[OK] Saved: {strategy_path}")

    report = generate_training_report(kaggle_strategy, training_history)
    save_json(report, report_path)
    print(f"[OK] Report: {report_path}")

    refs_dir = os.path.join(SKILL_DIR, "references")
    os.makedirs(refs_dir, exist_ok=True)
    for fname in OUTPUT_FILES:
        src = os.path.join(output_dir, fname)
        if os.path.exists(src):
            dst = os.path.join(refs_dir, f"v54-{fname}")
            shutil.copy2(src, dst)
            print(f"[OK] Archived: {dst}")

    print(f"\n=== Integration Complete ===")


if __name__ == "__main__":
    main()
