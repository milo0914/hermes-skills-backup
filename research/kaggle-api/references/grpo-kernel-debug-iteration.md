# GRPO Kernel Debug Iteration (2026-06-07 ~ 2026-06-08)

## Kernel: mhhuang14/grpo-regime-aware-factor-training

### Bug Timeline

| Version | Bug | Error | Fix |
|---------|-----|-------|-----|
| v2 | .py→.ipynb cell 切割 | `IndentationError: unexpected indent` line 10 | 動態掃描 section headers 重建 notebook + compile() 驗證 |
| v4-v5 | PyTorch API 拼寫 | `AttributeError: 'total_mem'` | `.total_mem` → `.total_memory` |
| v5 | CUDA capability 不相容 | `AcceleratorError: no kernel image` on P100 (sm_60) | 加入 `get_device_capability()` 檢查 + `GRPO_FORCE_CPU` fallback |
| v6 | tensor 維度不匹配 | `RuntimeError: Tensors must have same dimensions: got 2 and 3` | `action.unsqueeze(0).unsqueeze(0)` → `action.unsqueeze(0)` |
| v8 | 零收斂 — 根因A: StackVM 隨機 (loss=0, reward=-5) | 99.8% 隨機公式無效 → advantages 全零 → 梯度消失 | 引導式解碼(StackVMState) + 恆等公式warmup + advantage全無效fallback |
| v9 | torch.cat 維度 | `RuntimeError: Tensors must have same dimensions` | `action.unsqueeze(0)` → `action.view(1, 1)` |
| v10 | 409 Conflict push | 舊 kernel 仍在執行中，push 新版被拒 | 等 kernel 完成 or 改 slug 推送 |
| v11 | torch.cat 維度再現 | `RuntimeError: Tensors must have same number of dimensions: got 2 and 1` | guided decoding loop 中 `action.unsqueeze(0)` 全面改為 `action.view(1, 1)`；同時修復 warmup 路徑 |
| v11b | 重複 class 定義 | StackVMState 在 line 153 和 line 230 各定義一次，Python 用後者但狀態不一致 | grep 確認重複，刪除舊版定義（line 228-289），檔案從 1906→1844 行 |
| v12 | 409 Conflict push | v11 修復後 push，但舊 kernel 仍在執行 | 需等 kernel 完成或 Web UI 取消後再 push |
| v13 | 零收斂 — 根因B: 特徵大小寫不匹配 | loss=-0.0000, mean_r=0.000, valid=0.0% 持續 7500+ 步，但有效率 100%（根因A已修） | zscore 前插入 `_lower_to_upper` 映射（`g.rename(columns=...)`）；feat_tensor 提取優先大寫；合成 inst/margin 數據 |
| v3.1 | 本地 ai_dig_money_core.py 整合 + Kaggle re-push | 原始 slug 舊版 log 仍顯示零收斂（INST_FLOW mean=0.0000）；新版修復需推送 | 新 slug `twse-grpo-regime-aware-alpha-factor-training-v3-1`；含 lower→upper 修復 + action.view(1,1) + TWSEDataFetcher stub + compute_features 22因子；push 成功，監控中 |
| v12 (original slug) | jupytext .ipynb 缺少 kernelspec | `ValueError: No kernel name found in notebook and no override provided` | jupytext 轉換不產生 `metadata.kernelspec`；push 後手動注入 `{"display_name":"Python 3","language":"python","name":"python3"}` |
| v12 | pandas level_0 衝突 | `ValueError: cannot insert level_0, already exists` in compute_features() | compute_features 中反覆 `g.set_index("date")` / `g.reset_index()` 在 groupby 迴圈內造成 index 衝突。用 `pd.merge(how='left')` + `reset_index(drop=True)` 重寫整個方法 |
| v13 | PyTorch 計算圖斷開 | `RuntimeError: element 0 of tensors does not require grad and does not have a grad_fn` | `ratio = torch.ones_like(log_probs_tensor)` 斷開梯度 → 改為 `ratio = 1.0 + 0.0 * log_probs_tensor`；fallback `torch.tensor(0.0)` 需 `requires_grad=True` |
| v13 | Kaggle P100 與 PyTorch 2.10 不相容 | GPU sm_60 < sm_70 minimum | 自動 CPU fallback（G=4, batch=16, steps=3000）；需 Kaggle UI 手動選 T4 才能用 GPU |
| v13 | 資料集與訓練架構不同步 | 舊 dataset 只有 7 欄 OHLCV，缺少 inst/margin/futures_oi/us_indices 4 張表 | 更新 dataset v2：5 個 CSV（ohlcv + inst + margin + futures_oi + us_indices），匹配 v3.1 的 22 因子架構 |
| v3.2-fix | Categorical logits 缺 squeeze(0) | `RuntimeError: stack expects each tensor to be equal size, but got [1] at entry 0 and [] at entry 2` | warmup/fallback logits 加 `.squeeze(0)`；stack 前加 `[lp.reshape(()) for lp in all_log_probs]` |
| v3.2-fix | result_frames 未用 keep_cols | ABSORPTION mean=14639（讀到未正規化小寫值）| `result_frames.append(g[keep_cols])` 只保留 date+stock_id+FEATURE_NAMES |
| v3.3 | push 409 slug 衝突 | metadata id 與已完成 kernel slug 衝突 | 用全新 slug `grpo-v3-3-regime-alpha-factor-training` |
| v5 | Dataset 未掛載 + PPO loss=0 | 「無 Kaggle Dataset，使用合成數據」+ loss=0.0000, clip_ratio=0%, mean_r=0.175→-0.504 | Dataset: os.walk 遞迴搜尋修復；PPO: 改用 REINFORCE |
| v5.1 | v5 兩 bug 修復版 | REINFORCE + os.walk + group_size=16 + lr_warmup_steps=500 | build_v51.py 字串替換建構法 → push 成功，RUNNING |

