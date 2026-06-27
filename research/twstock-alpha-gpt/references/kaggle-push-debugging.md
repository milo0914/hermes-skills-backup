# Kaggle Kernel Push 除錯記錄 (2026-06-07 ~ 2026-06-08)

## 問題

將 `grpo_regime_training_kaggle.py`（46KB）推送到 Kaggle GPU T4 執行，遭遇一連串問題。

## 發現的 Bug 序列

### Bug 1: IndentationError at Cell 1, Line 10

**症狀**: Kaggle 日誌顯示 `IndentationError: unexpected indent` at `In [1]`, line 10

**根因**: 原始 `.py` 檔案包含行號前綴格式（如 `10|stack.append(...)`），轉換為 `.ipynb` 時這些前綴被直接放入 cell source，導致 Python 直譯器遇到 `10|` 開頭的行而報縮排錯誤。

**修正**: 去除行號前綴，確保 cell source 只包含純 Python 程式碼。

### Bug 2: kernel_type 不匹配

**症狀**: `kernel-metadata.json` 設定 `"kernel_type": "script"` 但 `code_file` 是 `.ipynb`

**根因**: 初版推送用 script 模式，但 Kaggle 內部用 papermill 執行 notebook 格式轉換，兩者衝突。

**修正**: 統一使用 `"kernel_type": "notebook"` + `.ipynb` code_file。

### Bug 3: Cell 切割切斷 class 定義

**症狀**: 原始 notebook 有 46 個 cell，許多在 `# ===` section marker 處切割，導致 class definition 被切斷為多個 cell。

**修正**: 改為少量大 cell（4 cell 版本），按功能模塊切割：imports+constants → all classes → main block。

### Bug 4: "Push 成功但 Kernel 消失"

**症狀**: `kaggle kernels push` 回報成功但 kernel 不在列表中、網頁 404。

**狀態**: 後續版本已成功推送並可見。根因可能是 Kaggle 索引延遲或 slug 衝突。

### Bug 5: `kernels status` 500 Server Error

**根因**: Kaggle v1 gRPC endpoint (`GetKernelSessionStatus`) 間歇性故障。替代方案：`kernels output` 更可靠。

### Bug 6: pandas level_0 衝突 (2026-06-08 發現)

**症狀**: v3-1 script kernel 執行失敗：`ValueError: cannot insert level_0, already exists`

**根因**: compute_features 中 `set_index('date').reindex(g.index).reset_index()` 在 groupby 迴圈內反覆執行，group key 殘留導致 level_0 衝突。

**修正**: 4 處全部改為 `pd.merge(how='left', on=join_cols)` 模式。詳見 references/compute-features-v32-merge-fix.md

### Bug 7: GPU session 並行上限 (2026-06-08 發現)

**症狀**: `kaggle kernels push` 回報 `Maximum batch GPU session count of 2 reached`

**根因**: Kaggle 免費帳號最多 2 個同時 GPU session。舊 kernel (v3-1) 雖已執行完畢但 GPU slot 可能延遲釋放。

**修正**: 改用 CPU-only metadata（移除 `enable_gpu` 和 `machine_shape`），CPU 模式不受 GPU session 限制。或到 Web UI 手動 Cancel Run 釋放 slot。

### Bug 8: P100 (sm_60) 與 PyTorch 2.10 不相容 (2026-06-08 確認)

**症狀**: v3-1 kernel 被分配 P100，CUDA op 拋 runtime error，fallback 到 CPU。

**根因**: PyTorch 2.10+cu128 只支援 sm_70+。P100 是 sm_60。

**修正**: Notebook 內建 `torch.cuda.get_device_capability(0)` 檢查 + `GRPO_FORCE_CPU=1` fallback。若需 GPU，在 Kaggle UI 手動選 T4。

## kernel 版本歷史

| 版本 | 模式 | 狀態 | 失敗原因 |
|------|------|------|----------|
| v2-v12 | notebook | ❌ 各種 bug | IndentationError, kernelspec, cell切割 |
| v3-1 (script) | GPU P100 | ❌ 失敗 | sm_60 不相容 + level_0 衝突 |
| v14 (notebook) | GPU T4 | ❌ 未執行 | GPU session 2/2 已滿 |
| v16 (notebook) | CPU-only | 🔄 監控中 | push 成功，cron 每 10 分鐘檢查 |

## 本地驗證結果

在本地 CPU 環境（無 PyTorch）驗證了以下模組：

| 模組 | 結果 |
|------|------|
| 合成數據生成 | ✅ |
| 特徵工程 | ✅ (22, N) tensor |
| StackVM 公式執行 | ✅ |
| GRPOConfig | ✅ auto_detect → cpu |
| RewardCalculator | ✅ |
| FormulaDecoder | ✅ ALL_FEATURE_NAMES 22 因子映射正確 |
| compute_features merge 模式 | ✅ 4 處 set_index 全移除 |
| PyTorch training | ❌ 本地無 torch，Kaggle 執行 |
