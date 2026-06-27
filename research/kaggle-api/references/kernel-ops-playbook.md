# Kaggle Kernel 操作實戰手冊

版本：v1.0（2026-06-08）

本文件記載 Kaggle API/CLI 的完整實戰操作模式，涵蓋推送、監控、停止、輸出等日常運維場景。

---

## 1. 推送 ipynb 到 Kaggle 執行

### 1.1 完整流程（端對端）

```
本地編輯 .py → 轉換 .ipynb → 準備 metadata → 驗證 → push → 監控
```

### 1.2 準備推送資料夾

推送前需準備一個資料夾，包含兩個必要檔案：

```
/tmp/kaggle-kernel/
├── kernel-metadata.json    # Kernel 配置
└── your-notebook.ipynb     # 筆記本檔案
```

### 1.3 kernel-metadata.json 完整範例

```json
{
  "id": "username/kernel-slug",
  "id_no": 123456,
  "title": "Kernel Display Title",
  "code_file": "your-notebook.ipynb",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": "true",
  "enable_gpu": "true",
  "enable_tpu": "false",
  "enable_internet": "true",
  "keywords": ["grpo", "reinforcement-learning"],
  "dataset_sources": ["username/dataset-slug"],
  "kernel_sources": [],
  "competition_sources": [],
  "model_sources": [],
  "machine_shape": "NvidiaTeslaT4"
}
```

**⚠️ 實測有效的 metadata 格式（v6.18 風格，2026-06-18 驗證，v6.19 確認）：**
```json
{
  "id": "mhhuang14/twstock-grpo-v6-19-composite-score-full-fix",
  "title": "TWStock GRPO v6 19 Composite Score Full Fix",
  "code_file": "twstock-grpo-v6-19.ipynb",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": "true",
  "enable_gpu": "true",
  "enable_internet": "true",
  "dataset_sources": ["mhhuang14/twstock-v6-0-real-data-20stocks-5y"],
  "machine_shape": "Gpu",
  "docker_image": "gcr.io/kaggle-private-byod/python@sha256:57e612b484cf3df5026ee4dcc3cb176974b22b2bc0937fb1e16132a8be4cb13c",
  "enable_tpu": "false",
  "keywords": ["gpu"]
}
```

**關鍵差異（v6.19 失敗 vs v6.18 成功）：**
- ❌ 失敗：`"accelerator": "GPU_T4"`, `"machine_shape": "NvidiaTeslaT4"`, `"is_idle_no_idle": true`
- ✅ 成功：`"machine_shape": "Gpu"`, `"docker_image": "..."`（具體 sha256），**無** `accelerator`、**無** `is_idle_no_idle`
- `is_private`、`enable_gpu`、`enable_internet`、`enable_tpu` 建議用字串 `"true"`/`"false"` 而非布林值
- `docker_image` 指定具體基礎映像可提高穩定性（從 `kernels pull -m` 取得的 metadata 可獲取當前環境的 docker_image）

關鍵欄位說明：
- `id`: `username/slug` 格式，slug 由 title 自動推導（小寫+連字符）
- `id_no`: 數字 ID，首次推送可省略，push 成功後 CLI 會回傳
- `code_file`: **必須**與資料夾中的實際檔名一致
- `kernel_type`: `notebook`（.ipynb）或 `script`（.py），不可混用
- `is_private` / `enable_gpu`: 建議用字串 `"true"` 而非布林值
- `machine_shape`: `NvidiaTeslaT4`、`NvidiaTeslaP100`、`NvidiaTeslaV100` 等
- `dataset_sources`: 附加的 Kaggle dataset（`owner/slug` 格式），執行時自動掛載到 `/kaggle/input/`

### 1.4 .py → .ipynb 轉換

