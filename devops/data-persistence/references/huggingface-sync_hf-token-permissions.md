# Hugging Face Token 權限說明

## Token 類型與權限

### Read Token（讀取權限）
- **用途**：下載模型、數據集、讀取倉庫內容
- **限制**：無法上傳、修改或刪除任何內容
- **識別**：在 HF Dashboard 中顯示為 `read` 角色
- **適用場景**：
  - 從 HF Hub 下載模型
  - 讀取 Dataset 文件
  - 驗證 token 有效性

### Write Token（寫入權限）✅ 推薦
- **用途**：上傳模型、數據集、創建/修改/刪除文件
- **限制**：無法管理用戶或組織設置
- **識別**：在 HF Dashboard 中顯示為 `write` 角色
- **適用場景**：
  - 上傳會話備份到 Dataset
  - 同步配置文件
  - 自動化備份流程

### Full Permissions Token（完整權限）
- **用途**：完整訪問所有 HF API
- **限制**：無限制（高風險）
- **識別**：在 HF Dashboard 中顯示為 `owner` 角色
- **適用場景**：
  - 管理組織成員
  - 刪除倉庫
  - 管理 billing

## 如何創建 Write Token

### 步驟 1：進入 Token 管理頁面
訪問：https://huggingface.co/settings/tokens

### 步驟 2：創建新 Token
1. 點擊 "Create new token" 按鈕
2. 輸入 Token 名稱（例如：`hermes-sync-write`）
3. **勾選 `write` 權限**（必要！）
4. 點擊 "Generate token"

### 步驟 3：保存 Token
- 立即複製 token（只顯示一次！）
- 格式：`hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxx`
- 安全存儲，不要提交到 Git

### 步驟 4：配置到 Hermes
```bash
# 編輯 .env 文件
nano /data/.hermes/.env

# 替換舊 token
AUTH_TOKEN=hf_你的新_write_token
```

## 驗證 Token 權限

### Python 驗證
```python
from huggingface_hub import HfApi

api = HfApi(token="hf_你的 token")
user = api.whoami()

print(f"用戶：{user['name']}")
print(f"類型：{user['type']}")
# 嘗試上傳操作來驗證 write 權限
```

### CLI 驗證
```bash
# 測試讀取
huggingface-cli whoami

# 測試寫入（會創建測試文件）
huggingface-cli upload --repo-type dataset milo0914/test-repo test.txt test.txt
```

## 常見錯誤

### 403 Forbidden - Read Token
```
403 Forbidden: you must use a write token to upload to a repository.
Cannot access content at: https://huggingface.co/api/datasets/...
```
**原因**：使用了只有 read 權限的 token  
**解決**：創建新的 write token 並更新 `.env`

### Token 過期
```
401 Unauthorized: Invalid token
```
**原因**：token 無效或已撤銷  
**解決**：重新創建 token 並更新配置

### 權限不足
```
403 Forbidden: You don't have permission to access this resource.
```
**原因**：token 權限不足或訪問私有倉庫  
**解決**：檢查 token 權限和倉庫可見性

## 安全建議

### ✅ 推薦做法
1. **最小權限原則**：只授予必要的權限
2. **定期輪換**：每 3-6 個月更換一次 token
3. **環境變量**：使用 `.env` 文件，不直接寫死在代碼中
4. **私有倉庫**：備份數據設置為 private

### ❌ 避免做法
1. 不要將 token 提交到 Git 倉庫
2. 不要在前端代碼中使用 token
3. 不要分享或洩露 token
4. 不要使用同一個 token 跨多個環境

## 權限對照表

| 操作 | Read | Write | Full |
|------|------|-------|------|
| 下載模型 | ✅ | ✅ | ✅ |
| 上傳模型 | ❌ | ✅ | ✅ |
| 下載 Dataset | ✅ | ✅ | ✅ |
| 上傳 Dataset | ❌ | ✅ | ✅ |
| 刪除倉庫 | ❌ | ❌ | ✅ |
| 管理用戶 | ❌ | ❌ | ✅ |
| 管理 billing | ❌ | ❌ | ✅ |

## 參考鏈接
- [HF Token 管理頁面](https://huggingface.co/settings/tokens)
- [HF API 文檔](https://huggingface.co/docs/huggingface_hub)
- [HF 安全最佳實踐](https://huggingface.co/docs/hub/security)
