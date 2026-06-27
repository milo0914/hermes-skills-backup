# v6.17 Fixed: PyTorch 2.0.1+cu118 相容性修復完整記錄

**日期**: 2026-06-17  
**Kernel**: `mhhuang14/twstock-grpo-v6-17-fixed-val-ic-reward`  
**基於**: v6.17 訓練失敗 (cu118 timeout + functorch 錯誤)

---

## 失敗現象

### 1. cu118 安裝超時 (120s)
```
[v6.17] CUDA probe: FAIL — 嘗試安裝 cu118...
[v6.17] cu118 install: ERROR (Command '['/usr/bin/python3', '-m', 'pip', 'install', 'torch==2.2.0+cu118', '--quiet', '-f', 'https://download.pytorch.org/whl/torch_stable.html']' timed out after 119.99997649 seconds) → CPU fallback
```

### 2. PyTorch 2.10 functorch 屬性錯誤
```
AttributeError: module 'torch._functorch.eager_transforms' has no attribute 'grad_and_value'
```
堆疊追蹤顯示在 `torch.optim.Adam()` 初始化時，經由 `torch._dynamo` → `torch._functorch.deprecated` → 找不到 `grad_and_value` 崩潰。

---

## 根因分析

### PyTorch 版本時間線與 sm_60 支援

| 版本 | 發布時間 | CUDA | sm_60 支援 | functorch 狀態 | 狀態 |
|------|---------|------|------------|----------------|------|
| 2.0.1 | 2023-04 | 11.8 | ✅ | 穩定，無 dynamo 強制編譯 | ✅ 可用 |
| 2.1.0 | 2023-10 | 11.8 | ✅ | **已從 index 移除** | ❌ 不可用 |
| 2.2.0 | 2024-01 | 11.8 | ✅ | 有 dynamo，大檔案 | ⚠️ timeout 風險 |
| 2.10.0 | 2024-10 | 12.8 | ❌ (sm_70+) | 重組，grad_and_value 移除 | ❌ 不支援 P100 |

**關鍵發現**: Kaggle 分配的 GPU 約 50% 是 Tesla P100 (sm_60)，PyTorch 2.10+ 預設安裝的 cu128 **不支援 sm_60**。v6.14+ 的 CUDA probe 會檢測到失敗並嘗試安裝 cu118 版本。

---

## 修復方案

### 1. 使用 PyTorch 2.0.1+cu118 (首選)
```python
subprocess.run([
    sys.executable, "-m", "pip", "install",
    "torch==2.0.1+cu118",
    "torchvision==0.15.2+cu118",
    "torchaudio==2.0.2+cu118",
    "--quiet",
    "-f", "https://download.pytorch.org/whl/torch_stable.html"
], check=True, timeout=300)
```
優點: 支援 sm_60、無 functorch 問題、檔案較小、下載快

### 2. 增加 timeout 到 300 秒
```python
timeout=300  # 5 分鐘，給大檔案下載足夠緩衝
```

### 3. 禁用 torch._dynamo (防禦性)
```python
def init_torch(self):
    import torch
    # 【v6.17 fix】禁用 torch dynamo 避免 PyTorch 2.10+ functorch grad_and_value 錯誤
    torch._dynamo.config.suppress_errors = True
    try:
        torch._dynamo.disable()
    except:
        pass
    self.model = build_looped_transformer(self.config)
    self.optimizer = torch.optim.Adam(...)
```

---

## 驗證清單

下次遇到 Kaggle GPU 相容性問題時檢查：

- [ ] `torch.cuda.get_device_capability(0)` 確認 GPU 架構 (sm_60 = P100, sm_70 = V100, sm_75 = T4, sm_80 = A100)
- [ ] `torch.__version__` 確認 PyTorch 版本
- [ ] CUDA probe 實測: `torch.zeros(1, device="cuda") + 1.0` + `torch.cuda.synchronize()`
- [ ] 若 sm_60: 必須用 cu118 版本 (2.0.1 或 2.2.0)
- [ ] 若 PyTorch >= 2.10: 必須加 `torch._dynamo.disable()` 避免 functorch 錯誤
- [ ] pip install timeout >= 300s

---

## 相關檔案

- Notebook: `/tmp/twstock-grpo-v6-17-fixed.ipynb`
- Metadata: `/tmp/kernel-metadata-v6.17-fixed.json`
- 原始失敗 log: `/tmp/v617_output/twstock-grpo-v6-17-val-ic-reward-fix.log`
- Builder script: `/tmp/build_v617_fixed.py`

---

## 經驗總結

1. **Kaggle GPU 分配不可控** — 設計時假設 P100 (sm_60) 為常態，T4 (sm_75) 為加分項
2. **PyTorch 版本鎖定策略** — sm_60 環境強制使用 2.0.1+cu118，不要嘗試更新版本
3. **timeout 預設值陷阱** — 120s 對大型 wheel 檔案不夠，預設 300s 更安全
4. **dynamo 是新版 PyTorch 的隱性依賴** — optimizer 初始化會觸發編譯器，functorch 重組導致崩潰，禁用是最穩妥方案