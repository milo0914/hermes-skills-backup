# Kaggle Kernel Cron 監控模式

## 背景
長時間 GPU 訓練（10-30 分鐘）需要自動化監控，避免人工輪詢。Hermes cronjob 可每 N 分鐘自動檢查 kernel 狀態並回報。

## Cronjob 設定範例

```python
# Hermes cronjob 建立
cronjob = {
    "name": "kaggle-grpo-v69-advantage-monitor",
    "skill": "kaggle-api",
    "skills": ["kaggle-api", "twstock-grpo-v6-changelog"],
    "schedule": "every 30m",  # 或 "every 5m" 更頻繁
    "repeat": "forever",
    "deliver": "local",
    "prompt": """
監控 Kaggle 上 twstock-grpo-regime-aware-factor-training-v6-9 notebook 的訓練輸出...

任務：
1. 使用 Kaggle API 獲取 kernel 的最新執行狀態和輸出日誌
2. 分析輸出中是否有 advantage collapse 跡象：
   - "Adv near-zero" 或 "advantage std" 接近 0
   - "Z-score" 相關警告
   - reward 方差極小 (std < 0.01)
   - 所有 rewards 接近相同值
3. 檢查 regime 訓練是否正常（所有 4 個 regime 都有訓練，不只是 MID_CAP_TECH）
4. 檢查 Multi-Objective Reward 是否正常運作
5. 若發現問題，輸出具體的修改建議參數
6. 將分析結果和建議儲存到本地檔案
    """
}
```

## Python 監控腳本範例

```python
#!/usr/bin/env python3
"""
Kaggle Kernel 自動監控腳本
用於 cronjob 定時執行
"""
import os
import json
import subprocess
from datetime import datetime

KERNEL_SLUG = "mhhuang14/twstock-grpo-regime-aware-factor-training-v6-9"
OUTPUT_DIR = "/tmp/kaggle_monitor_output"
LOG_FILE = f"{OUTPUT_DIR}/monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

os.makedirs(OUTPUT_DIR, exist_ok=True)

def run_kaggle_cmd(cmd):
    """執行 kaggle CLI 命令，返回 (success, output)"""
    env = os.environ.copy()
    env["KAGGLE_API_TOKEN"] = os.getenv("KAGGLE_API_TOKEN", "")
    try:
        result = subprocess.run(
            ["python3", "-m", "kaggle"] + cmd,
            capture_output=True, text=True, env=env, timeout=60
        )
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)

def check_kernel_status():
    """檢查 kernel 狀態"""
    # 1. 檢查 status
    success, output = run_kaggle_cmd(["kernels", "status", KERNEL_SLUG])
    
    # 2. 下載 output
    success, output = run_kaggle_cmd(["kernels", "output", KERNEL_SLUG, "-p", OUTPUT_DIR])
    
    # 3. 解析 log
    if success:
        log_files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.log')]
        if log_files:
            log_path = os.path.join(OUTPUT_DIR, log_files[0])
            with open(log_path) as f:
                log_content = f.read()
            return parse_log_for_issues(log_content)
    
    return {"status": "unknown", "issues": [], "recommendations": []}

def parse_log_for_issues(log_content):
    """解析 log 檢測 advantage collapse 等問題"""
    issues = []
    recommendations = []
    
    # 檢測 advantage collapse
    if "Adv near-zero" in log_content or "adv_std" in log_content:
        import re
        adv_std_matches = re.findall(r'adv_std=([\d.e+-]+)', log_content)
        if adv_std_matches:
            latest = float(adv_std_matches[-1])
            if latest < 0.01:
                issues.append(f"Advantage collapse detected: adv_std={latest}")
                recommendations.append("Increase group_size or switch to rank-based advantage")
    
    # 檢測 regime 覆蓋率
    regime_trained = []
    for regime in ["LARGE_CAP", "MID_CAP_TECH", "TRADITIONAL", "FINANCIAL"]:
        if f"regime={regime}" in log_content:
            regime_trained.append(regime)
    if len(regime_trained) < 4:
        issues.append(f"Only {len(regime_trained)}/4 regimes trained: {regime_trained}")
        recommendations.append("Check auto_detect() CPU mode regime filtering logic")
    
    # 檢測 Multi-Objective Reward
    if "Multi-Objective Reward" not in log_content and "sharpe" not in log_content.lower():
        issues.append("Multi-Objective Reward may not be active")
        recommendations.append("Verify use_multi_objective=True and reward_weights config")
    
    return {
        "timestamp": datetime.now().isoformat(),
        "status": "completed" if not issues else "issues_detected",
        "issues": issues,
        "recommendations": recommendations,
        "regimes_trained": regime_trained
    }

if __name__ == "__main__":
    result = check_kernel_status()
    with open(LOG_FILE, 'w') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(json.dumps(result, indent=2, ensure_ascii=False))
```

## 關鍵監控指標

| 指標 | 正常範圍 | 異常判定 | 建議動作 |
|------|----------|----------|----------|
| `adv_std` | > 0.1 | < 0.01 | 增加 group_size、改用 rank-based |
| `valid_mask` 比例 | > 80% | < 50% | 檢查 StackVM guided decoding |
| Regime 覆蓋率 | 4/4 | < 4/4 | 修正 CPU mode 過濾邏輯 |
| `reward_std` | > 0.5 | < 0.1 | 增加 reward 多樣性 |
| `loss` 變化 | 有波動 | 恆為 0 | 檢查 PPO ratio 計算 |

## 觸發修改流程

1. Cronjob 檢測到問題 → 寫入 `monitor_issues_<timestamp>.json`
2. Agent 讀取檔案 → 分析具體問題
3. 修改 notebook 參數（group_size, reward_weights, train_steps 等）
4. 重新 `kaggle kernels push`
5. Cronjob 繼續監控新版本

## 參考檔案

- `/home/appuser/twstock_v69_kernel/twstock-grpo-regime-aware-factor-training-v6-9.ipynb` — 最新訓練 notebook
- `references/cron-v69-monitor.json` — 當前 cronjob 設定
- `twstock-grpo-v6-changelog` skill 中的 `references/CHANGELOG_v6.9.md` — v6.9 修復詳情