### v5/v5.1 Build Pattern (2026-06-09)

**v5 實測根因確認**：
- v5 log: `loss=0.0000, mean_r=0.175→-0.504, clip_ratio=0%` — PPO on-policy loss≡0 首個 Kaggle T4 實測證據
- v5 log: 「無 Kaggle Dataset，使用合成數據」— 確認 dataset 三層巢狀路徑 bug

**v5.1 建構方法（字串替換腳本）**：
迭代修復大型 Kaggle 腳本（2358行）時，不反覆 patch，改用 Python build 腳本做目標字串替換：
```python
# /tmp/build_v51.py — 3 fixes via string substitution
with open(source_v5) as f:
    code = f.read()
# Fix 1: Dataset path — os.listdir → os.walk
code = code.replace(old_flat_scan, new_os_walk_pattern)
# Fix 2: PPO → REINFORCE
code = code.replace(old_ppo_block, reinforce_loss_block)
# Fix 3: group_size=8→16, lr_warmup_steps=200→500
code = code.replace("group_size = 8", "group_size = 16")
with open(output_v51, 'w') as f:
    f.write(code)
py_compile.compile(output_v51, doraise=True)  # validate
```
優點：(a) 不觸發 patch 縮排腐蝕；(b) 可重複執行；(c) 替換內容可追溯。缺點：替換字串須唯一。

**v5.1 push 400 錯誤**：title 超過 50 字符 → `kaggle kernels push` 回 400。縮短 title 後成功。

### 根因 B 詳細診斷 (v13)

症狀：引導式解碼 + warmup 已修復根因 A，有效率 100%，但 reward 仍全部 = -5.0。

診斷步驟：
1. `kaggle kernels output` 下載 log → 確認 reward 全 = -5.0, IC=NaN
2. 本地 debug 腳本：對比 `feat_dict['RET']` (大寫 zscore) vs `feat_dict['ret']` (小寫原始)
3. 發現：大寫值全部 = 0.0000（因 zscore 找不到大寫欄位 → 設為 0），小寫值正常
4. 追蹤到 `compute_features()` 生成小寫欄位，但 `FEATURE_NAMES` 是大寫

修復過程中的縮排陷阱：
- `_lower_to_upper` 映射和 zscore 塊被 patch 插入在 for loop 外（4sp/8sp）
- 需在 for loop 內（12sp/16sp/20sp）
- 0sp 空行打斷 Python 縮排塊（ast.parse 不報錯但語意錯誤）
- 修復方式：write_file Python 腳本按行號精確修正縮排

### Key Architecture Decisions
- `machine_shape: NvidiaTeslaT4` 在 kernel-metadata.json 中指定 GPU 型號
- CPU fallback 模式: G=4, batch=16, steps=3000
- GPU 模式: G=8, batch=128, steps=20000
- `kaggle kernels status` API 持續 500，改用 `kernels output` 下載判斷完成

### Monitoring Pattern

