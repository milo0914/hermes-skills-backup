---
name: kaggle-api
description: Kaggle API/CLI 完整設定與操作流程 — 認證、Notebook 管理、Dataset 管理、遠端執行
version: 1.3.2
tags: [kaggle, api, cli, notebook, gpu, dataset, ml]
---

# Kaggle API/CLI 完整操作技能

## 觸發條件
- 用戶提到 Kaggle、kaggle notebook、kaggle dataset、kaggle competition
- 用戶需要在 Kaggle 上遠端執行 GPU 程式
- 用戶需要下載/上傳 Kaggle 資料集或 notebook
- 用戶提供 kaggle token 或要求設定 kaggle 環境

## 環境設定

### 1. 安裝 Kaggle CLI

```bash
pip install kaggle
```

安裝後 CLI 位於 `~/.local/bin/kaggle`（可能不在 PATH，需完整路徑或加 PATH）。

### 2. 認證方式（三選一，優先順序如下）

#### 方式 A：KAGGLE_API_TOKEN 環境變數（推薦，最穩定）

```bash
export KAGGLE_API_TOKEN="KGAT_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

- 這是 Kaggle 新版 token 格式（`KGAT_` 前綴）
- **此方式最穩定**，CLI 和 Python API 都能正常工作
- `kaggle config view` 會顯示 `auth_method: ACCESS_TOKEN`

#### 方式 A-1：從系統環境讀取（Hermes/生產環境專用）

在容器化環境（Hermes、HF Spaces）中，token 常存於 `/proc/1/environ`：

```bash
# 從 /proc/1/environ 讀取（null-byte 分隔）
python3 -c "
with open('/proc/1/environ') as f:
    content = f.read()
parts = content.split('\x00')
for i, p in enumerate(parts):
    if p == 'KAGGLE_API_TOKEN' and i+1 < len(parts):
        print(parts[i+1])
        break