```python
import json, uuid

def py_to_ipynb(py_path, ipynb_path, cell_breaks=None):
    """將 .py 檔案轉換為 Kaggle 相容的 .ipynb

    Args:
        py_path: 來源 .py 檔案路徑
        ipynb_path: 輸出 .ipynb 路徑
        cell_breaks: 可選，每個 cell 的起始行號 list（0-indexed）
                     若不提供，自動掃描 '# ====...# N.' section headers
    """
    with open(py_path) as f:
        py_lines = f.read().split('\n')

    # 自動掃描 section headers 作為 cell 切割點
    if cell_breaks is None:
        cell_breaks = [0]
        for i, line in enumerate(py_lines):
            if line.startswith('# ====') and i + 1 < len(py_lines) \
               and py_lines[i+1].strip().startswith('# ') \
               and not py_lines[i+1].strip().startswith('# ==='):
                cell_breaks.append(i)

    cells = []
    for idx, start in enumerate(cell_breaks):
        end = cell_breaks[idx + 1] if idx + 1 < len(cell_breaks) else len(py_lines)
        lines = py_lines[start:end]
        # 移除尾部空行
        while lines and not lines[-1].strip():
            lines.pop()
        source = [l + "\n" for l in lines[:-1]] + ([lines[-1]] if lines else [])

        # 驗證每個 cell 可獨立編譯
        src = ''.join(source)
        try:
            compile(src, f'<cell{idx}>', 'exec')
        except SyntaxError as e:
            print(f"Cell {idx} SYNTAX ERROR: line {e.lineno}: {e.msg}")
            raise

        cells.append({
            "cell_type": "code",
            "metadata": {},
            "source": source,
            "execution_count": None,
            "outputs": [],
            "id": str(uuid.uuid4())[:8]
        })

    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3"
            },
            "language_info": {
                "name": "python",
                "version": "3.12.0"
            }
        },
        "cells": cells
    }

    with open(ipynb_path, 'w') as f:
        json.dump(nb, f, indent=1)

    print(f"Notebook: {len(cells)} cells, {sum(len(c['source']) for c in cells)} lines")
    return nb

# 使用範例
py_to_ipynb("/path/to/source.py", "/tmp/kaggle-kernel/notebook.ipynb")
```

注意事項：
- 每個 cell 必須有 `id` 欄位（uuid），否則 Kaggle 會拋 MissingIDFieldWarning
- cell 不可切斷 class/function 定義中間，否則執行時 IndentationError
- 用 `compile()` 驗證每個 cell 的語法
- source 必須是 list of strings（每行一個元素），最後一行不加 `\n`

### 1.5 推送指令

```bash
# 基本 push
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels push -p /tmp/kaggle-kernel/

# 指定加速器（覆蓋 metadata 中的設定）
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels push -p /tmp/kaggle-kernel/ --accelerator GPU_T4

# 設定超時（預設 1200 秒 = 20 分鐘，最大 36000 秒 = 10 小時）
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels push -p /tmp/kaggle-kernel/ -t 7200
```

成功回應：
```
Kernel version 5 successfully pushed
```

### 1.6 常見推送錯誤

| 錯誤 | 原因 | 解法 |
|------|------|------|
| `409 Conflict` | 同 slug 前一版仍在執行 | 等 kernel 完成 or Web UI 取消後再 push |
| `404 Not Found` | slug 不存在且 title 無法推導為該 slug | 修改 title 或 id 欄位 |
| `400 Bad Request` | metadata 格式錯誤 | 檢查 JSON 格式、code_file 是否存在 |
| `Warning: title does not resolve to id` | title 與 slug 不匹配 | 不影響推送，但建議統一 |

### 1.7 Script 模式（kernel_type=script）— 更簡單的替代方案

若不願處理 .py→.ipynb 轉換和 cell 切割，可用 script 模式直接推送 .py 檔案：

```json
{
  "id": "username/kernel-slug",
  "title": "Kernel Display Title",
  "code_file": "training_script.py",
  "language": "python",
  "kernel_type": "script",
  "is_private": "true",
  "enable_gpu": "true",
  "enable_internet": "true",
  "machine_shape": "NvidiaTeslaT4"
}
```