```bash
# 方法 1：kernels output 下載 log（推薦）
KAGGLE_API_TOKEN="***" kaggle kernels output OWNER/SLUG -p /tmp/kout/

# 方法 2：輪詢檢查（每 60 秒）
while true; do
 KAGGLE_API_TOKEN="***" kaggle kernels output OWNER/SLUG -p /tmp/out/ 2>/dev/null
 if [ -f /tmp/out/*.log ]; then break; fi
 rm -rf /tmp/out; mkdir -p /tmp/out; sleep 60
done
```

### Log 解析方法

Kaggle kernel output 的 .log 檔案是 JSON 格式，每行一個 JSON 物件：
```json
{"stream_name": "stdout", "time": 15.12, "data": " GPU: Tesla T4..."}
{"stream_name": "stderr", "time": 23.81, "data": "Traceback (most recent call last):"}
```

解析 traceback 的方法：
```python
import json
with open("kernel.log") as f:
 for line in f:
  entry = json.loads(line)
  if entry.get("stream_name") == "stderr":
   print(entry["data"], end="")
```

### Notebook Build Script Pattern

```python
import json, uuid, os

with open("source.py") as f:
 py_lines = f.read().split('\n')

# 動態掃描 section headers
section_starts = [0]
for i, line in enumerate(py_lines):
 if line.startswith('# ====') and i+1 < len(py_lines) \
 and py_lines[i+1].strip().startswith('# ') \
 and not py_lines[i+1].strip().startswith('# ==='):
  section_starts.append(i)

# 分組邏輯 cells (合併小 sections)
cell_group_starts = [0, 22, 79, 141, 238, 380, 479, 562, 895]
cell_group_ends = [22, 79, 141, 238, 380, 479, 562, 895, len(py_lines)]

cells = []
for idx, start in enumerate(cell_group_starts):
 end = cell_group_ends[idx]
 lines = py_lines[start:end]
 while lines and not lines[-1].strip(): lines.pop()
 source = [l + "\n" for l in lines]
 
 # 驗證編譯
 src = ''.join(source)
 try: compile(src, f'<cell{idx}>', 'exec')
 except SyntaxError as e:
  print(f"Cell {idx}: line {e.lineno}: {e.msg}")
  raise
 
 cells.append({
  "cell_type": "code",
  "metadata": {},
  "source": source,
  "execution_count": None,
  "outputs": [],
  "id": str(uuid.uuid4())[:8]
 })
```

### v5 FinMind Real Data Integration (2026-06-09)

27. **FinMind 中文機構名稱是期貨 OI 因子為零的根因** — `taiwan_futures_institutional_investors` API 回傳中文（`外資`/`投信`/`自營商`），fetch_real_data.py v4.1 用英文比對導致 inst_net_oi 全 NaN。v4.2 修復為中文比對後，futures_oi.csv 606/606 筆全 non-zero。
28. **Kaggle dataset 靜默未掛載** — v5 kernel 的 `dataset_sources` 指定了 `mhhuang14/twstock-grpo-training-data`，但執行時 log 顯示「無 Kaggle Dataset，使用合成數據」。可能原因：dataset slug 不匹配、索引延遲、或 kernel metadata 格式問題。診斷：notebook 開頭加 `os.listdir('/kaggle/input/')` 確認。
29. **真實數據適配層需在 notebook 內** — `adapt_finmind_data()` 函數在 notebook main() 中調用，將 FinMind CSV 格式適配為訓練腳本期望的 DataFrame 格式（inst_data pivot、margin 欄位映射、futures_oi 雙格式處理、us_indices 寬長轉換）。
30. **yfinance 個別下載+延遲策略** — 批次下載多個美股指數會被限流。改為個別下載 + 3 次重試 + 指數退避（5s/10s/15s），成功率 100%。

### v4/v4.1 Unified Build (2026-06-09)

| Version | Bug | Error | Fix |
|---------|-----|-------|-----|
| v4-k1 | ipynb cell 切斷 StackVMState.execute() | KeyError: 'inst_flow' | 重建 notebook cell 切割點 |
| v4-k2 | GPU sm_60 + 無真實數據 | AcceleratorError + 14/22 因子為0 | CUDA probe try/except + 上傳 FinMind dataset |
| v4.1 | P100 CUDA probe → CPU fallback | — | 自動 CPU fallback 成功 (G=4, batch=16, 1114.9s) |
| v5 | Dataset 未掛載 + 舊版 SwiGLU | fallback 合成數據 | 待修復 dataset binding + re-push |
| v5-push | 409 Conflict | 舊版 kernel 佔用 slug | 等待或改 slug |

