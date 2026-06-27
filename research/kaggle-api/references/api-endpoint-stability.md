# Kaggle API 端點穩定性記錄

測試日期：2026-06-07 ~ 2026-06-08

## 已知 API 端點問題

### 1. `kernels status` — 500 Server Error (間歇性)

- **端點**: `https://api.kaggle.com/v1/kernels.KernelsApiService/GetKernelSessionStatus`
- **症狀**: 對所有 kernel（包括正常運作的）返回 500
- **不影響**: `kernels list`, `kernels push`, `datasets create` 等其他端點
- **推測**: Kaggle v1 gRPC endpoint 間歇性故障
- **替代方案**: 網頁查看、`kernels list` lastRunTime 推斷、`kernels output` 下載 log

### 2. `kernels list` REST API — 400 Bad Request

- **端點**: `https://www.kaggle.com/api/v1/kernels/list`
- **症狀**: 直接 curl 調用返回 400
- **原因**: 可能需要特定查詢參數格式或 Kaggle 內部路由問題

### 3. Python API `kernels_list(search=...)` — 401 Unauthorized

- **端點**: `kernels.KernelsApiService/ListKernels`
- **症狀**: 即使 CLI 認證正常，Python API 的 `kernels_list(search='grpo', mine=True)` 返回 401
- **原因**: gRPC 端點與 REST 端點使用不同的認證機制
- **注意**: `kaggle kernels list -m` CLI 命令正常，但 Python API 的同功能調用可能失敗

### 4. "Push 成功但 Kernel 消失"

- **症狀**: `kaggle kernels push` 回報 "Kernel version N successfully pushed" 但 kernel 不出現在列表
- **推送次數**: 7 次（grpo-regime-aware-factor-training）+ 1 次（grpo-test-kernel）
- **URL**: `https://www.kaggle.com/code/mhhuang14/grpo-regime-aware-factor-training` → 404
- **kernels list --mine**: 不含新 kernel
- **狀態**: 未解決，可能是帳號限制或 Kaggle 索引延遲

### 5. `kernels push` — 409 Conflict (2026-06-08 確認)

- **端點**: `https://api.kaggle.com/v1/kernels.KernelsApiService/SaveKernel`
- **症狀**: 當同一 slug 的前一版 kernel 仍在執行中時，push 新版本返回 `409 Client Error: Conflict`
- **觸發條件**: 上一次 push 的 kernel 尚未完成（status=running 或 queue）
- **影響**: 無法推送新版本修復 bug，必須等待
- **CLI 無 stop 命令**: `kaggle kernels stop` 不存在
- **解法**:
  - (a) 等 kernel 執行完成（用 `kernels output` 監控："Kernel is still running" → 完成 → 再 push）
  - (b) 到 Kaggle Web UI 手動取消（Code → Your Work → 該 kernel → Cancel Run）
  - (c) 改 title/slug 推送新版本（不推薦，因舊 slug 仍殘留）
- **預防**: push 前先用 `kernels output` 確認前一版已完成

### 6. `kernels output` — 最可靠的狀態監控端點

- **端點**: `kaggle kernels output OWNER/SLUG -p /path`
- **行為矩陣**:
  | Kernel 狀態 | CLI 回傳 | 成功率 |
  |------------|---------|--------|
  | 仍在執行 | "Kernel is still running"（不下載檔案） | 100% |
  | 已完成（成功） | 下載 .log + output 檔案到 -p 路徑 | 100% |
  | 已完成（失敗） | 下載 .log（含 stderr traceback） | 100% |
  | 不存在 | 錯誤訊息 | 100% |
- **對比 `kernels status`**: status API 常回 500，output 端點始終穩定
- **.log 格式**: 每行一個 JSON 物件，含 stream_name（stdout/stderr）、time、data 欄位

### 7. `kernels push` — GPU Session 限制 (2026-06-08 確認)

- **端點**: `kaggle kernels push -p /path`
- **症狀**: 返回 `429 Too Many Requests` 或 inline 錯誤 `Maximum batch GPU session count of 2 reached`
- **觸發條件**: 同一帳號已有 2 個 GPU kernel 在執行/佇列中
- **影響**: 新 push 的 GPU kernel 不會啟動，但不影響 CPU kernel
- **解法**:
  - (a) 等 GPU session 完成（用 `kernels output` 監控）
  - (b) 到 Kaggle Web UI 手動 Cancel Run 釋放 GPU slot
  - (c) 改用 CPU-only metadata（移除 `enable_gpu` 和 `machine_shape`）
- **注意**: 舊 session 即使已有 output（執行完畢），GPU slot 可能延遲釋放

### 8. `kernels push` — push 不自動執行 (2026-06-08 確認)

- **症狀**: push 成功但 kernel 進入 idle 狀態，不自動開始執行
- **解法**: 在 `kernel-metadata.json` 中加入 `"is_idle_no_idle": true`，或到 Web UI 手動按 "Run"
- **CPU-only push**: 不加此欄位也可能進入 idle，需確認