```bash
# 直接複製 .py 到 kernel 資料夾
cp /path/to/training_script.py /tmp/kaggle-kernel/
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels push -p /tmp/kaggle-kernel/
```

優點：
- 無需 cell 切割、compile 驗證、notebook JSON 構建
- 修改 .py 後直接重新推送，迭代更快
- py_compile 驗證即可，不需額外轉換步驟

缺點：
- Kaggle 用 papermill 逐行執行整個 script，出錯時只看到最終 traceback（notebook 模式可看到哪個 cell 失敗）
- Kaggle Web UI 中不會顯示 cell 分段，整個 script 是一個大 code block

建議：對已通過 py_compile 驗證的大型訓練腳本，script 模式更高效；對需要逐段觀察輸出的實驗，notebook 模式更可控。

---

## 2. 查看 Kernel List

### 2.1 CLI 查詢

```bash
# 列出自己的所有 kernel
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels list -m

# 指定每頁數量
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels list -m --page-size 20

# 排序方式
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels list -m --sort-by dateRun

# 搜尋特定用戶的 kernel
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels list --user MHHUANG14

# 篩選語言和類型
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels list -m --language python --kernel-type notebook
```

### 2.2 Python API 查詢

```python
import os
os.environ['KAGGLE_API_TOKEN'] = 'KGAT_xxx'

from kaggle.api.kaggle_api_extended import KaggleApi
api = KaggleApi()
api.authenticate()

# 列出自己的 kernel
kernels = api.kernels_list(mine=True, page_size=20)
for k in kernels:
    print(f"{k.ref} | {k.title} | lastRun={k.lastRunTime} | status={k.status}")

# 查詢特定用戶
kernels = api.kernels_list(user='MHHUANG14', page_size=10)
```

注意：
- Python API 的 `kernels_list(search=..., mine=True)` 可能返回 401（gRPC 認證問題）
- CLI `kaggle kernels list -m` 最穩定
- `--page-size` 替代已移除的 `--max`

### 2.3 輸出欄位說明

CLI 輸出格式：
```
ref                                                         title                    lastRunTime    totalVotes
mhhuang14/grpo-regime-aware-factor-training                GRPO Regime-Aware...     2026-06-08     0
```

Python API 物件屬性：
- `k.ref`: `owner/slug` 格式的唯一標識
- `k.title`: 顯示標題
- `k.lastRunTime`: 最近執行時間（ISO 格式）
- `k.status`: 執行狀態
- `k.totalVotes`: 投票數

---

## 3. 即時監控 Kernel 執行進程

### 3.1 方法一：kernels output（推薦，最穩定）

```bash
# 下載 output 到指定路徑（含 .log 檔案）
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels output mhhuang14/grpo-regime-aware-factor-training -p /tmp/kout/
```

行為：
- Kernel 仍在執行 → **CLI 會阻塞/卡住**，不回傳 "still running"，也不寫入檔案，直到 kernel 完成或超時（v6.19 實測確認）。Python API `api.kernels_output()` 行為相同。
- Kernel 已完成 → 下載 `.log` + output 檔案到 `-p` 路徑
- Kernel 失敗 → 下載 `.log`（含 stderr traceback）

**非阻塞監控替代方案：**
```bash
# 方法 A：觀察 lastRunTime 更新（間接確認已完成）
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels list -m --sort-by dateRun --page-size 5

# 方法 B：kernels pull -m 確認版本號增加（間接確認已有新版本）
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels pull OWNER/SLUG -p /tmp/check/ -m

# 方法 C：kernels status（偶爾成功，但常回 500）
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels status OWNER/SLUG
```

### 3.2 方法二：kernels status（不穩定，常回 500）

```bash
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels status mhhuang14/grpo-regime-aware-factor-training
```