### 重點教訓 (2026-06-07 ~ 2026-06-16)

1. **action.view(1,1) vs unsqueeze(0)** — Categorical 取樣 action shape=[1]，接到 inp [1,seq_len] 必須 view(1,1)。所有路徑（warmup + guided decoding + normal sampling）都要一致。

---

### v6.12/v6.13 新增教訓 (2026-06-16)

27. **PyTorch pip 降級在 Kaggle 失敗 — C extension 版本不一致 (v6.12/v6.13 根因)** — v6.12/v6.13 嘗試 `pip install torch==2.6.0+cu126` 以支援 P100 (sm_60)，但 Kaggle 預裝的 `torch._C` C extension 位於系統路徑（`/usr/local/lib/python3.12/dist-packages/torch/`），pip 只替換 Python 包（`torch/nn/` 等）而**不會替換編譯好的 C extension**。導致 Python 代碼引用新版 API（如 `torch._C._dynamo.eval_frame.skip_code`），但舊版 `torch._C` 沒有此符號 → `ImportError: cannot import name 'skip_code'` 連鎖崩潰（從 `guards.py` → `variables/base.py` → `trace_rules.py` → `symbolic_convert.py` → `convert_frame.py` → `_dynamo/__init__.py` → `_compile.py` → `Adam.__init__` 觸發 dynamo → crash）。**結論：pip 降級 PyTorch 是結構性死路，絕對不可行**。

28. **GPU 分配不可控，僅能用 CUDA probe + CPU fallback (v6.11 方案為正確)** — Kaggle API `machine_shape: NvidiaTeslaT4` 和 `--accelerator GPU_T4` 完全無效，約 50% 分配到 P100。v6.11 的 CUDA probe 實測（`torch.zeros(1, device='cuda')` + 實際矩陣運算 + `synchronize()`）是**唯一可靠方案**：
   - Probe PASS → 使用 GPU
   - Probe FAIL → 設置 `GRPO_FORCE_CPU=1` → 完整 CPU fallback
   - **不可**嘗試 pip 降級、不可用 cc>=5 門檻（sm_60 通過門檻但執行失敗）

29. **CPU fallback 必須用完整 5000 steps，不可簡化模型/回測** — v6.11/v6.12/v6.13 CPU fallback 參數 `train_steps=5000, batch_size=128, group_size=64` 已是 GPU 參數簡化而來，但模型結構（d_model=64, nhead=4, nlayer=2）和回測邏輯（IC+Sharpe+MDD+Turnover）保持完整。簡化會導致「跑出結果但無意義」。CPU 訓練 4 regime 約 30 分鐘，可接受。

30. **版本號字符串必須同步更新** — v6.13 notebook 內部 `check_environment()` 仍印 `v6.12`，`output` 仍寫 `v6.12`，導致 Kaggle log 顯示錯誤版本號，干擾事後分析。每次版本發布需 grep 全檔案確認：`grep -n \"v6\\.1[23]\" notebook.ipynb`，同時更新：docstring、print 輸出、output JSON metadata。

31. **Kaggle GPU session 併發限制 2 (v6.13 確認)** — 同帳號最多 2 個 GPU session 同時執行。push 時若超限回報 `Maximum batch GPU session count of 2 reached`。即使舊 kernel 已完成（有 log），GPU slot 可能延遲釋放。解法：(a) 等 slot 釋放；(b) Web UI 手動 Cancel；(c) 用 CPU-only metadata（移除 `enable_gpu`/`machine_shape`），CPU 模式無此限制。