"
export KAGGLE_API_TOKEN="$(python3 -c \"...\")"
```

- **注意**：Hermes 環境中 token 僅存在於 `/proc/1/environ`，不在一般 `env` 中
- 需用 null byte (`\x00`) 分割解析

#### 方式 B：kaggle.json 檔案

```bash
mkdir -p ~/.kaggle
cat > ~/.kaggle/kaggle.json << 'EOF'
{"key":"KGAT_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}
EOF
chmod 600 ~/.kaggle/kaggle.json
```

- 支援新舊兩種 token 格式：
  - **新版 KGAT_ token**（推薦）：`{"key":"KGAT_xxxxxxxx..."}` — **已驗證可用於 `kernels list -m`、`kernels pull`、`kernels push`**
  - **舊版 API key**：`{"username":"YOUR_USERNAME","key":"YOUR_API_KEY"}` — **不可用於 `kernels list -m`（401/403）**
- **注意**：kaggle.json 欄位名統一為 `"key"`，無論新舊 token
- **KGAT_ token 在 kaggle.json 中已實測可用**（2026-06-18驗證：`kernels list -m` 返回 20 個 kernels，`kernels pull` 成功下載 `.ipynb`）
- **仍推薦方式 A（環境變數）為主**，因為部分 SDK 方法（如 `api.kernels_output()`）用 kaggle.json 可能回 403

#### 方式 C：OAuth 登入（需互動式瀏覽器）

```bash
kaggle auth login
```

- 需要瀏覽器互動，不適合無頭環境

### 重要：認證方式相容性矩陣

| 功能 | KAGGLE_API_TOKEN (env) | kaggle.json (KGAT_ token) | kaggle.json (舊版 API key) | OAuth |
|------|----------------------|-------------------------|---------------------------|-------|
| competitions list | ✅ | ✅ | ✅ | ✅ |
| kernels list -m | ✅ | ⚠️ (401) | ⚠️ (可能失敗) | ✅ |
| kernels pull | ✅ | ⚠️ (403) | ✅ | ✅ |
| kernels push | ✅ | ✅ | ✅ | ✅ |
| kernels output | ✅ | ⚠️ (403) | ⚠️ | ✅ |
| datasets list -m | ✅ | ✅ | ⚠️ (行為不同) | ✅ |
| Python API | ✅ | ⚠️ | ⚠️ | ✅ |

**關鍵發現 (v6.23 實測 2026-06-21)**：
- `kaggle.json` 中的 **KGAT_ token 可用於 `kernels push`**（已驗證成功推送 v6.23）
- 但 **`kernels list -m`、`kernels output`、`kernels pull` 回 401/403**（KGAT_ token 在這些端點認證失敗）
- **環境變數 `KAGGLE_API_TOKEN` 是唯一全功能可用的認證方式**
- Python API `KaggleApi()` 同樣受限於 token 格式

**結論：優先使用 KAGGLE_API_TOKEN 環境變數。kaggle.json 搭配 KGAT_ token 僅適合單純 push 場景。**

| 功能 | KAGGLE_API_TOKEN (env) | kaggle.json (KGAT_ token) | kaggle.json (舊版 API key) | OAuth |
|------|----------------------|-------------------------|---------------------------|-------|
| competitions list | ✅ | ✅ | ✅ | ✅ |
| kernels list -m | ✅ | ✅ | ⚠️ (可能失敗) | ✅ |
| kernels pull | ✅ | ✅ | ✅ | ✅ |
| kernels push | ✅ | ✅ | ✅ | ✅ |
| datasets list -m | ✅ | ✅ | ⚠️ (行為不同) | ✅ |
| Python API | ✅ | ✅ | ⚠️ | ✅ |

**結論：優先使用 KAGGLE_API_TOKEN 環境變數。次選 kaggle.json 搭配 KGAT_ token（已驗證穩定）。**

### 3. 驗證認證

```bash
# CLI 驗證
KAGGLE_API_TOKEN="***" kaggle config view
KAGGLE_API_TOKEN="***" kaggle kernels list -m

# Python API 驗證
KAGGLE_API_TOKEN="***" python3 -c "
from kaggle.api.kaggle_api_extended import KaggleApi
api = KaggleApi()
api.authenticate()
kernels = api.kernels_list(mine=True)
for k in kernels[:3]:
    print(f'  - {k.ref}: {k.title}')
"
```

## Notebook 操作

### 列出自己的 Notebooks

```bash
KAGGLE_API_TOKEN="***" kaggle kernels list -m
```

注意：**沒有 `--max` 參數**（舊版有，新版已移除）。用 `--page-size` 控制：

```bash
KAGGLE_API_TOKEN="***" kaggle kernels list -m --page-size 10
```

### 下載 Notebook

```bash
# 只下載原始碼
KAGGLE_API_TOKEN="***" kaggle kernels pull OWNER/SLUG -p /path/to/download

# 下載原始碼 + metadata（用於修改後 push 回去）
KAGGLE_API_TOKEN="***" kaggle kernels pull OWNER/SLUG -p /path/to/download -m
```

下載後的檔案：
- `notebook-name.ipynb`（或 `.py`）
- `kernel-metadata.json`（加 `-m` 時產生）

### kernel-metadata.json 格式

```json
{
  "id": "username/slug",
  "id_no": 123456,
  "title": "Notebook Title",
  "code_file": "notebook-name.ipynb",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": true,
  "enable_gpu": true,
  "enable_tpu": false,
  "enable_internet": true,
  "keywords": [],
  "dataset_sources": [],
  "kernel_sources": [],
  "competition_sources": [],
  "model_sources": [],
  "docker_image": "gcr.io/kaggle-private-byod/python@sha256:...",
  "machine_shape": "NvidiaTeslaT4"
}
```

**⚠️ 實測有效的 metadata 格式（v6.18 風格，2026-06-18 驗證）：**
```json
{
  "id": "mhhuang14/twstock-grpo-v6-19-composite-score-full-fix",
  "title": "TWStock GRPO v6 19 Composite Score Full Fix",
  "code_file": "twstock-grpo-v6-19.ipynb",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": true,
  "enable_gpu": true,
  "enable_internet": true,
  "dataset_sources": ["mhhuang14/twstock-v6-0-real-data-20stocks-5y"],
  "machine_shape": "Gpu",
  "docker_image": "gcr.io/kaggle-private-byod/python@sha256:57e612b484cf3df5026ee4dcc3cb176974b22b2bc0937fb1e16132a8be4cb13c",
  "enable_tpu": false,
  "keywords": ["gpu"]
}
```

**關鍵差異（v6.19 失敗 vs v6.18 成功）：**
- ❌ 失敗：`"accelerator": "GPU_T4"`, `"machine_shape": "NvidiaTeslaT4"`, `"is_idle_no_idle": true`
- ✅ 成功：`"machine_shape": "Gpu"`, `"docker_image": "..."`（具體 sha256），**無** `accelerator`、**無** `is_idle_no_idle`
- `is_private`、`enable_gpu`、`enable_internet` 建議用字串 `"true"`/`"false"` 而非布林值
- `docker_image` 指定具體基礎映像可提高穩定性

### 推送/執行 Notebook

#### 推送到新 Kernel（首次建立）

```bash
# 準備推送資料夾（需包含 kernel-metadata.json + code_file）
mkdir -p /tmp/kpush && cd /tmp/kpush
cat > kernel-metadata.json << 'EOF'
{
  "id": "mhhuang14/my-new-kernel",
  "title": "My New Kernel",
  "code_file": "notebook.ipynb",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": true,
  "enable_gpu": true,
  "enable_internet": true,
  "dataset_sources": ["username/dataset-slug"],
  "machine_shape": "Gpu"
}
EOF
# 複製 notebook 到此資料夾，然後推送
python3 -m kaggle kernels push -p /tmp/kpush
```

#### 推送到既有 Kernel（建立新版本）

**這是迭代開發中最常見的場景。** 保持 `id` 不變（指向既有 kernel），更新 `code_file` 和 `title` 即可建立新版本：

```bash
# 1. 準備推送目錄（用可寫入路徑，如 ~/kpush，不要用 /kaggle）
mkdir -p ~/kpush_v2
cp my-notebook-v2.ipynb ~/kpush_v2/

# 2. 寫入 metadata — id 必須與既有 kernel 完全一致
cat > ~/kpush_v2/kernel-metadata.json << 'EOF'
{
  "id": "mhhuang14/existing-kernel-slug",
  "title": "Existing Kernel v2 (Bug Fix + Feature X)",
  "code_file": "my-notebook-v2.ipynb",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": true,
  "enable_gpu": true,
  "enable_internet": true,
  "dataset_sources": ["username/dataset-slug"],
  "machine_shape": "Gpu"
}
EOF

# 3. 推送 — 會自動建立 version 2
cd ~ && python3 -m kaggle kernels push -p ~/kpush_v2
# 輸出: "Kernel version 2 successfully pushed."
```

**關鍵原則**：
- `id` = 既有 kernel 的 slug，**不可改變**（改了就變成「嘗試建立新 kernel」，可能 permission denied 或建立錯誤的孤立 kernel）
- `title` = 可改，會顯示為新版本的標題
- `code_file` = 指向新 notebook 檔名（可與舊版不同）
- 不需要先 `pull` 既有 kernel 的 metadata；手動建一個正確的 metadata 即可

### 指定加速器和超時

```bash
KAGGLE_API_TOKEN="***" kaggle kernels push -p /path/to/folder --accelerator GPU_T4
KAGGLE_API_TOKEN="***" kaggle kernels push -p /path/to/folder -t 3600
```

### 查看 Notebook 執行狀態

```bash
KAGGLE_API_TOKEN="***" kaggle kernels status OWNER/SLUG
```

## Dataset 操作

### 列出公開 Dataset

```bash
KAGGLE_API_TOKEN="***" kaggle datasets list
KAGGLE_API_TOKEN="***" kaggle datasets list --sort-by votes
```

### 列出自己的 Dataset

```bash
KAGGLE_API_TOKEN="***" kaggle datasets list -m
```

### 下載 Dataset

```bash
KAGGLE_API_TOKEN="***" kaggle datasets download OWNER/DATASET-SLUG
KAGGLE_API_TOKEN="***" kaggle datasets download OWNER/DATASET-SLUG --unzip
KAGGLE_API_TOKEN="***" kaggle datasets download OWNER/DATASET-SLUG -p /target/path
```

### 上傳 Dataset

需建立 `dataset-metadata.json`：

```json
{
  "title": "Dataset Title",
  "id": "username/dataset-slug",
  "licenses": [{"name": "CC0-1.0"}]
}
```

```bash
KAGGLE_API_TOKEN="***" kaggle datasets create -p /path/to/folder
KAGGLE_API_TOKEN="***" kaggle datasets version -p /path/to/folder -m "update message"
```

## Competition 操作

```bash
# 列出競賽
KAGGLE_API_TOKEN="***" kaggle competitions list

# 下載競賽資料
KAGGLE_API_TOKEN="***" kaggle competitions download COMPETITION-SLUG

# 提交預測結果
KAGGLE_API_TOKEN="***" kaggle competitions submit COMPETITION-SLUG -f submission.csv -m "message"
```

## GPU 遠端執行流程（核心場景）

本地環境無 GPU 時，透過 Kaggle 遠端執行 GPU 程式。

### 完整操作循環

```
編輯 .py → 轉 .ipynb → 準備 metadata → push → 監控 → debug → 修復 → re-push
```

### 1. 推送 ipynb 到 Kaggle 執行

```bash
# 準備推送資料夾（需包含 kernel-metadata.json + .ipynb）
mkdir -p /tmp/kaggle-kernel && cd /tmp/kaggle-kernel

# 建立 metadata（首次推送）
cat > kernel-metadata.json << 'EOF'
{
  "id": "username/kernel-slug",
  "title": "Kernel Display Title",
  "code_file": "notebook.ipynb",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": "true",
  "enable_gpu": "true",
  "enable_internet": "true",
  "dataset_sources": ["username/dataset-slug"],
  "machine_shape": "NvidiaTeslaT4"
}
EOF

# .py → .ipynb 轉換（含 compile 驗證每個 cell）
python3 /path/to/py_to_ipynb.py source.py /tmp/kaggle-kernel/notebook.ipynb

# 推送
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels push -p /tmp/kaggle-kernel/

# 指定加速器和超時
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels push -p /tmp/kaggle-kernel/ --accelerator GPU_T4 -t 7200
```

metadata 關鍵欄位：`id`(owner/slug)、`code_file`(須與實際檔名一致)、`kernel_type`(notebook/script 不可混用)、`machine_shape`(T4/P100/V100)、`dataset_sources`(自動掛載到 /kaggle/input/)

常見推送錯誤：409 Conflict(前版仍在跑)、400 Bad Request(metadata 格式錯)、title/slug 不匹配(警告但可推送)

### 2. 查看 Kernel List

```bash
# 列出自己的 kernel
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels list -m
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels list -m --page-size 20 --sort-by dateRun

# 搜尋特定用戶
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels list --user MHHUANG14
```

Python API：
```python
from kaggle.api.kaggle_api_extended import KaggleApi
api = KaggleApi(); api.authenticate()
kernels = api.kernels_list(mine=True, page_size=20)
for k in kernels:
    print(f"{k.ref} | {k.title} | lastRun={k.lastRunTime}")
```

注意：Python API 的 `kernels_list(search=..., mine=True)` 可能 401（gRPC 認證問題），CLI 更穩定。

### 3. 即時監控 Kernel 執行進程

```bash
# 方法 A：kernels output（推薦，100% 可靠）
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels output OWNER/SLUG -p /tmp/kout/
# → "Kernel is still running" = 執行中
# → 下載 .log + output 檔案 = 已完成

# 方法 B：kernels status（常回 500，不推薦）
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels status OWNER/SLUG

# 方法 C：自動化輪詢監控
while true; do
 RESULT=$(KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels output OWNER/SLUG -p /tmp/kout/ 2>&1)
 if echo "$RESULT" | grep -q "still running"; then
 echo "[$(date +%H:%M:%S)] 仍在執行..."
 rm -rf /tmp/kout; mkdir -p /tmp/kout; sleep 60
 elif ls /tmp/kout/*.log 2>/dev/null; then
 echo "[$(date +%H:%M:%S)] 完成！"; break
 fi
done

# 方法 D：Hermes cron 自動監控（長時間 GPU 訓練，5-10 分鐘級別）
# 建立一個 Python 腳本 check_kaggle_latest.py，用 KaggleApi 下載最新 output
# 然後用 Hermes cronjob 每 5 分鐘執行一次（repeat=12, schedule=5m）
# cron 會自動回報狀態到對話中
```

**⚠️ kernels output 行為細節（v6.19 實測）：**
- **Kernel 執行中（RUNNING）時**：CLI `kernels output` 會**阻塞/卡住**，不回傳 "still running"，也不寫入檔案，直到 kernel 完成或超時。Python API `api.kernels_output()` 行為相同。
- **Kernel 完成（COMPLETE）後**：正常下載 .log + output 檔案到指定路徑。
- **非阻塞檢查替代方案**：用 `kernels list -m --sort-by dateRun` 觀察 `lastRunTime` 是否更新，或用 `kernels pull -m` 確認版本號增加。
- **輪詢腳本需改用 status + list 組合**：`kernels status` 雖常回 500，但偶爾成功；配合 `kernels list` 間接判斷。

### 4. 停止 Runtime

**重要：CLI 無 `kaggle kernels stop` 命令。** 替代方案：

- **方案 A（推薦）**：Kaggle Web UI → Code → Your Work → 目標 kernel → Cancel Run
- **方案 B**：等待自然結束（超時或 OOM 自動終止），用 `kernels output` 監控
- **方案 C（不推薦）**：改 title/slug 推送新版本（舊 slug 仍殘留）

確認已停止：`kernels output` 下載到 .log → 已停止；"still running" → 仍在跑

### 5. 輸出與解析 Logs

```bash
# 下載 output（含 .log 和 notebook 產出的檔案）
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels output OWNER/SLUG -p /tmp/kout/
```

.log 格式：每行一個 JSON 物件 `{"stream_name":"stdout|stderr","time":15.12,"data":"..."}`

```python
# 解析 stdout
import json
with open("/tmp/kout/kernel-slug.log") as f:
    for line in f:
        entry = json.loads(line)
        if entry.get("stream_name") == "stdout":
            print(entry["data"], end="")

# 解析 error traceback
with open("/tmp/kout/kernel-slug.log") as f:
    for line in f:
        entry = json.loads(line)
        if entry.get("stream_name") == "stderr":
            print(entry["data"], end="")
```

### 6. Pull → 修改 → Re-push 循環

```bash
# 下載既有 kernel（含 metadata）
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels pull OWNER/SLUG -p /tmp/kpull/ -m

# 修改 /tmp/kpull/notebook.ipynb

# 重新 push（使用原 metadata）
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels push -p /tmp/kpull/
```

## Pitfalls

### 筆記本 source 格式的關鍵陷阱

70. **Kaggle notebook code cell `source` 必須是 `str` 而非 `list`** — 這是 Kaggle 平台最隱蔽但也最致命的坑之一。當你把 notebook JSON 中的 code cell source 設為 `list`（即使只有一個元素，如 `["# whole script..."]`），Kaggle 的 kernel runner 會**跳過所有 cell 的實際執行**，只執行 nbconvert 把 notebook 轉為 HTML。症狀：kernel 狀態從 RUNNING 瞬間跳到 COMPLETE，output 只有 `.log` 檔案（內容僅 nbconvert 轉換記錄），沒有 `__results__.html` 以外的任何輸出檔案，沒有 stdout/stderr 訓練日誌。**v6.19 慘痛教訓**：v1~v3 都因為 source=list 導致 Kaggle 跳過執行，v4 改回 str 後才真正開始運行。但 v4 推送後因缺少 `"is_idle_no_idle": true`，kernel 進入 idle 狀態後被 Kaggle 自動清理，導致 kernel 在 list 中可見但網頁/(output API 都回 404。

**觸發場景**（三種情況會把 source 從 str 變成 list）：
- (a) 使用 `nbformat` 套件讀取 notebook 後再寫出（nbformat v4.x 預設將 str source 轉為 list of lines）
- (b) 呼叫任何 notebook 正規化/驗證函式（如 `nbformat.normalize()`、`nbformat.validate()` 加 `upgrade=False` 仍會改 source 格式）
- (c) 手動加 cell `id` 欄位時，若透過 nbformat 的 API 操作而非直接操作 JSON dict

**正確做法**：
- 直接操作 `json.load()` / `json.dump()` 讀寫 notebook，**不經過 nbformat 套件**
- 若需加 cell IDs，直接修改 dict：`cell['id'] = uuid.uuid4().hex[:10]`，不要用 `nbformat` API
- 每次修改後**務必確認** `isinstance(cell['source'], str)`，若發現是 `list` 則還原：`cell['source'] = ''.join(cell['source']) if isinstance(cell['source'], list) else cell['source']`
- 推送前用 assert 檢查：`assert isinstance(nb['cells'][1]['source'], str), "source must be str!"`
- **推送_metadata 必須加 `"is_idle_no_idle": true`** — 否則 kernel push 成功後會進入 idle 狀態，需手動到 Web UI 按 "Run"，否則可能被自動清理

**修復被錯誤轉換的 notebook**：
```python
import json
with open('broken.ipynb') as f:
    nb = json.load(f)
for cell in nb['cells']:
    if isinstance(cell['source'], list):
        cell['source'] = ''.join(cell['source'])
with open('fixed.ipynb', 'w') as f:
    json.dump(nb, f)
```

**驗證方法**：推送後等 15-30 秒，`kaggle kernels status` 顯示 `RUNNING` 表示正常執行。若直接跳到 `COMPLETE` 且 output 只有 nbconvert log，就是 source 格式問題。若 kernel 在 list 中但網頁/API 回 404，就是缺少 `is_idle_no_idle` 導致 idle 被清理。

71. **Python 語法陷阱: inline comment 吞噬 closing delimiter** (v6.23 新增) — 在 notebook code cell 中，若 `lambda:`、`field(default_factory=...)` 或任何 inline expression 內的 dict/list literal 後**同一行加 comment**，Python parser 會將 closing `}`/`]`/`)` 視為 comment 一部分而吞噬，引發 `SyntaxError: '{' was never closed`。這在自動生成 notebook 代碼時極易觸發（如 docstring 更新、參數調整時殘留 comment）。
  - ❌ `reward_weights: dict = field(default_factory=lambda: {"ic": 0.35, "length": 0.08  # comment})`
  - ✅ `# comment\nreward_weights: dict = field(default_factory=lambda: {"ic": 0.35, "length": 0.08})`
  - **通用規則**: 在任何 inline expression（lambda、list comprehension、dict literal 等）中，**不要在 literal 後同一行加 comment**。將 comment 移至上一行或分行。

72. **KGAT_ Token 在 session 中可能過期** (v6.23 續集新增) — 同一 session 中，同一個 KGAT_ token **從 push 成功 → 幾分鐘後所有 API 調用 401/403**。推測 token 有極短 TTL 或被 Kaggle 撤銷。現象：`kernels push` 成功，但隨後 `kernels list -m`、`kernels output`、`kernels pull` 全部 401/403。解決：(a) 改用 `KAGGLE_API_TOKEN` 環境變數（較長 TTL）；(b) 或到 Kaggle Settings → Account → Create New Token 重新生成 kaggle.json。**關鍵**：push 成功不代表後續監控可用，長任務需預先設定環境變數認證。

75. **conditional import 造成 UnboundLocalError** (v6.23 fix4 新增) — 在 `if/else` 分支內做 `import numpy as np`（如 `if fallback: import numpy as np`），Python 3.12+ 會將 `np` 標記為整個函式的局部變數。當程式走 `else` 分支時，`np` 從未賦值 → `UnboundLocalError: cannot access local variable 'np' where it is not associated with a value`。**修復**：將 `import numpy as np` 移到函式開頭（在任何 if/else 之前），確保無論哪個分支都有一致的 `np` 定義。同樣原則適用於 `import pandas as pd` 等。**這是 Python 3.12+ 嚴格化的 scoping 規則，舊版 3.10/3.11 不會觸發此錯誤。**

73. **dataset_sources 錯誤 slug 靜默失敗** (v6.23 續集新增) — `kernel-metadata.json` 中 `dataset_sources` 引用不存在的 dataset slug（如 `twstock-grpo-dataset-v2`），Kaggle **不報錯**，只是靜默不掛載任何數據到 `/kaggle/input/`。Notebook 用 `os.walk('/kaggle/input/')` 發現空目錄，fallback 行為取決於代碼邏輯（若無 fallback 則 `sys.exit(1)` 或產出空結果）。**修復**：push 前先 `kaggle datasets list` 確認 slug 存在，或在 notebook 開頭加 debug print 列印 `/kaggle/input/` 實際掛載內容。**經驗**：dataset slug 錯誤是「無數據」最上游的根因，優先於 notebook 落地邏輯排查。

74. **Notebook 應有 graceful fallback 而非 sys.exit(1)** (v6.23 續集新增) — 當真實數據不可用（dataset 未掛載、檔案缺失、格式錯誤）時，notebook 應 fallback 到合成數據繼續執行，**不要**用 `sys.exit(1)` 直接終止 kernel。`sys.exit(1)` 導致：(a) kernel 瞬間 COMPLETE，無任何訓練日誌；(b) 無法區分「數據問題」與「代碼邏輯錯誤」；(c) 浪費 GPU quota（kernel 啟動→秒結束）。**修復模式**：try/except 包裹數據載入，失敗時生成合成數據 + print 警告，繼續執行訓練邏輯。這對迭代開發至關重要——數據問題不應阻斷代碼邏輯驗證。

1. **`--max` 參數已移除** — 新版 kaggle CLI 2.2.1 不支援 `--max`，改用 `--page-size`
2. **kaggle.json 認證不穩定** — 部分命令（`kernels list -m`、`datasets list -m`）用 kaggle.json 會認證失敗，必須用 `KAGGLE_API_TOKEN` 環境變數
3. **新舊 token 格式不同** — `KGAT_xxxx` 是新版 token（用環境變數），`kaggle.json` 中的 `key` 是舊版 API key，兩者不可互換
4. **access_token 檔案方式也不穩定** — `~/.kaggle/access_token` 存放新 token 仍可能認證失敗
5. **pip install 後 CLI 可能不在 PATH** — 需用 `~/.local/bin/kaggle` 或加 PATH
6. **push 需要完整資料夾** — 必須包含 `kernel-metadata.json` 和對應的 code_file
7. **machine_shape 選項** — `NvidiaTeslaT4`、`NvidiaTeslaP100` 等，在 `kernel-metadata.json` 或 `--accelerator` 參數指定
8. **kaggle.json 的 key 不是 KGAT_ token** — 如果用戶提供的是 `KGAT_` 前綴 token，只能用環境變數方式，不能寫入 kaggle.json
9. **Kaggle 筆記本必須自含全部邏輯** — Kaggle 環境無法 import 本地自訂模組。所有 class、function、config 必須 inline 在單一 .py 或 .ipynb 中。若本地模組更新，必須同步更新 Kaggle 版本。
10. **Kaggle base image 可能缺 scipy** — `pd.Series.corr(method='spearman')` 依賴 scipy，缺時拋 `ModuleNotFoundError`。改用 numpy rank-based spearman：`scipy.stats.spearmanr` → `numpy.argsort(argsort(x))` 計算 rank correlation。
11. **script 模式 vs notebook 模式** — `kernel_type: "script"` 對應 `.py` 檔案，`kernel_type: "notebook"` 對應 `.ipynb`。兩者不能混用，code_file 副檔名必須匹配。
12. **Python → ipynb 轉換陷阱** — 將 `.py` 轉為 `.ipynb` 時常見問題：(a) 行號前綴（如 `10|`）會導致 IndentationError；(b) Cell 切割不能切斷 class/function 定義，否則該 Cell 無法獨立執行；(c) 每个 code cell 的 source 必須是字串 list，每行末尾加 `\n`（最後一行除外）；(d) 每个 cell 必須有 `id` 欄位（可用 uuid），否則 Kaggle 會拋 MissingIDFieldWarning 並可能在未來版本硬錯誤。推薦做法：用 json 直接構建 nbformat 4.5 notebook，每個 cell 用 `compile()` 驗證後再推送。
13. **"Push 成功但 Kernel 消失"症候群** — `kaggle kernels push` 回報 "Kernel version N successfully pushed" 但 kernel 不出現在 `kernels list --mine`、網頁返回 404。可能原因：(a) Kaggle 索引延遲（新 kernel 需數分鐘才出現）；(b) 帳號 kernel 數量上限（默認 1000，但可能較低）；(c) kernel 執行失敗過快（<1s 出錯）可能不產生版本記錄。排查步驟：1. 等 5 分鐘再查 list；2. 嘗試 `kaggle kernels pull OWNER/SLUG`；3. 檢查 Kaggle 網頁 "Your Work" 頁面；4. 用不同 slug 重新推送；5. 若持續失敗，在 Kaggle 網頁手動創建 notebook 再用 API push 更新。
14. **`kernels status` 500 Server Error 是 Kaggle 端問題** — `kaggle kernels status OWNER/SLUG` 返回 500 不代表認證失敗或 kernel 不存在，而是 Kaggle v1 gRPC endpoint (`GetKernelSessionStatus`) 的間歇性故障。此時所有 kernel 的 status 都會 500，不限特定 kernel。替代方案：通過網頁查看、用 `kernels list` 間接推斷（lastRunTime 更新 = 已執行）、或用 `kernels pull` 確認版本更新。
15. **Notebook cell 數量與大小建議** — Kaggle notebook 建議 5-15 個 code cell，每個 cell 50-200 行。單一 cell 超過 500 行仍可執行，但出錯時難以定位。過多 cell（>30）則增加 notebook 解析風險。推薦按功能模塊切割：imports → constants → class definitions → training → evaluation → output。
- `is_private` 欄位必須是字串 — `kernel-metadata.json` 中 `"is_private": "true"` 而非布林值 `true`。Kaggle CLI 對此容忍但行為可能不同。同樣 `"enable_gpu": "true"` 也建議用字串。
- **title 中的點號（.）會導致 slug 不匹配，觸發 400 Bad Request** — Kaggle 從 title 推導 slug 時，將點號視為普通字元保留（如 `v6.16` → slug 含 `v6.16`），但 id 欄位中的點號被 Kaggle 轉為連字號（如 `twstock-grpo-v6-16`）。兩者不一致時回 400。**修復**：title 中的版本號用空格取代點號（如 `v6 16` 而非 `v6.16`），使推導出的 slug 與 id 欄位完全一致。同理，title 中避免其他可能轉換不一致的特殊字元（括號、加號、斜線）。
17. **PyTorch CUDA capability 相容性 — sm_60 不等於可用** — Kaggle 可能分配 P100（sm_60）而非 T4（sm_75）。`torch.cuda.get_device_capability(0)` 回傳 `(6, 0)` 代號 sm_60，但 PyTorch 2.10+cu128 只編譯了 sm_70/75/80/86/90/100/120 的 CUDA kernel。**`cc[0] >= 5`（sm_50）的判斷是錯的** — sm_60 通過此檢查但實際執行任何 CUDA op 會拋 `AcceleratorError: CUDA error: no kernel image is available for execution on the device`。正確做法：(a) **`cc[0] >= 7`**（sm_70）才標記 GPU 相容；(b) **更安全（已驗證可行）**：用 `try/except` 實際建一個小 tensor `torch.zeros(1, device="cuda")` + 做一次運算 `_test = _test + 1.0` + `torch.cuda.synchronize()` 測試，失敗則 fallback CPU（v4.1 實測：P100 probe 失敗 → 自動 CPU fallback → 訓練成功完成）；(c) 設 `GRPO_FORCE_CPU=1` 強制 CPU 模式。`GRPOConfig.auto_detect()` 也需檢查此變數。CPU fallback 配置（G=4, batch=16, steps=3000）可用但較慢（4 regime ~18min）。
18. **PyTorch API: `total_memory` not `total_mem`** — `torch.cuda.get_device_properties(0)` 的屬性是 `.total_memory`（非 `.total_mem`）。後者拋 `AttributeError`。
19. **torch.cat autoregressive 維度陷阱** — GRPO 生成公式時 `action = dist.sample()` 從 `Categorical(logits=[1, vocab_size])` 取樣，形狀為 `[1]`（1D）。接到 `inp`（2D `[1, seq_len]`）用 `action.view(1, 1)` 變 `[1,1]`（2D）。**不要**用 `.unsqueeze(0).unsqueeze(0)` — 這會產生 3D `[1,1,1]`。`.unsqueeze(0)` 雖然也產生 `[1,1]`，但語義不如 `.view(1,1)` 清晰，且在 guided decoding 中若 action shape 變化時 `.view` 更安全。規則：cat 前 print 兩個 tensor 的 `.shape` 確認一致。
20. **`kaggle kernels push` 409 Conflict** — 兩種觸發場景：(a) 同一 slug 的前一版 kernel 仍在執行中；(b) `id` 欄位與帳號下已存在（含已完成）的 kernel slug 衝突。場景 (b) 常發生在修改 metadata 的 `id` 但 title 推導的 slug 與舊版重疊時。CLI 無 `kaggle kernels stop` 命令。解法：(a) 等 kernel 執行完成（用 `kernels output` 監控），(b) 到 Kaggle Web UI 手動取消（Code → Your Work → Cancel Run），(c) 用全新 title/slug 推送避免衝突（如 `grpo-v33-regime-alpha-factor-training`）。場景 (b) 只能用方式 (c)。注意：Kaggle 自動將 title 轉為 slug（空格→連字號、大寫→小寫、移除特殊字元），須確認新 title 不與既有 slug 重複。
21. **`kernels output` 是比 `kernels status` 更可靠的監控方式** — `kernels status` 常回 500，但 `kernels output OWNER/SLUG -p /path` 一定能工作：(a) kernel 仍在執行 → 回傳 "Kernel is still running"；(b) kernel 已完成 → 下載 .log + output 檔案到指定路徑；(c) kernel 失敗 → .log 中包含完整 traceback。推薦監控模式：迴圈呼叫 `kernels output`，解析回傳字串判斷狀態。注意：即使 kernel 仍在執行中，下載的 .log 也可能包含截至目前為止的部分輸出（JSON 格式，每行一個 entry），可用於診斷問題而不需等待完成。
22. **.py→.ipynb cell 切割必須驗證編譯** — 用 `compile(''.join(cell_source), '<cellN>', 'exec')` 逐一驗證每個 code cell。常見失敗模式：(a) cell 切在 class/function 中間（導致 `unexpected indent` 或 `NameError`）；(b) section header 行號因 patch 而偏移但切割邊界未同步更新。推薦：用正則掃描 `# ====... # N. section_name` 動態定位切割點，不要硬編碼行號。
23. **重複 class 定義會導致隱蔽 bug** — patch 大檔案時若同一 class 被定義兩次（如 StackVMState 在 line 153 和 line 230），Python 使用最後一個定義，但兩個實例的 `__class__` 不同，可能導致 isinstance 檢查失敗或狀態不一致。必須用 `grep -n "^class ClassName" file.py` 確認只有一個定義，若有多個則刪除舊版。
24. **Kaggle kernel 執行失敗的完整 debug 流程** — (1) `kaggle kernels output OWNER/SLUG -p /tmp/kout/` 下載 log；(2) 解析 .log 中的 stderr traceback（JSON 格式，stream_name="stderr"）；(3) 在本地修復 .py 檔案 → 驗證語法 `py_compile` → 重建 notebook → push。常見失敗模式見 references/grpo-kernel-debug-iteration.md。
25. **DataFrame 欄位大小寫不匹配是隱蔽的零收斂根因** — 特徵工程函數生成小寫欄位（`ret`, `liq_score`），但常數定義使用大寫（`RET`, `LIQ_SCORE`）。正規化邏輯遍歷大寫名稱 → 找不到欄位 → 設為零 → 特徵全零 → 信號無效 → reward=-5.0 → loss=0。此 BUG 語法完全正確，py_compile/ast.parse 無法偵測。診斷：對比 `df['RET']`（大寫正規化後）vs `df['ret']`（小寫原始）確認兩者不同。修復：在正規化前 `df.rename(columns={f.lower(): f for f in FEATURE_NAMES})`。
31. **確認 Kaggle kernel 版本的唯一可靠方式** — 截圖中的 log 文字可能與代碼格式看似不同（如 `valid=100.0%` 截圖中可能讀成 `mean_valid=100.0%`），容易誤判為「跑的是舊版」。正確做法：`kaggle kernels pull OWNER/SLUG -p /tmp/pull/` 取得實際代碼，比對特定格式字串（如 print template 的精確拼寫）。也可以在代碼中加入版本號 print（如 `print("v15.0")`）作為快速識別。
32. **Kaggle GPU session 並行上限為 2** — 同一帳號最多 2 個 GPU kernel 同時執行。超過時 `kaggle kernels push` 回報 `Maximum batch GPU session count of 2 reached`。此時需：(a) 等既有 GPU session 完成（用 `kernels output` 監控），(b) 到 Kaggle Web UI 手動 Cancel Run，(c) 改用 CPU-only metadata（移除 `enable_gpu` 和 `machine_shape`），CPU 模式不受此限。注意：即使舊 kernel 已執行完畢（有 log），GPU slot 可能仍被佔用（Kaggle 延遲釋放）。
33. **`kaggle kernels push` 不自動執行** — push 只是上傳新版本，不保證立即執行。若需 push 後自動開始執行，在 `kernel-metadata.json` 中加入 `"is_idle_no_idle": true`。否則 kernel 會進入 idle 狀態，需到 Web UI 手動按 "Run" 才會啟動。
34. **`kernels output` 下載空目錄 ≠ kernel 失敗** — `kaggle kernels output OWNER/SLUG -p /path/` 下載後目錄為空，可能是：(a) kernel 仍在佇列中等待執行（尚未開始），(b) kernel 正在執行中（此時應回傳 "still running"，但偶爾靜默返回空目錄），(c) kernel 執行完畢但無產出檔案（只有 .log）。區分方式：檢查 .log 是否存在。有 .log = 已完成（至少開始執行），無 .log = 尚未開始。
56. **`kernels output` 可能返回部分執行 log** — `kaggle kernels output` 在 kernel 仍在執行時，可能下載一個包含部分 log 的 .log 檔案（而非回傳 "still running" 字串）。此 log 會在最後一個已寫入的 JSON entry 處截斷，導致看起來只完成了部分 cell。**判斷方式**：(a) log 最後一行不是 `[Cell N DONE]` 且沒有 NbConvertApp entry → 可能是截斷；(b) 等數分鐘後再次 `kernels output` 下載，若新 log 更大 → 前次是部分 log；(c) 第二次下載若只剩 NbConvertApp entries（~800 bytes）→ kernel 已完成，前次已下載完整執行 log，第二次只取到轉換步驟的 log。**可靠確認完成的方法**：檢查第二次下載的 log 是否包含 `[NbConvertApp] Writing N bytes to __results__.html`，這是 Kaggle notebook 執行完成後的 HTML 轉換步驟，出現即代表 kernel 已完成。
58. **`python3 -m kaggle` 比 `kaggle` CLI 更可靠** — `pip install kaggle` 後 CLI 二進位可能在 `~/.local/bin/kaggle` 不在 PATH，直接呼叫 `kaggle` 會報 `command not found`。`python3 -m kaggle` 透過 Python module 機制執行，永遠可用。所有 kaggle 子命令都支援：`python3 -m kaggle kernels status OWNER/SLUG`、`python3 -m kaggle kernels output OWNER/SLUG -p /path/`、`python3 -m kaggle kernels push -p /dir/` 等。
59. **GRPO GPU 訓練 regime 分類可能遺漏 regime** — 在合成數據上用 GPU 訓練時（v5.1/v5.4），只有 1 個 regime（mid_cap_tech/2882）被訓練，其他 3 檔（2330/2454/1301）未出現在 regime 分類中。CPU 版本（v4）成功訓練全部 4 regime。可能原因：(a) 合成數據 regime 分類邏輯 bug；(b) group_size 過濾條件太嚴格。**建議**：kernel 開頭加 debug print 列出每檔股票的 regime 分類結果，確認全部股票都被分配到 regime。
60. **[v5.9→v6.0] `--accelerator` 和 `machine_shape` 均無效** — API push 無法控制 GPU 型號分配。**防禦措施**：(a) notebook 開頭必須有 `try: torch.zeros(1, device='cuda')` 實測（不用 sm 版本檢查，P100 sm_60 完全相容 PyTorch 2.x CUDA）；(b) CPU fallback 需 G≥16（G=4 會 advantage collapse，見 twstock-alpha-gpt #90）；(c) **唯一可靠方式**：Kaggle Web UI 手動選 T4 accelerator。
26. **jupytext 轉換的 .ipynb 缺少 kernelspec metadata** — `python3 -m jupytext source.py --to ipynb` 產生的 notebook 不含 `metadata.kernelspec`，導致 Kaggle papermill 執行時拋 `ValueError: No kernel name found in notebook and no override provided`。必須在轉換後手動注入：`nb["metadata"]["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}`。也加入 `"language_info": {"name": "python", "version": "3.12.0"}` 確保相容。
27. **jupytext `--pipe` 參數會清空 notebook 內容** — `jupytext source.py --to ipynb -o out.ipynb --pipe true` 會把 notebook 內容清空為 0.3KB 空殼（`--pipe` 是將內容 pipe 給外部命令處理後回寫，`true` 不產生 output → notebook 被覆蓋為空）。正確做法：**不要用 `--pipe`**，只用 `jupytext source.py --to ipynb -o out.ipynb`。
28. **pandas 反覆 set_index/reset_index 造成 level_0 衝突** — 在 groupby 迴圈中反覆執行 `g = g.set_index("date")` / `g = g.reset_index()` 會拋 `ValueError: cannot insert level_0, already exists`。根因：groupby 後 g 的 index 含 group key，第一次 reset_index 把 group key 放回 columns，第二次 reset_index 發現欄位已存在就嘗試用 `level_0` 命名 → 衝突。修復方案：用 `pd.merge(how='left', on=join_cols)` 取代 `set_index/reindex/reset_index` 模式；或在 groupby 後立即 `g = g.reset_index(drop=True)` 取得乾淨 integer index，再做所有計算。
29. **PyTorch PPO ratio 必須保持有效梯度（非零偏導數）**：三種寫法梯度行為完全不同：(a) `ratio = torch.ones_like(log_probs_tensor)` — 無 grad_fn，斷開計算圖，backward 拋 RuntimeError；(b) `ratio = 1.0 + 0.0 * log_probs_tensor` — **最隱蔽的 bug**：計算圖連接但 `d(ratio)/d(log_pi)=0.0`，梯度為零，模型永遠不學習（loss=-0.0000）；(c) `ratio = torch.exp(log_probs_tensor - log_probs_tensor.detach())` — ✅ 正確：ratio=1.0，`d(ratio)/d(log_pi)=1.0`。同理 warmup 階段 `log_prob = torch.tensor(0.0, requires_grad=True)` 是葉節點無 grad_fn，梯度無法回傳模型參數。修復：warmup 時仍用模型 forward pass 取得 dist.log_prob(action)。
30. **[已更正 2026-06-11] P100 (sm_60) 與 PyTorch 2.x 相容，sm 門檻拒絕是錯誤邏輯** — 原結論「P100 不相容」是錯的。v5.7 的 CUDA error 根因是 Kaggle 預裝 `PyTorch+cpu`（非 `+cu128`），安裝 CUDA 版後 P100 可正常執行。v5.9 實測 P100 被 `cc[0]>=7` 門檻錯誤拒絕→CPU fallback→advantage collapse。**正確做法**：不安裝 CUDA PyTorch 時才 CPU fallback；安裝後用 `try: torch.zeros(1, device='cuda')` 實測，失敗才 fallback。CPU fallback 需 G≥16（G=4 會結構性坍縮，見 twstock-alpha-gpt pitfall #90）。
35. **PyTorch Categorical logits 必須 squeeze batch dim** — model forward 回傳 `(B, T, vocab)` logits，取 `[:, -1, :]` 後為 `(1, vocab)`。若不加 `.squeeze(0)` 就傳給 `Categorical`，Categorical 視為 batch=1 → `log_prob()` 回傳 1D `[1]` 而非 scalar `[]`。混合不同路徑的 log_prob 到 `torch.stack` 會拋 `RuntimeError: stack expects each tensor to be equal size, but got [1] at entry 0 and [] at entry N`。所有路徑（主迴圈、warmup、fallback）都必須 `.squeeze(0)`。保險措施：stack 前加 `[lp.reshape(()) for lp in all_log_probs]`。
36. **Script 模式 .py 推送後縮排錯誤仍可能發生** — 本地 `py_compile.compile()` 通過不代表 Kaggle 執行環境不會報 `IndentationError`。常見原因：(a) 本地修復用 Python 腳本替換行時，空行殘留 1sp（非 0sp）不影響本地語法但 Kaggle papermill 解析可能不同；(b) tab/space 混合（本地編輯器自動 tab→space 但替換腳本可能插入 tab）；(c) Unicode 空格（NBSP 0xa0）混入。建議：修復腳本中加入 `line.encode('utf-8')` hex dump 檢查關鍵行的前導字元；推送前用 `python3 -c \"import ast; ast.parse(open('file.py').read())\"` 做第二道驗證。
37. **FinMind 期貨 OI 機構名稱是中文** — `taiwan_futures_institutional_investors` API 回傳的 `institutional_investors` 欄位是中文（`外資`、`投信`、`自營商`），不是英文（`Foreign Investor` 等）。用英文名稱比對會導致 `inst_net_oi` / `retail_net_oi` 全為 NaN，3 個期貨因子恆為 0。正確做法：`df[df["institutional_investors"] == "外資"]` 取外資 OI，`df[df["institutional_investors"].isin(["投信", "自營商"])]` 取投信+自營商。另外，此 API 的 `net_open_interest` 欄位可能不可靠，建議自行計算 `net_oi = long_open_interest - short_open_interest`。
38. **Kaggle notebook 缺少真實數據會 fallback 合成數據** — 若 dataset_sources 中未包含真實訓練數據集，notebook fallback 到合成數據時，期貨OI/美股因子等外部數據因子全為 0（合成數據只生成 OHLCV）。症狀：14/22 因子恆為 0，GRPO 訓練信號極弱。解決：在推送 kernel 前，先 `kaggle datasets create/version` 上傳真實數據 CSV，然後在 `kernel-metadata.json` 的 `dataset_sources` 引用該 dataset。
39. **Kaggle dataset_sources 掛載路徑是三層巢狀結構** — 實際掛載路徑為 `/kaggle/input/datasets/{owner}/{dataset-slug}/{files}`，**不是**文件常載的 `/kaggle/input/{dataset-slug}/{files}`。用 `os.listdir('/kaggle/input/')` 只會看到 `datasets/` 目錄，再 `os.listdir` 一層只看到 `owner/`，需三層才能到達 CSV 檔案。**修復**：用 `os.walk('/kaggle/input/', topdown=True)` 遞迴搜尋目標檔案（如 `twstock_daily.csv`），不要假設固定深度。其他靜默失敗場景：(a) dataset slug 拼寫錯誤（Kaggle 不報錯，只是不掛載）；(b) dataset 剛 version 更新後索引延遲；(c) kernel push 時引用的 dataset 版本已被刪除/替換。診斷方式：notebook 開頭加 `import os; [print(root, files) for root, dirs, files in os.walk('/kaggle/input/')]` 確認實際掛載內容與路徑深度。若目錄為空或找不到檔案，需到 Kaggle UI 手動重新綁定 dataset（Settings → Data → Add Data Source）。
40. **FinMind API 是台股真實數據的可靠來源** — 從 HF Space 或 Kaggle 環境均可存取。關鍵 API：`StockPrice`（OHLCV）、`taiwan_stock_institutional_investors`（三大法人）、`taiwan_stock_margin`（融資融券）、`taiwan_futures_daily`（期貨日K+OI）、`taiwan_futures_institutional_investors`（期貨法人OI）。**注意**：期貨法人 OI 的 `institutional_investors` 欄位是中文（`外資`/`投信`/`自營商`），不是英文。TWSE/TAIFEX 官方 API 從雲端環境因 IP 限制不可用（451/TLS error）。完整工作流見 `twstock-alpha-gpt` skill references/finmind-real-data-workflow.md。
41. **Kaggle push 409 Conflict 後的恢復策略** — (a) 首選：等舊 kernel 完成後再 push（用 `kernels output` 監控）；(b) 到 Kaggle Web UI → Code → Your Work → Cancel Run；(c) 用全新 title/slug 推送避免衝突（如加版本號 v5, v6 等）；(d) **不建議**：反覆嘗試 push，只會被限流。409 也可能是 slug 與已完成 kernel 衝突（非正在執行），此時只能用方式 (c)。
42. **Kaggle 環境可能預裝 CPU-only PyTorch** — 即使 metadata 設 `enable_gpu: true` + `machine_shape: NvidiaTeslaT4`，執行環境可能仍分配 `PyTorch 2.10.0+cpu`（非 `+cu128`），`torch.cuda.is_available()=False`。v3.2 實測遇到此問題。**修復**：在 notebook 開頭強制安裝 CUDA 版：`pip install torch --index-url https://download.pytorch.org/whl/cu128`，安裝後 `importlib.reload(torch)` 確認版本。注意：若 GPU 為 P100 (sm_60)，PyTorch 2.10+cu128 仍不相容（見 pitfall #30），需 CUDA probe 實測。
43. **Dataset 掛載路徑 ≠ dataset slug 字串** — v3.1 寫死 `data_path = "/kaggle/input/twstock-training-data"` 但 dataset slug 為 `twstock-grpo-training-data`，導致掛載失敗靜默 fallback 到合成數據。Kaggle 掛載目錄名是 slug 的 normalized form（小寫、連字號）。**最佳實踐**：不寫死路徑，用遞迴掃描 `/kaggle/input/` 尋找目標 CSV 檔案，並加 verbose debug `print(os.listdir('/kaggle/input/'))` 確認實際掛載結構。
44. **Script 模式 (kernel_type=script) 可避免 notebook 格式截斷** — v4 嘗試 .py→.ipynb 轉換時 StackVM.execute() 定義被截斷（SyntaxError: incomplete input）。改用 script 模式（code_file=.py, kernel_type=script）直接推送 .py 檔案可避免此問題。缺點：出錯時只看到最終 traceback（notebook 模式可看到哪個 cell 失敗）。對已通過 py_compile 的大腳本，script 模式更高效。
45. **Loss/ Reward 印出格式建議 `.6f` 或 `.8f`** — GRPO 訓練中 loss 變化極小（如 -0.000042），若用 `.4f` 格式印出會顯示 `-0.0000`，誤導為「loss 完全為零」。建議所有關鍵訓練指標（loss、reward、advantage、IC）至少用 `.6f`，最好 `.8f`。此格式問題曾浪費大量調試時間在已修復梯度但仍誤判為零收斂的場景。
46. **`kernel-metadata.json` title 最長 50 字符** — `kaggle kernels push` 回 400 Bad Request 若 title 超過 50 字符。Kaggle 自動從 title 推導 slug（空格→連字號、大寫→小寫），slug 無獨立長度限制但 title 有。修復：縮短 title 或用縮寫（如 `GRPO v51 REINFORCE fix` 而非完整描述）。
47. **迭代修復大型 Kaggle 腳本用 build 腳本而非 patch** — 對 2000+ 行的 `.py` 訓練腳本做多次 bug fix 時，反覆 patch 會腐蝕縮排（見 pitfall #25）。改用 Python build 腳本（如 `/tmp/build_v51.py`）做目標字串替換：讀取 source → 多個 `code.replace(old, new)` → 寫出 → `py_compile.compile()` 驗證。優點：(a) 不腐蝕縮排；(b) 可重複執行；(c) 替換內容可追溯。前提：替換字串在源文件中必須唯一。
48. **`kaggle kernels pull` 不保留 cell outputs** — 從 Kaggle pull 回的 .ipynb 只含 code cells，所有執行結果（stdout、display output、報表）都不在內。若需查看執行結果，必須透過 `kaggle kernels output OWNER/SLUG -p /path/` 下載 .log 檔案。這是 Kaggle API 的設計限制，非 bug。完整 workflow 見 `references/existing-ipynb-push-workflow.md`。
57. **`kaggle kernels pull` 回傳的 metadata 會遺失 GPU/網路設定** — pull 回的 `kernel-metadata.json` 中 `enable_gpu` 會變成 `false`、`enable_internet` 變 `false`、`machine_shape` 變 `None`，即使推送時設為 GPU + internet。這是 Kaggle API 的已知行為，不代表實際執行時沒用 GPU。**切勿用 pull 回的 metadata 直接重新 push**（會變成 CPU 模式）。正確做法：保留原始推送用的 `kernel-metadata.json`，或手動修正 pull 回的 metadata 中的 GPU/網路設定。
49. **既有 .ipynb 可直接推送，不需 .py 轉換** — 當已有 .ipynb（如看板任務產出、Colab 移植、開源 repo notebook），直接 `cp` 至推送目錄 + 建好 `kernel-metadata.json`（`code_file` 指向 .ipynb、`kernel_type: "notebook"`）即可 push。不需經過 .py→.ipynb 轉換流程。注意 `code_file` 副檔名必須是 `.ipynb`（不可寫 `.py`），否則 Kaggle 會拒絕或以 script 模式執行。
50. **headless-run 工具（如 FaceFusion）在 Kaggle 的適配模式** — 三個關鍵繞過：(a) `CONDA_READY=1` 環境變數跳過 conda 安裝步驟（Kaggle 已有 Python 環境）；(b) `headless-run` 子命令替代 GUI 模式（Kaggle 無顯示器）；(c) `OMP_NUM_THREADS=1` 避免 OpenMP 與 Kaggle 預設衝突。VRAM 策略：T4 16GB 用 fp16 模型（如 `inswapper_128_fp16`），避免 OOM。**FaceFusion 模型預裝是必須的** — facefusion 最小化 face_swapper+face_enhancer 需要 ~1.45 GB 模型（分散在 models-3.0.0/3.1.0/3.3.0 三個 HF repo），Kaggle 免費 GPU 的 ~60 秒閒置偵測會在下載中途 CANCEL kernel。解決方案：預先下載模型到本地 → 打包成 Kaggle Dataset → 掛載到 `/kaggle/input/` → notebook 開頭 `cp *.onnx *.hash facefusion/.assets/models/`。**已建 Datasets**: `mhhuang14/facefusion-models-330`（1,603 MB, 26 files, private）+ `mhhuang14/facefusion-test-images`（source.jpg+target.jpg, private）。v4 已驗證完全離線+真人換臉成功。詳見 `references/facefusion-kaggle-model-cache.md`。
54. **Kaggle kernel 閒置 CANCEL 的三個觸發模式** — (a) `subprocess.run(capture_output=True)` 吞掉 stdout → watchdog 看不到輸出 → 60s 後 CANCEL；(b) 工具（如 facefusion）處理時靜默退出（placeholder 圖片無人臉）→ 後續 cell 不執行 → CANCEL；(c) 模型下載耗時過長（>60s 無 stdout）→ CANCEL。修復：(a) 改用 `capture_output=False` 或串流 stdout；(b) 用 try/except 包裹 subprocess，錯誤時繼續執行後續 cells；(c) 預裝模型為 Kaggle Dataset。每個 cell 結尾加 `print('[Cell N DONE]')` 標記幫助 debug。
55. **FaceFusion 模型架構與最小化需求** — 模型分散在多個 HuggingFace repo：`facefusion/models-3.0.0`（58 onnx）、`models-3.1.0`（11）、`models-3.2.0`（2）、`models-3.3.0`（8）、`models-3.4.0`（6）、`models-3.5.0`（15）、`models-3.6.0`（3）。URL 格式：`https://huggingface.co/facefusion/{repo}/resolve/main/{filename}`。最小化 face_swapper=inswapper_128_fp16 + face_detector=yoloface_8n 需要 22 個檔案（11 對 .hash+.onnx），總計 ~1.45 GB。核心模型清單：nsfw_1/2/3（content analyser，342 MB 最大）、fairface（face classifier）、yoloface_8n（face detector）、2dfan4/fan_68_5（face landmarker）、arcface_w600k_r50（face recognizer）、xseg_1（face masker）、inswapper_128_fp16（face swapper）。可選 face_enhancer=gfpgan_1.4（324.5 MB）。模型存放在 `facefusion/.assets/models/`，每個模型有對應 .hash 驗證檔。**Dataset 已完整**：`facefusion-models-330` 已更新為 26 檔案（含 bisenet_resnet_34 和 kim_vocal_2），v4 驗證完全離線執行成功。配合 `facefusion-test-images` Dataset 提供真人照片，face swap pipeline 完整可用。
51. **patch() 工具縮排腐蝕 — 每次替換多行區塊都可能破壞前導空格** — patch 工具替換 >5 行的區塊時，常將 4-space 縮排壓縮為 1-space，導致 IndentationError。更隱蔽的變體：class body 中 `def forward()` 從 8sp 被推到 12sp（語法合法但 PyTorch 找不到 forward → `NotImplementedError: Module is missing the required "forward" function`）。`py_compile.compile()` 和 `ast.parse()` 都無法偵測此變體——只有運行時才爆發。**正確模式**：(a) patch 改邏輯 → `py_compile` 驗證 → 若縮排壞了 → write_file Python 修復腳本（讀取檔案按行號修正，以周圍正確行為參照） → 再驗證；(b) >20 行的大段插入直接用 write_file Python 腳本，不用 patch；(c) 迭代修復大型 Kaggle 腳本（2000+ 行）用 build script 模式（讀取 → 多個 `code.replace(old, new)` → 寫出 → py_compile 驗證），不反覆 patch。**絕對不要反覆用 patch 修復縮排**——每次只會引入新的錯誤。
52. **驗證 .ipynb 內容時不要用字面量跨行搜索** — `.ipynb` 的 code cell source 是字串 list（`["line1\n", "line2\n"]`），用 `'\n'.join(cell['source'])` 拼接後搜索包含 `\n` 的字面量模式（如 `"KNOWN_REGIMES = {\\n    2330:"`）常因空格數量不匹配而失敗。正確做法：(a) 搜索單行片段（如 `"KNOWN_REGIMES"`），然後檢查其後續幾行；(b) 用 `json.load()` 後遍歷每個 code cell 的 `source` list，逐行比對；(c) 若只需確認某段代碼存在，用較寬鬆的單行匹配（如 `pattern in all_code` 其中 `all_code = '\n'.join(...)`，pattern 不含精確縮排）。**不要用硬編碼縮排的多行字面量做 PASS/FAIL 斷言**——.ipynb 的 JSON 縮排與 Python 代碼縮排是兩個不同的空格系統。
53. **.py→.ipynb cell 切割切斷 class 定義導致 PyTorch 找不到 forward()** — 即使每個 cell 單獨 `compile()` 通過（因為 cell A 的 `class SwiGLU(nn.Module): def __init__` 和 cell B 的 `def forward` 各自語法完整），Kaggle 逐 cell 執行時 cell B 的 `def forward` 不在 class body 內 → PyTorch `nn.Module.__call__` 找不到 forward → `NotImplementedError: Module is missing the required "forward" function`。**與 pitfall #72 的區別**：#72 是 patch 工具縮排腐蝕（同一檔案內 forward 過度縮排），此處是 cell 邊界切斷 class（不同 cell）。**修復**：確保整個 class（含 `__init__` 和 `forward`）在同一個 cell 中；或改用 script 模式（kernel_type=script）直接推送 .py 檔案，完全避免 cell 切割問題。檢查方式：grep notebook 中每個 cell 的 source，確認 `class X(nn.Module)` 和其 `def forward` 在同一 cell。
65. **PyTorch 降級安裝 (`pip install torch --index-url`) 在 Kaggle 會導致 C extension 版本不一致** — Kaggle 預裝的 `torch._C` C extension 常駐系統路徑（`/usr/local/lib/python3.12/dist-packages/torch/_C/`），pip install 只替換 Python 包但不替換已載入的 C extension。新版 Python 碼引用舊版 C extension 中不存在的符號 → `ImportError: cannot import name 'skip_code' from 'torch._C._dynamo.eval_frame'`。此崩潰觸發鏈為：model init → Adam optimizer → `__repr__` 觸發 dynamo compilation → eval_frame 導入失敗 → 全 crash。**結論：在 Kaggle 環境中 PyTorch 降級是結構性死路，切勿嘗試。** 正確做法：(a) 用 v6.11 的 CUDA probe 實測（`torch.zeros(1, device='cuda')` + `+1.0` + `synchronize()`），失敗則 CPU fallback；(b) 放棄「降級安裝舊版 PyTorch 支援 sm_60」的思路，P100 + cu128 = 不相容且無法修復。
66. **v6.13 實測驗證：PyTorch 降級失敗的完整崩潰鏈** — (1) Kaggle 分配 P100 sm_60 → cu128 不支援 → pip 降級 torch 2.6+cu126 安裝成功；(2) `importlib.reload(torch)` 後 TORCH_LIBRARY namespace 衝突：`Only a single TORCH_LIBRARY can be used to register the namespace triton`；(3) CUDA probe 仍失敗（`cudaErrorNoKernelImageForDevice`）→ CPU fallback；(4) 但降級後的 Python 碼與未替換的 C extension 不匹配 → `ImportError: cannot import name 'skip_code'`；(5) 任何觸發 `torch._dynamo` 的操作（如 Adam.__repr__）都會崩潰 → **kernel 全滅**。Kaggle slug: `mhhuang14/twstock-grpo-v6-13-complexity-reward-fix`, log 33825 bytes。
67. **Kaggle GPU 分配約 50% P100 / 50% T4** — `machine_shape: NvidiaTeslaT4` 和 `--accelerator GPU_T4` 完全無效（pitfall #60 已記錄），實測 v6.8~v6.13 五次 push 中約一半分配到 P100。策略設計必須假設 P100 為常態而非異常。
68. **GRPO CPU fallback 需要更小的模型配置** — CPU 模式沿用 GPU 的 Transformer 參數（d_model=48, nhead=4, nlayer=2）速度過慢。建議 CPU 專用：d_model=32, nhead=2, nlayer=1, G=32, batch=64, steps=3000, 簡化 backtest (只算 IC)。預期 4 regime 從 ~30min 降到 ~8min。
69. **kernel-metadata.json title 與 slug 必須一致** — push 時若 title 推導出的 slug 與 `id` 欄位不匹配，Kaggle 回 400 Bad Request。修復方法：title 不含特殊字元，用可預測的 slug 格式（如 `TWStock GRPO v6.13 complexity reward fix` → slug `twstock-grpo-v6-13-complexity-reward-fix`）。
61. **[GRPO] advantage 歸一化在 reward std≈0 時會坍縮** — `(r-mean)/std` 在 std<0.01 時使 advantage 全零；min-max 歸一化在 Rmax=Rmin 時也失效。根本原因：合成數據下 G 個 candidate reward 完全相同。**v6.0 修復**：當 `group_std < 0.01` 時改用 `np.linspace(-1, 1, G)` 排名歸一化，不依賴 reward 絕對差異。同時確保真實數據（非合成）使 reward 自然分化。
62. **[GRPO] reward 完全相同導致公式退化到單 token** — v5.9 所有 regime 收斂到單 token 公式，因為單 token 在行為一致的合成數據上 reward 不比長公式差。**v6.0 修復**：(a) 適當長度 bonus：3-8 token +0.1；(b) 新穎性 bonus：與歷史 best 不同 +0.05；(c) 使用真實數據（股票行為自然分化）。
63. **[GRPO] CPU 模式 G=4 是結構性坍縮** — G=4 太小，4 個 candidate 很快收斂到同一公式 → reward 相同 → advantage=0 → 梯度無效 → 永久退化。CPU fallback 必須 G≥16 + batch=64 + steps≤10000。
64. **FinMind pip install 在 Kaggle 失敗，改用 requests REST API** — `pip install FinMind` 在 Kaggle Python 3.12 環境中 metadata-generation-failed，根因是 `pyproject.toml` 嚴格限制 `pydantic>=1.6.1,<2.0.0`，與 Kaggle 預裝的 pydantic v2 衝突（`--no-build-isolation` 也無法繞過因為需要從 source build）。**替代方案**：用 `requests` 直接呼叫 `https://api.finmindtrade.com/api/v4/data`，無需安裝任何套件。dataset 參數：`TaiwanStockInstitutionalInvestorsBuySell`（三大法人買賣超）、`TaiwanStockMarginPurchaseShortSale`（融資融券）、`TaiwanFuturesInstitutionalInvestors`（期貨法人 OI）。注意：期貨機構 OI 回傳的 `institutional_investors` 欄位是中文，非英文。詳見 `twstock-alpha-gpt` skill 的 FinMind API 章節。
52. **pandas groupby 迴圈中 append DataFrame view 會靜默丟失數據** — `result_frames.append(g[keep_cols])` 中的 `g[keep_cols]` 回傳 view（非 copy），下一個 groupby 迭代覆蓋 `g` 後，list 中所有 frame 都指向最後一個 DataFrame。症狀：4 檔股票輸入但 pd.concat 只得最後 1 檔。單檔呼叫正常（view 不會被覆蓋），只在多檔全量呼叫時觸發。**修復**：`result_frames.append(g[keep_cols].copy())`。診斷：用 `id(frame)` 比對或 monkey-patch `pd.concat` 追蹤。此 bug 語法完全正確、不報錯——py_compile/ast.parse 無法偵測，只能用實際多檔數據執行才能發現。詳見 twstock-alpha-gpt skill references/compute-features-groupby-view-bug.md。

## Python API 使用

```python
import os
os.environ['KAGGLE_API_TOKEN'] = 'KGAT_xxxxx'

from kaggle.api.kaggle_api_extended import KaggleApi
api = KaggleApi()
api.authenticate()

# 列出自己的 notebooks
kernels = api.kernels_list(mine=True, page_size=10)

# 下載 notebook
api.kernels_pull('owner/slug', '/path/to/download', metadata=True)

# 下載 dataset
api.dataset_download_files('owner/dataset-slug', path='/path', unzip=True)
```

## 參考資料

- See `references/kernel-ops-playbook.md` for **完整實戰操作手冊** — push ipynb 流程、kernel list 查詢、即時監控腳本、停止 runtime 替代方案、log 解析方法、一鍵 debug 腳本、多 kernel 並行監控
- See `references/auth-compatibility.md` for detailed auth method testing results
- See `references/cli-commands.md` for full CLI command reference
- See `references/api-endpoint-stability.md` for known API endpoint issues (500/401/404/409 patterns, push-but-invisible syndrome, kernels output monitoring)
- See `references/grpo-kernel-debug-iteration.md` for GRPO training kernel debug history (v2-v12 bugs and fixes)
- See `references/py-to-ipynb-conversion.md` for **.py→.ipynb 轉換最佳實踐** — section-header 正則切割、行號前綴清理、cell compile 驗證、kernelspec 注入
- See `references/dataset-mount-path-depth.md` for **Kaggle dataset 掛載路徑深度問題** — 三層巢狀路徑結構 + os.walk 遞迴搜尋修復方案
- See `references/existing-ipynb-push-workflow.md` for **既有 .ipynb 直接推送工作流** — 不需 .py→.ipynb 轉換，含 FaceFusion 特化筆記
- See `references/facefusion-kaggle-model-cache.md` for **FaceFusion Kaggle 模型預裝策略** — 模型清單、大小、HF repo 分佈、Dataset 打包流程、debug 歷史
- See `references/facefusion-v3-validation.md` for **FaceFusion v3 Kaggle 驗證結果** — v2 vs v3 對比、Cell 結構、Dataset 掛載核心邏輯、metadata 設定
- See `references/kaggle-notebook-source-str-requirement.md` for **notebook source 格式關鍵陷阱** — `source` 必須是 `str` 否則 Kaggle 跳過執行（v6.19 慘痛教訓）
- See `references/facefusion-video-autoscan.md` for **FaceFusion 影片自動掃描模式** — Cell 4 修改：自動掃描 /kaggle/input/ 的 mp4/avi/mov/mkv，優先選 mp4，無需手動設 TARGET_VIDEO
- See `references/kaggle-kernel-cron-monitor.md` for **Kaggle Kernel Cron 監控模式** — 長時間 GPU 訓練自動監控、advantage collapse 檢測、regime 覆蓋率驗證、自動化修改建議流程
- See `templates/facefusion-kernel-metadata.json` for **FaceFusion Kaggle push 用 kernel-metadata.json 模板**
