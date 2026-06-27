# Kaggle Auth 相容性測試結果

測試日期：2026-06-06
Kaggle CLI 版本：2.2.1
Python 版本：3.11.15

## 測試環境

- OS: Linux (Amazon 2023), container/VM
- 用戶: MHHUANG14
- Token 格式: KGAT_ 前綴（新版）

## 三種認證方式測試

### 方式 1: KAGGLE_API_TOKEN 環境變數

```bash
export KAGGLE_API_TOKEN="KGAT_xxxxx"
```

| 命令 | 結果 |
|------|------|
| kaggle config view | ✅ 顯示 auth_method: ACCESS_TOKEN |
| kaggle kernels list -m | ✅ 正常列出 |
| kaggle datasets list -m | ✅ 正常列出 |
| kaggle kernels pull | ✅ 正常下載 |
| kaggle kernels pull -m | ✅ 下載含 metadata |
| Python KaggleApi | ✅ 正常認證 |

### 方式 2: ~/.kaggle/kaggle.json

```json
{"username":"MHHUANG14","key":"KGAT_xxxxx"}
```

| 命令 | 結果 |
|------|------|
| kaggle datasets list | ✅ 正常（列出公開資料集） |
| kaggle datasets list -m | ⚠️ 列出公開而非自己的（行為錯誤） |
| kaggle kernels list -m | ❌ Authentication required |
| kaggle kernels pull | ✅ 正常下載 |

**問題**：kaggle.json 中放 KGAT_ 格式 token 時，`-m`（mine）參數命令認證失敗或行為異常。kaggle.json 的 `key` 欄位預期的是舊版 API key，不是新版 KGAT_ token。

### 方式 3: ~/.kaggle/access_token 檔案

```bash
echo "KGAT_xxxxx" > ~/.kaggle/access_token
```

| 命令 | 結果 |
|------|------|
| kaggle kernels list -m | ❌ Authentication required |

此方式不可用。

## 結論

**唯一穩定的認證方式是 KAGGLE_API_TOKEN 環境變數。**

kaggle.json 僅適用於舊版 API key 格式（非 KGAT_ 前綴），且即使如此，部分 -m 命令仍可能失敗。