32. **GRPOConfig.auto_detect() 需檢查 GRPO_FORCE_CPU** — v6.12/v6.13 的 `auto_detect` 已正確檢查 `os.environ.get("GRPO_FORCE_CPU", "0") == "1"`，並在 CPU 模式保留 regime-specific `group_size`（不再強制覆蓋）。這點 v6.12 已修正，需保留。
2. **patch 後必須 grep 檢查重複定義** — 大檔案 patch 容易產生重複 class/function。用 `grep -n "^class " file.py` 確認。
3. **409 Conflict 只能等** — 沒有 CLI stop 命令，必須等 kernel 自然結束或到 Web UI 取消。
4. **kernels output 是最可靠的 debug 工具** — status API 會 500，但 output 一定會回傳 log 或 "still running"。
5. **零收斂有兩個獨立根因** — 根因 A（StackVM 無效公式）和根因 B（特徵大小寫不匹配）都會導致 reward=-5.0，但機制不同。修復 A 後有效率 100% 但信號仍為零 = 根因 B。診斷順序：(1) 確認有效率 > 0%，(2) 確認 feat_tensor 非全零。
6. **大小寫不匹配是最隱蔽的 BUG** — 語法完全正確，py_compile/ast.parse 無法偵測。數據靜默為零。必須用實際數據執行並對比大寫/小寫欄位值才能發現。
7. **0sp 空行打斷縮排塊** — Python 允許 0sp 空行在縮排塊內，但若空行後的程式碼縮排等級不正確，Python 解析器會將其視為跳出迴圈/class。ast.parse 不一定報錯（取決於後續程式碼結構），但語意完全錯誤。
8. **大段代碼插入用 write_file Python 腳本，不用 patch** — 超過 20 行的新 function/class 插入，patch 幾乎必腐蝕縮排。正確做法：write_file 一個 Python 腳本，讀取源文件、按行號插入新代碼塊、寫回文件、py_compile 驗證。详见 twstock-alpha-gpt skill references/compute-features-v31-implementation.md。
9. **Kaggle kernel 重新推送用新 slug** — 當舊 slug 仍在執行或 log 需保留對照時，用新 slug 推送修復版（如 `twse-grpo-regime-aware-alpha-factor-training-v3-1`）。舊 slug 的 output/log 仍可下載對照。

### v12-v14 新增教訓 (2026-06-08)

