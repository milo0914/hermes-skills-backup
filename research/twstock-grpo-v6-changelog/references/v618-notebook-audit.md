# TWStock GRPO v6.18 Notebook 逐行審計報告

## 審計範圍
- 檔案: `grpo-v6-18-composite-score-cpu-single.ipynb` (92,209 bytes)
- Kernel slug: `mhhuang14/grpo-v6-18-composite-score-cpu-single`
- 審計日期: 2026-06-18

## 審計方法
將 notebook 轉為 JSON，提取程式碼 cell (`cells[1].source`)，逐行搜尋關鍵變數與函式呼叫，比對 v6.18 Eng Plan 預期修改。

## 審計結果摘要

### ✅ 正確實作的部分

| 項目 | 行號 | Eng Plan 預期 | 實際 | 判定 |
|------|------|--------------|------|------|
| best_val_ic 獨立追蹤 | L1499-1504 | 每 200 步，不限 warmup | `if step % 200 == 0` 在 early stop warmup 之外 | ✅ |
| operator_bonus 調降 | L702 | 2.0→0.5 | `operator_bonus: float = 0.5` | ✅ |
| early_stop_warmup 調降 | L700 | 3000→1000 | `early_stop_warmup: int = 1000` | ✅ |
| CUDA probe FAIL→CPU | L52-54 | 不安裝 cu118 | `"直接使用 CPU 模式 (略過 cu118 安裝)"` | ✅ |
| CPU 模式標記 | L58-60 | GRPO_FORCE_CPU=1 | `os.environ["GRPO_FORCE_CPU"] = "1"` | ✅ |
| Composite score 存在 | L1431 | composite = train_ic*0.3 + max(val_ic,0)*0.7 | `_composite = _best_train_ic * 0.3 + max(_best_val_ic, 0.0) * 0.7` | ✅ |
| Operator tiny bonus | L1434-1435 | +0.05 if n_ops>0 | `if _best_n_ops > 0: _composite += 0.05` | ✅ |
| best_composite 停滯重種 | L1476-1485 | 每 1000 步檢查 | `if (step > 0 and step % 1000 == 0 and step - best_step >= 1000)` | ✅ |

### ❌ 半實作或全未實作的部分

#### AUDIT-1 (P0): best_idx 仍為 reward-argmax

- **行號**: L951
- **問題**: `"best_idx": int(np.argmax(rewards))` — 回傳的是 GRPO reward 最高的 index，非 composite 最高的
- **衝擊**: Composite score 的「選擇」建立在 reward-argmax 之上，從根源限制了其有效性

#### AUDIT-2 (P0): Composite score 只算 reward-argmax 那一個 formula

- **行號**: L1427-1439
- **問題**: 
  ```python
  best_idx = result["best_idx"]  # ← reward-argmax
  _best_train_ic = float(train_ic[best_idx])     # 只看 reward 最高的
  _best_val_ic = float(val_ic[best_idx])          # 只看 reward 最高的
  _composite = ...  # 只算 reward 最高那一個
  if _composite > best_composite:
      best_formula = all_tokens[best_idx]  # ← 選的仍是 reward 最高的
  ```
- **衝擊**: Group 中可能有 formula B (val_IC=0.08, reward=-2.0) 和 formula A (val_IC=0.01, reward=1.5)。`best_idx=A`，所以 composite 只算 A。B 的 composite 更高但永遠不會被考慮。
- **Eng Plan 預期**: Composite score 應遍歷全 group，取 composite-argmax

#### AUDIT-3 (P0): best_val_ic 追蹤引用 reward-based best_idx

- **行號**: L1499-1504
- **問題**:
  ```python
  # 【v6.18 P0】best_val_ic 獨立追蹤
  if val_ic is not None and len(val_ic) > 0:
      _current_val_ic = float(np.max(val_ic))  # 用 max(val_ic) - 取 group 最高
  ```
  雖然這裡用了 `np.max(val_ic)` 而非 `best_idx`，但 L1522 印出的 debug 資訊：
  ```python
  best_toks = all_tokens[result["best_idx"]]  # ← 仍是 reward 最高的
  best_n_ops = sum(1 for t in best_toks if t >= N_FEATURES)
  ```
- **衝擊**: 報表中 `best_ops`、`best_len`、`val_ic_best` 可能對應到不同公式，不一致

#### AUDIT-4 (P0): Early stop has_exploration 引用 reward-based best

- **行號**: L1449
- **問題**:
  ```python
  has_exploration = best_n_ops > 0 and len(best_toks) > 2
  ```
  `best_n_ops` 和 `best_toks` 來自 `result["best_idx"]`（reward-argmax）。當 reward 最高的永遠是單變數公式時：
  - `has_exploration = False`（因為 best_n_ops=0）
  - `patience_counter` 永遠不增加
  - **Early stop 永遠不會觸發**
  - 結果：跑完 6000 步但最佳公式始終是 step 0 的單變數
- **Eng Plan 預期**: has_exploration 應基於 composite-best 的 n_ops 和 len

#### AUDIT-5 (P1): Re-seed 注入 3-token 公式（長度 < min_formula_len=4）

