# 推送既有 .ipynb 到 Kaggle 的工作流程

## 適用場景
已有 .ipynb 檔案（非 .py），需直接推送至 Kaggle 執行。
常見於：看板任務產出、Colab notebook 移植、開源 repo 的 notebook 改寫。

## 操作步驟

### 1. 準備推送目錄

```bash
mkdir -p /tmp/kaggle-push
cp /path/to/existing.ipynb /tmp/kaggle-push/
```

### 2. 建立 kernel-metadata.json

```json
{
 "id": "username/kernel-slug",
 "title": "Kernel Display Title",
 "code_file": "existing.ipynb",
 "language": "python",
 "kernel_type": "notebook",
 "is_private": "true",
 "enable_gpu": "true",
 "enable_internet": "true",
 "dataset_sources": [],
 "machine_shape": "NvidiaTeslaT4"
}
```

關鍵：
- `code_file` 必須與實際檔名完全一致（含副檔名）
- `id` 格式為 `username/slug`，slug 由 title 自動推導（小寫、空格→連字號）
- title 最長 50 字符
- `is_private` / `enable_gpu` 建議用字串 "true"（非布林值）

### 3. 推送

```bash
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels push -p /tmp/kaggle-push/
```

### 4. 監控

```bash
# 方法 A：kernels output（推薦）
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels output OWNER/SLUG -p /tmp/kout/

# 方法 B：kernels status（可能 500）
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels status OWNER/SLUG
```

### 5. 下載執行結果

```bash
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels output OWNER/SLUG -p /tmp/kout/
```

### 6. 拉回原始碼（注意：不含 cell outputs）

```bash
KAGGLE_API_TOKEN="KGAT_xxx" kaggle kernels pull OWNER/SLUG -p /tmp/kpull/
```

**重要**：`kaggle kernels pull` 取回的 .ipynb 不包含 cell outputs。
Kaggle 只回傳 code cells，執行結果需透過 `kernels output` 取得。
**重要**：pull 回的 `kernel-metadata.json` 會遺失 GPU/網路設定，切勿直接重新 push。

## 輸出 log 格式差異

### 執行期間 vs 完成後的 output

| 狀態 | `kernels output` 行為 | log 內容 |
|------|----------------------|----------|
| 仍在執行 | 回傳 "Kernel is still running" | N/A |
| 已完成 | 下載 .log + 產出檔案 | JSON 格式（每行一個 entry） |
| 執行失敗 | 下載 .log（含 stderr traceback） | JSON 格式 |

### log 解析

```python
import json

with open("/tmp/kout/kernel-slug.log") as f:
 for line in f:
  entry = json.loads(line)
  if entry.get("stream_name") == "stdout":
   print(entry["data"], end="")
  elif entry.get("stream_name") == "stderr":
   print(f"[STDERR] {entry['data']}", end="")
```

## 已知問題

1. **409 Conflict** — 同 slug 前版仍在執行，或 slug 與已完成 kernel 衝突
 - 解法：用新 title/slug，或等前版完成
2. **Title/slug 不匹配警告** — 僅警告不阻擋，可正常推送
3. **Push 成功但 kernel 消失** — Kaggle 索引延遲，等 5 分鐘再查
4. **GPU session 並行上限 2** — 超過需等舊 session 完成
5. **kernels pull 不含 outputs** — 只有 code cells，需用 kernels output 取執行結果
6. **kernels pull 回傳的 metadata 遺失 GPU 設定** — 需手動修正 enable_gpu/enable_internet/machine_shape

## FaceFusion 特化筆記

FaceFusion 在 Kaggle T4 上需注意：
- 使用 `headless-run` 模式（無 GUI）
- 設 `CONDA_READY=1` 繞過 conda 安裝步驟
- `OMP_NUM_THREADS=1` 避免 OpenMP 衝突
- 使用 `inswapper_128_fp16` 降低 VRAM 需求（T4 16GB）
- **必須使用 Dataset 預裝模型** — 不依賴 HuggingFace 下載
- **必須使用真人照片** — placeholder 無法觸發 face swap
- 安裝含不必要 gradio 依賴（可精簡，SKIP_GRADIO=True）
- numba-cuda 版本衝突警告不影響執行

### FaceFusion Dataset 預裝模型（v4 驗證通過 2026-06-10）

**問題**：FaceFusion 懶載入模型，首次執行需下載 ~1.6 GB。Kaggle watchdog ~60s 無 stdout 後 CANCEL kernel。

**解法**：
1. 預包 Kaggle Dataset `mhhuang14/facefusion-models-330`（26 files, 1,603 MB, private）
2. 新建 `mhhuang14/facefusion-test-images`（source.jpg + target.jpg, private）
3. Notebook 開頭 cp 模型到 `facefusion/.assets/models/`，載入真人照片

**v4 驗證結果**：
- 模型載入：25.9s，26 個模型全部從 Dataset 載入
- HuggingFace 下載：0（完全離線）
- 真人換臉：成功，result.jpg (12.6 KB, 6.32 秒)
- 總執行時間：79.7s，全部 10 個 cell DONE
- 掛載路徑：`/kaggle/input/datasets/mhhuang14/facefusion-models-330`（三層巢狀）
- 推送 metadata 需加兩個 dataset_sources
- Notebook 中移除 `--download-providers huggingface`

詳見 `references/facefusion-kaggle-model-cache.md` 和 `references/facefusion-v3-validation.md`

### Pull-Modify-Push 單 Cell 修改循環

修改既有 Kaggle notebook 的單一 cell 流程：

1. `kaggle kernels pull OWNER/SLUG -p /tmp/pull/ -m` 取回 ipynb + metadata
2. 本地用 Python json 讀取 .ipynb，定位目標 cell（按 index 或內容關鍵字搜尋）
3. 修改 cell source（注意格式：每行末加 `\n`，最後一行不加）
4. **修正 metadata**（pitfall #57）：pull 回的 `enable_gpu`/`enable_internet`/`machine_shape` 會遺失，必須手動改回
5. 複製修改後的 ipynb 至 pull 目錄覆蓋原檔
6. `kaggle kernels push -p /tmp/pull/` 推送

ipynb cell source 格式：
```python
lines = new_source.split('\n')
cell['source'] = [line + '\n' for line in lines[:-1]] + [lines[-1]]
```