可能回應：
- `Status: running` / `Status: complete` / `Status: error`
- `500 Server Error`（Kaggle gRPC 端點間歇性故障，不代表 kernel 有問題）

### 3.3 方法三：自動化輪詢監控腳本

```bash
#!/bin/bash
# 監控 Kaggle kernel 執行狀態，每 60 秒檢查一次
OWNER_SLUG="mhhuang14/grpo-regime-aware-factor-training"
OUT_DIR="/tmp/kout"
TOKEN="KGAT_xxx"

rm -rf "$OUT_DIR"; mkdir -p "$OUT_DIR"

echo "開始監控 $OWNER_SLUG ..."
while true; do
    RESULT=$(KAGGLE_API_TOKEN="$TOKEN" kaggle kernels output "$OWNER_SLUG" -p "$OUT_DIR" 2>&1)

    if echo "$RESULT" | grep -q "still running"; then
        echo "[$(date +%H:%M:%S)] Kernel 仍在執行中..."
        rm -rf "$OUT_DIR"; mkdir -p "$OUT_DIR"
        sleep 60
    elif ls "$OUT_DIR"/*.log 2>/dev/null; then
        echo "[$(date +%H:%M:%S)] Kernel 已完成！Log 已下載到 $OUT_DIR"
        break
    else
        echo "[$(date +%H:%M:%S)] 未預期回應: $RESULT"
        sleep 60
    fi
done
```

### 3.4 方法四：Python 自動化監控

```python
import os, time, json, subprocess

os.environ['KAGGLE_API_TOKEN'] = 'KGAT_xxx'

def monitor_kernel(owner_slug, out_dir='/tmp/kout', poll_interval=60):
    """監控 Kaggle kernel 執行，完成後回傳 log 路徑"""
    os.makedirs(out_dir, exist_ok=True)

    while True:
        # 清空舊 output
        for f in os.listdir(out_dir):
            os.remove(os.path.join(out_dir, f))

        result = subprocess.run(
            ['kaggle', 'kernels', 'output', owner_slug, '-p', out_dir],
            capture_output=True, text=True
        )

        if 'still running' in result.stdout.lower():
            print(f"[{time.strftime('%H:%M:%S')}] 仍在執行...")
            time.sleep(poll_interval)
        elif os.listdir(out_dir):
            print(f"[{time.strftime('%H:%M:%S')}] 完成！Output 在 {out_dir}")
            return out_dir
        else:
            print(f"未預期回應: {result.stdout} {result.stderr}")
            time.sleep(poll_interval)

# 使用
log_dir = monitor_kernel('mhhuang14/grpo-regime-aware-factor-training')
```

---

## 4. 停止 Runtime

### 4.1 重要：CLI 無 stop 命令

Kaggle CLI 2.2.1 **不支援** `kaggle kernels stop`。也沒有 `kaggle kernels cancel` 或類似命令。

### 4.2 替代方案

#### 方案 A：Kaggle Web UI 手動取消（最可靠）

1. 前往 https://www.kaggle.com/code
2. 左側欄 → Your Work
3. 找到目標 kernel → 點擊進入
4. 若正在執行，右上角會出現 "Cancel Run" 按鈕
5. 點擊取消，等待狀態變為 "Cancelled"（通常 10-30 秒）

#### 方案 B：等待自然結束

- Kernel 最長執行時間受限於超時設定（預設 1200 秒，最大 36000 秒）
- 若 OOM 或 runtime error，kernel 會自動終止
- 用 `kernels output` 監控確認完成

#### 方案 C：改 slug 推送新版本（不推薦）

修改 `kernel-metadata.json` 中的 `id` 和 `title`，用新 slug 推送：
- 缺點：舊 slug 的 output 仍殘留在帳號
- 缺點：後續引用會不一致
- 僅在緊急情況使用

### 4.3 確認 Runtime 已停止