- **行號**: L1470-1497 (3 處 re-seed)
- **問題**:
  ```python
  all_tokens[rg] = [int(tf[rg % N_FEATURES]),       # feature 1
                    int(tf[(rg+1) % N_FEATURES]),     # feature 2
                    int(np.random.choice(OPERATORS))]  # operator
  ```
  長度 = 3 < min_formula_len=4 → 被 `short_formula_penalty=5.0 * (4-3) = 5.0` 扣分 → reward 極低 → 永遠不被選為 best → 探索無效
- **衝擊**: 所有 re-seed 注入的 operator 公式都是「負資產」

#### AUDIT-6 (P1): CPU 模式仍訓練 4 regime

- **行號**: L1710-1718
- **問題**:
  ```python
  if _force_cpu or not _gpu_avail:
      print("CPU 模式 → 訓練所有 4 個 regime")
  ```
  CPU 模式只訓練 1 regime 是 v6.18 Eng Plan 的關鍵設計（節省時間），但程式碼仍走 v6.12 的 4 regime 全訓路徑。
- **實際表現**: Output 只含 mid_cap_tech，可能因 Kaggle 6h timeout 只跑完 1 個

#### AUDIT-7 (P1): RegimeConfig 覆蓋 group_size

- **行號**: L243, L1177-1181, L1719
- **問題**: v6.18 Eng Plan 要求 CPU `group_size=32`，但：
  - `RegimeConfig.training_params[MID_CAP_TECH]["group_size"] = 24`
  - `L1181: self.config.group_size = max(self.config.group_size, 16)`
  - `L1177: self.config.group_size = regime_plan["group_size"]` → 覆蓋成 24
  - Config output 證實：`group_size=24`
- **衝擊**: 違反 Eng Plan 設計，CPU 訓練速度慢 33%

#### AUDIT-8 (P1): Val_IC penalty 只懲罰負值不獎勵正值

- **行號**: L869-874
- **問題**:
  ```python
  val_penalty = abs(v_ic) * 10.0 if v_ic < 0 else 0.0
  ```
  - val_ic = 0.109 → 無獎勵（0）
  - val_ic = -0.01 → 懲罰 0.1
  - val_ic = 0.001 → 無獎勵（0），但比 val_ic=-0.01 的懲罰還弱
- **衝擊**: GRPO reward 無法區分 val_ic=0 和 val_ic=0.1 的公式

## 修正優先級

| 優先級 | Bug ID | 衝擊 | 預估工時 |
|--------|--------|------|---------|
| P0 | AUDIT-1,2 | best_formula 永遠選不到真正好的公式 | 30 min |
| P0 | AUDIT-4 | Early stop 永不觸發，浪費訓練時間 | 10 min |
| P1 | AUDIT-5 | Re-seed 探索無效 | 20 min |
| P1 | AUDIT-6 | CPU 浪費 4x 時間 | 10 min |
| P1 | AUDIT-7 | group_size 錯配 24 vs 32 | 5 min |
| P1 | AUDIT-8 | val_IC 正值無獎勵 | 5 min |
| P2 | META | 版號錯誤、title 殘留 | 5 min |

## v6.18 半實作根因分析

v6.18 Eng Plan 在設計層完全正確（composite score、operator bonus 調降、val_IC 獨立追蹤），但 notebook 實作時出現了「設計意圖」與「程式碼」之間的 **half-implementation gap**：

1. **認知落差**: Eng Plan 寫「best_formula 改用 composite score 選擇」，開發者理解為「在選擇環節加入 composite 計算」，但未意識到需要「遍歷全 group」— 只改了 `if reward > best_reward → if composite > best_composite`，卻忘了 `best_idx` 仍是 reward-argmax。
2. **遺留代碼**: v6.18 notebook 從 v6.16 notebook 複製修改，v6.12 的 CPU 4-regime 邏輯（L1712）未被 v6.18 Eng Plan 覆蓋。
3. **Re-seed 長度**: 3 處 re-seed 代碼完全相同，從 v6.16 到 v6.18 均未被審計到 `min_formula_len=4` 的約束。
4. **版號殘留**: 所有 version 字串（L1753, L1764）和 metadata.title 都未更新，暗示 notebook 是逐行手動修改而非整體重構。

## v6.19 需要全面重寫的區塊

| 區塊 | 行號範圍 | 重寫方式 |
|------|---------|---------|
| Composite score 選擇 | L1425-1441 | 完整替換為全遍歷邏輯 |
| Early stop 條件 | L1445-1460 | 修改 has_exploration 引用 |
| Re-seed 3 處 | L1470-1497 | 全部替換為 _make_reseed_formula 呼叫 |
| Closed-loop 最佳 composite 停滯 | L1476-1497 | 修改觸發邏輯 |
| CPU regime 過濾 | L1710-1718 | 改為只保留 mid_cap_tech |
| group_size 硬編碼 | L1177-L1181 | 加入 CPU 模式判斷 |
| Val_IC reward | L869-874 | 加入正值獎勵 |
| Debug print | L1500-1527 | 新增 JSONL log |
| version/title | 全 notebook | 全面清理 |
| GRPOConfig | L680-735 | 新增 12+ 參數 |