10. **jupytext 轉換後必須注入 kernelspec** — `jupytext source.py --to ipynb` 不產生 `metadata.kernelspec`，Kaggle papermill 拋 `ValueError: No kernel name found`。每次轉換後用 Python 注入 `{"display_name":"Python 3","language":"python","name":"python3"}`。
11. **絕對不要用 `--pipe` 參數** — `jupytext ... --pipe true` 會把 notebook 清空為空殼（pipe 給外部命令處理，`true` 無 output → 空內容回寫）。只用 `jupytext source.py --to ipynb -o out.ipynb`。
12. **groupby 迴圈內禁止反覆 set_index/reset_index** — 這是 pandas 的經典陷阱。groupby 後 g 的 index 含 group key，反覆 reset 會累積 level_0/level_1 衝突。正確模式：(a) groupby 後立即 `g = g.reset_index(drop=True)` 清理 index；(b) 用 `pd.merge(how='left', on=join_cols)` 取代 set_index/reindex；(c) 所有 merge 操作基於欄位名而非 index。
13. **PyTorch PPO ratio 初始化必須保持梯度** — `torch.ones_like(x)` 創建無 grad_fn 的葉節點，斷開計算圖。用 `1.0 + 0.0 * x` 或 `torch.exp(x - x.detach())` 代替，值為 1.0 但保持梯度連接。
14. **訓練資料集必須與模型架構同步** — 擴展因子詞彙（16→22）後，舊 dataset（只有 OHLCV 7 欄）不包含新因子所需的外部資料表（inst/margin/futures_oi/us_indices）。notebook fallback 到合成數據可跑通，但正式訓練需要真實數據。每次架構更新後檢查 dataset 欄位匹配。
15. **Kaggle GPU 分配不可控** — API push 只能指定 `enable_gpu: true`，無法選擇 GPU 型號。可能分配到 P100（sm_60，PyTorch 2.10 不支援）或 T4（sm_75，正常）。需在 notebook 開頭加 GPU capability 檢查 + CPU fallback 邏輯。
16. **`1.0 + 0.0 * x` 不是有效的梯度保持寫法 (v14 零收斂根因C)** — v13 將 `torch.ones_like(log_probs)` 修復為 `ratio = 1.0 + 0.0 * log_probs_tensor`，但 v14 訓練 7500+ 步仍零收斂（loss=-0.0000, mean_r=0.000, best_r=-5.000）。根因：`d(1.0+0.0*x)/dx = 0.0`，ratio 的梯度恆為零。這比 `ones_like` 更隱蔽——不拋 RuntimeError，計算圖視覺上連接，但梯度完全消亡。正確修復：`ratio = torch.exp(log_probs - log_probs.detach())` → ratio=1.0, d(ratio)/d(log_pi)=1.0。同時 warmup 階段 `torch.tensor(0.0, requires_grad=True)` 也需改為模型 forward pass 取得 log_prob。
17. **FormulaDecoder 必須使用 ALL_FEATURE_NAMES (v14)** — v3.1 擴展因子至 22 個，但 Kaggle notebook 的 FormulaDecoder 仍使用舊的 `TW_FEATURE_NAMES`（16 因子），token 16-21 被誤判為 operator 而非 feature，導致反編譯錯誤。每次擴展因子詞彙後，必須在 FormulaDecoder.decode() 中同步更新為 `ALL_FEATURE_NAMES`。
18. **Kaggle GPU session 並行上限 2 (v16)** — 同一帳號最多 2 個 GPU session 同時執行。push 時若超限回報 `Maximum batch GPU session count of 2 reached`。CPU-only metadata（移除 enable_gpu/machine_shape）不受此限。舊 session 即使已完成也可能延遲釋放 GPU slot。
19. **push 不自動執行 (v16)** — `kaggle kernels push` 只上傳新版本。若需 push 後自動執行，在 `kernel-metadata.json` 加 `"is_idle_no_idle": true`。否則需到 Web UI 手動按 "Run"。
20. **kernels output 空目錄 ≠ 失敗** — 下載後目錄為空可能是 kernel 尚未開始執行（佇列中）。有 .log = 已開始/完成，無 .log = 未啟動。
21. **合成數據無 alpha 信號 = 零收斂 (v3.3 根因D)** — 即使修復了所有梯度 bug，若合成數據的報酬是純隨機噪聲（與特徵無因果關係），GRPO 仍無法學到有效策略。reward=0.639 只是噪聲相關的隨機偏誤。修復：注入 alpha 信號（每檔標的 4 個特徵加權組合 + AR(1) 自相關），讓 `ret = trend + scale * alpha_component + noise`。
22. **`torch.tensor(0.0, requires_grad=True)` 是 leaf tensor，梯度無法回傳 (v3.3 根因E)** — warmup/fallback 路徑中用此寫法取得 log_prob，但 leaf tensor 沒有 grad_fn 連接模型參數，backward 時梯度停在該節點不回傳。修復：warmup 和 fallback 都必須通過模型 forward pass 取得 `Categorical.log_prob()` 返回值，確保計算圖完整。
23. **GitHub 即時監控 Kaggle 訓練** — 在 notebook 中加入 `GitHubLogPusher` 類別，每 500 步透過 GitHub Contents API 推送 `kaggle-logs/{regime}/latest_metrics.json` 和 `progress.txt` 到 `milo0914/AlphaGPT` repo。需要在 Kaggle Secrets 中設定 `GITHUB_TOKEN`。推送路徑：`kaggle-logs/{regime}/latest_metrics.json`（最新指標）、`kaggle-logs/{regime}/progress.txt`（單行摘要）、`kaggle-logs/{regime}/final_result.json`（最終結果）、`kaggle-logs/{regime}/training_history.json`（歷史曲線）。
24. **Categorical logits 缺 squeeze(0) 導致 torch.stack shape mismatch (v3.2-fix→v3.3)** — model forward 回傳 `(B=1, T, vocab)` logits。主迴圈正確使用 `logits[:, -1, :].squeeze(0)` → `(vocab,)` → log_prob scalar `[]`。但 warmup 和 fallback 路徑遺漏 `.squeeze(0)`，傳入 `(1, vocab)` 2D logits → Categorical 回傳 log_prob shape `[1]`。`torch.stack(all_log_probs)` 因 `[1]` vs `[]` 不一致拋 RuntimeError。修復：(a) warmup/fallback 加 `.squeeze(0)`；(b) stack 前加 `[lp.reshape(()) for lp in all_log_probs]` 保險。`reshape(())` 比 `.squeeze()` 更可靠（squeeze 對 scalar 是 no-op，reshape 強制為 0-dim）。slug: `mhhuang14/grpo-v3-3-regime-alpha-factor-training`。
25. **result_frames.append(g) 需 keep_cols 過濾 (v3.3)** — compute_features 中的 `result_frames.append(g)` 保留所有欄位（含未正規化小寫版本），診斷時 ABSORPTION mean=14639 而非 ~0（讀到原始值）。修復：`keep_cols = ["date", "stock_id"] + list(FEATURE_NAMES)`，`result_frames.append(g[keep_cols])`。本地版已有此邏輯，Kaggle 版 v3.3 補上。
26. **push 409 也可能是 slug 與已完成 kernel 衝突 (v3.3)** — 不只是「前一版仍在執行」，也可能是 metadata 的 id/slug 與帳號下已存在的 kernel 衝突。解法：用全新 title/slug（如 `grpo-v3-3-regime-alpha-factor-training`），避免與 v3.1/v3.2/v3.2-fix 重複。