```bash
# 方法 1：kernels output
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels output OWNER/SLUG -p /tmp/kout/
# 如果下載到 .log 檔案 → kernel 已停止（完成或失敗）

# 方法 2：kernels list（間接推斷）
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels list -m
# lastRunTime 已更新 → kernel 已完成一次執行

# 方法 3：Web UI
# 前往 https://www.kaggle.com/code/OWNER/SLUG 查看狀態
```

---

## 5. 輸出與解析 Logs

### 5.1 下載 Output

```bash
# 下載到指定路徑
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels output OWNER/SLUG -p /tmp/kout/

# 下載後的檔案結構
/tmp/kout/
├── kernel-slug.log              # 執行 log（JSON 格式）
├── best_strategy_per_regime.json # Notebook 產生的 output 檔案
├── training_history.json         # Notebook 產出的 output
└── __results__.html              # HTML 格式的執行結果
```

### 5.2 Log 檔案格式

`.log` 檔案每行是一個 JSON 物件，格式如下：

```json
{"stream_name": "stdout", "time": 15.12, "data": " GPU: Tesla T4 (15.6 GB), CUDA capability sm_75\n"}
{"stream_name": "stdout", "time": 15.42, "data": " 特徵計算完成: 2000 筆\n"}
{"stream_name": "stderr", "time": 23.81, "data": "Traceback (most recent call last):\n"}
{"stream_name": "stderr", "time": 23.81, "data": "  File \"/kaggle/src/script.py\", line 1906, in <module>\n"}
```

欄位說明：
- `stream_name`: `"stdout"` 或 `"stderr"`
- `time`: 從 kernel 啟動開始的秒數（浮點數）
- `data`: 該時間點的輸出文字（含 `\n` 結尾）

### 5.3 解析完整 stdout

```python
import json

def parse_stdout(log_path):
    """解析 Kaggle kernel log，回傳所有 stdout 輸出"""
    output_lines = []
    with open(log_path) as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("stream_name") == "stdout":
                output_lines.append(entry["data"])
    return "".join(output_lines)

stdout = parse_stdout("/tmp/kout/kernel-slug.log")
print(stdout)
```

### 5.4 解析 Error Traceback

```python
import json

def parse_stderr(log_path):
    """解析 Kaggle kernel log，回傳所有 stderr（含 traceback）"""
    error_lines = []
    with open(log_path) as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("stream_name") == "stderr":
                error_lines.append(entry["data"])
    return "".join(error_lines)

stderr = parse_stderr("/tmp/kout/kernel-slug.log")
if stderr:
    print("=== ERROR ===")
    print(stderr)
```

### 5.5 提取特定時間段的輸出

```python
import json

def parse_time_range(log_path, start_sec=0, end_sec=float('inf')):
    """提取特定時間段的 log 輸出"""
    results = {"stdout": [], "stderr": []}
    with open(log_path) as f:
        for line in f:
            entry = json.loads(line)
            t = entry.get("time", 0)
            if start_sec <= t <= end_sec:
                stream = entry.get("stream_name", "stdout")
                results[stream].append(entry["data"])
    return {k: "".join(v) for k, v in results.items()}

# 範例：只看前 60 秒的輸出
early = parse_time_range("/tmp/kout/kernel-slug.log", 0, 60)
print(early["stdout"])
```

### 5.6 一鍵 Debug 腳本

```python
#!/usr/bin/env python3
"""Kaggle kernel debug 工具 — 下載 log → 解析錯誤 → 定位行號"""
import os, sys, json, subprocess

os.environ['KAGGLE_API_TOKEN'] = 'KGAT_xxx'

def debug_kernel(owner_slug, out_dir='/tmp/kdebug'):
    # 1. 下載 output
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        os.remove(os.path.join(out_dir, f))

    result = subprocess.run(
        ['kaggle', 'kernels', 'output', owner_slug, '-p', out_dir],
        capture_output=True, text=True
    )

    if 'still running' in result.stdout.lower():
        print("Kernel 仍在執行中，尚無 log 可用")
        return None

    # 2. 找到 log 檔案
    log_files = [f for f in os.listdir(out_dir) if f.endswith('.log')]
    if not log_files:
        print(f"未找到 .log 檔案。目錄內容: {os.listdir(out_dir)}")
        return None

    log_path = os.path.join(out_dir, log_files[0])
    print(f"Log 檔案: {log_path}")

    # 3. 解析 stderr（traceback）
    errors = []
    stdout_lines = []
    with open(log_path) as f:
        for line in f:
            entry = json.loads(line)
            stream = entry.get("stream_name", "")
            if stream == "stderr":
                errors.append(entry["data"])
            elif stream == "stdout":
                stdout_lines.append(entry["data"])

    # 4. 輸出結果
    print(f"\n=== STDOUT ({len(stdout_lines)} lines) ===")
    print("".join(stdout_lines[-50:]))  # 最後 50 行

    if errors:
        print(f"\n=== STDERR ({len(errors)} lines) ===")
        print("".join(errors))

        # 5. 嘗試提取錯誤行號
        for err in errors:
            if 'File' in err and 'line' in err:
                print(f"\n>>> 錯誤位置: {err.strip()}")
    else:
        print("\n=== 無 stderr，kernel 可能成功完成 ===")

    # 5. 列出 output 檔案
    output_files = [f for f in os.listdir(out_dir) if not f.endswith('.log')]
    if output_files:
        print(f"\n=== Output 檔案 ===")
        for f in output_files:
            size = os.path.getsize(os.path.join(out_dir, f))
            print(f"  {f} ({size:,} bytes)")

    return log_path

# 使用
debug_kernel('mhhuang14/grpo-regime-aware-factor-training')
```

---

## 6. Dataset 上傳與附加到 Kernel

### 6.1 上傳 Dataset

```bash
# 準備資料夾
mkdir -p /tmp/kaggle-dataset
cd /tmp/kaggle-dataset

# 建立 metadata
cat > dataset-metadata.json << 'EOF'
{
  "title": "TWStock GRPO Training Data",
  "id": "mhhuang14/twstock-grpo-training-data",
  "licenses": [{"name": "CC0-1.0"}]
}
EOF

# 放入資料檔案
cp /path/to/training_data.csv .

# 建立新 dataset
KAGGLE_API_TOKEN="KGAT_xxx" kaggle datasets create -p /tmp/kaggle-dataset/

# 更新既有 dataset 的新版本
KAGGLE_API_TOKEN="KGAT_xxx" kaggle datasets version -p /tmp/kaggle-dataset/ -m "v2: add futures OI data"
```

### 6.2 在 Kernel 中使用 Dataset

```json
// kernel-metadata.json 中指定 dataset_sources
{
  "dataset_sources": ["mhhuang14/twstock-grpo-training-data"],
  ...
}
```

在 Notebook 中存取（**重要：掛載路徑是三層巢狀，需用 os.walk 遞迴搜尋**）：
```python
import pandas as pd
import os

# ❌ 錯誤假設：路徑為 /kaggle/input/DATASET-SLUG/file.csv
# df = pd.read_csv('/kaggle/input/twstock-grpo-training-data/training_data.csv')

# ✅ 正確做法：用 os.walk 遞迴搜尋（實際路徑為 /kaggle/input/datasets/OWNER/SUG/file.csv）
def find_csv(filename, base='/kaggle/input/'):
    for root, dirs, files in os.walk(base):
        if filename in files:
            return os.path.join(root, filename)
    return None

csv_path = find_csv('training_data.csv')
if csv_path:
    df = pd.read_csv(csv_path)
    print(f"從 Kaggle Dataset 載入: {csv_path}")
else:
    print("未找到真實數據，fallback 到合成數據")
    # ... synthetic fallback ...
```

**注意**：`dataset_sources` 中的 dataset 掛載到 `/kaggle/input/datasets/{owner}/{slug}/{files}`（三層），不是 `/kaggle/input/{slug}/{files}`（一層）。用 `os.listdir('/kaggle/input/')` 只看到 `datasets/` 目錄名，需再往下兩層才到達 CSV 檔案。

---

## 7. 常見工作流範例

### 7.1 完整 Push → Monitor → Debug → Re-push 循環

```python
import os, json, time, subprocess, uuid

os.environ['KAGGLE_API_TOKEN'] = 'KGAT_xxx'

OWNER = 'mhhuang14'
SLUG = 'grpo-regime-aware-factor-training'
OWNER_SLUG = f'{OWNER}/{SLUG}'

def push_and_monitor(kernel_dir, poll_interval=60, max_wait=7200):
    """推送 kernel 並監控直到完成，回傳 log 路徑"""

    # 1. Push
    print("推送 kernel...")
    result = subprocess.run(
        ['kaggle', 'kernels', 'push', '-p', kernel_dir],
        capture_output=True, text=True
    )
    if 'successfully pushed' not in result.stdout:
        if '409' in result.stderr:
            print("409 Conflict: 前一版仍在執行，請等待或到 Web UI 取消")
            return None
        print(f"Push 失敗: {result.stdout} {result.stderr}")
        return None
    print(f"Push 成功: {result.stdout.strip()}")

    # 2. Monitor
    print(f"開始監控（每 {poll_interval}s 檢查一次，最長等待 {max_wait}s）...")
    out_dir = f'/tmp/kout-{SLUG}'
    start = time.time()

    while time.time() - start < max_wait:
        os.makedirs(out_dir, exist_ok=True)
        for f in os.listdir(out_dir):
            os.remove(os.path.join(out_dir, f))

        result = subprocess.run(
            ['kaggle', 'kernels', 'output', OWNER_SLUG, '-p', out_dir],
            capture_output=True, text=True
        )

        if 'still running' in result.stdout.lower():
            elapsed = int(time.time() - start)
            print(f"  [{elapsed}s] 仍在執行...")
            time.sleep(poll_interval)
        elif os.listdir(out_dir):
            elapsed = int(time.time() - start)
            print(f"  [{elapsed}s] 完成！")
            return out_dir
        else:
            time.sleep(poll_interval)

    print("等待超時！")
    return None

# 使用
log_dir = push_and_monitor('/tmp/kaggle-kernel/')
if log_dir:
    # 自動 debug
    # ... 使用 5.6 的 debug_kernel 邏輯 ...
    pass
```

### 7.2 更新既有 Kernel（Pull → 修改 → Push）

```bash
# 1. 下載既有 kernel（含 metadata）
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels pull OWNER/SLUG -p /tmp/kpull/ -m

# 2. 修改 .ipynb（手動或程式化）
# ... 編輯 /tmp/kpull/notebook.ipynb ...

# 3. 重新 push（使用原 metadata，slug 不變）
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels push -p /tmp/kpull/
```

### 7.3 多 Kernel 並行監控

```bash
#!/bin/bash
# 同時監控多個 kernel
KERNELS=(
  "mhhuang14/grpo-regime-aware-factor-training"
  "mhhuang14/another-experiment"
)

TOKEN="KGAT_xxx"

while true; do
    ALL_DONE=true
    for K in "${KERNELS[@]}"; do
        OUT="/tmp/kout-$(basename $K)"
        mkdir -p "$OUT"
        RESULT=$(KAGGLE_API_TOKEN="$TOKEN" kaggle kernels output "$K" -p "$OUT" 2>&1)
        if echo "$RESULT" | grep -q "still running"; then
            echo "[$(date +%H:%M:%S)] $K: 執行中"
            ALL_DONE=false
            rm -rf "$OUT"; mkdir -p "$OUT"
        else
            echo "[$(date +%H:%M:%S)] $K: 已完成"
        fi
    done
    [ "$ALL_DONE" = true ] && break
    sleep 60
done
echo "所有 kernel 已完成！"
```
