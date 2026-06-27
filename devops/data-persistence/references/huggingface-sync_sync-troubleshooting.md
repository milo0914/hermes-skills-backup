# 同步問題排查指南

## 快速診斷流程

### 1. 檢查同步狀態
```bash
# 查看最近同步日誌
tail -50 /data/.hermes/logs/sync_to_hf.log

# 查看同步狀態
cat /data/.hermes/sync_state.json | python3 -m json.tool

# 執行完整性檢查
python3 /data/.hermes/bin/integrity_check.py
```

### 2. 常見錯誤代碼

#### 403 Forbidden
```
403 Forbidden: you must use a write token to upload to a repository.
```
**原因**：Token 只有 read 權限  
**解決**：
1. 前往 https://huggingface.co/settings/tokens
2. 創建新的 write token
3. 更新 `/data/.hermes/.env` 中的 `AUTH_TOKEN`

#### 401 Unauthorized
```
401 Unauthorized: Invalid token
```
**原因**：Token 無效或過期  
**解決**：
1. 檢查 token 是否正確
2. 重新創建 token
3. 更新 `.env` 文件

#### Connection Error
```
ConnectionError: HTTPSConnectionPool(host='huggingface.co', ...)
```
**原因**：網絡問題或防火牆阻擋  
**解決**：
```bash
# 測試連通性
curl -I https://huggingface.co

# 檢查代理設置
echo $HTTP_PROXY
echo $HTTPS_PROXY
```

#### Rate Limit Exceeded
```
429 Too Many Requests: Rate limit exceeded
```
**原因**：短時間內請求過多  
**解決**：
1. 等待 1 小時後重試
2. 檢查 Cron 任務間隔（應 >= 2 小時）
3. 避免手動頻繁觸發

### 3. 文件級別問題

#### 文件上傳失敗
**症狀**：部分文件上傳成功，部分失敗
```
[INFO] [1/73] 上傳：session_xxx.json (new)
[ERROR] 上傳失敗 session_xxx.json: ...
```
**排查**：
1. 檢查文件大小（單文件 < 10GB）
2. 檢查文件名稱是否合法
3. 查看具體錯誤信息

**解決**：
```bash
# 重試失敗的文件
python3 /data/.hermes/bin/sync_to_hf.py --force

# 或手動上傳
python3 -c "
from huggingface_hub import HfApi
api = HfApi(token='hf_...')
api.upload_file(
    path_or_fileobj='/data/.hermes/sessions/session_xxx.json',
    path_in_repo='sessions/session_xxx.json',
    repo_id='milo0914/record-for-hermes',
    repo_type='dataset'
)
"
```

#### 文件損壞
**症狀**：完整性檢查報告 JSON 解析錯誤
```
[INFO] 損壞文件：1
[ERROR] JSON 解析錯誤：Expecting value: line 1 column 1
```
**解決**：
```bash
# 1. 從遠端恢復
python3 /data/.hermes/bin/sync_bidirectional.py --download-only

# 2. 手動修復（如果可以）
python3 -c "
import json
with open('/data/.hermes/sessions/session_xxx.json', 'r') as f:
    data = json.load(f)  # 檢查是否可解析
"

# 3. 刪除損壞文件（如果遠端有備份）
rm /data/.hermes/sessions/session_xxx.json
python3 /data/.hermes/bin/sync_bidirectional.py --download-only
```

### 4. 同步狀態異常

#### sync_state.json 丟失
**症狀**：無法找到同步狀態文件
**解決**：
```bash
# 重新創建狀態文件
echo '{"synced_files": {}, "last_sync": null}' > /data/.hermes/sync_state.json

# 重新執行完整同步
python3 /data/.hermes/bin/sync_to_hf.py --force
```

#### 同步循環
**症狀**：文件反覆上傳但始終不同步
**原因**：本地和遠端 MD5 不一致
**解決**：
```bash
# 1. 清除同步狀態
rm /data/.hermes/sync_state.json

# 2. 重新執行完整性檢查
python3 /data/.hermes/bin/integrity_check.py

# 3. 手動校對
python3 -c "
import hashlib
with open('/data/.hermes/sessions/session_xxx.json', 'rb') as f:
    print(hashlib.md5(f.read()).hexdigest())
"
```

### 5. Cron 任務問題

#### 任務未執行
**症狀**：Cron 任務創建但未按時執行
**排查**：
```bash
# 檢查 Cron 狀態
hermes cron list

# 查看 Cron 日誌
tail -50 /data/.hermes/logs/cron_*.log

# 檢查 Python 腳本
ls -la /data/.hermes/bin/*.py
```

**解決**：
```bash
# 重新創建 Cron 任務
hermes cron delete <job_id>
hermes cron create ...
```

#### 任務執行失敗
**症狀**：Cron 任務執行但報錯
**排查**：
```bash
# 手動執行腳本
bash /data/.hermes/bin/cron_sync.sh

# 查看詳細錯誤
journalctl -u hermes-cron -n 50
```

### 6. 性能問題

#### 同步速度慢
**症狀**：同步耗時過長（>10 分鐘）
**可能原因**：
1. 網絡延遲高
2. 文件數量多
3. 單次上傳文件過多

**優化**：
```bash
# 限制單次上傳數量（修改 sync_to_hf.py）
MAX_FILES_PER_COMMIT = 20  # 減少為 20
MAX_COMMITS_PER_RUN = 2    # 減少為 2 次

# 使用增量同步
python3 /data/.hermes/bin/sync_to_hf.py  # 只上傳變動

# 離峰時間同步
# 修改 Cron 為凌晨執行
```

#### 內存佔用高
**症狀**：同步過程中內存使用過高
**優化**：
```bash
# 使用流式上傳（已默認啟用）
# 減少並發數（修改腳本中的並發參數）
```

## 調試工具

### 1. 網絡診斷
```bash
# 測試 HF 連通性
curl -I https://huggingface.co
curl -I https://huggingface.co/api/datasets

# 測試 API 訪問
python3 -c "
from huggingface_hub import HfApi
api = HfApi(token='hf_...')
print(api.whoami())
"
```

### 2. 文件完整性
```bash
# 計算 MD5
md5sum /data/.hermes/sessions/*.json | head -10

# 比較本地和遠端
python3 /data/.hermes/bin/integrity_check.py --json
```

### 3. 日誌分析
```bash
# 查看錯誤
grep -i error /data/.hermes/logs/sync_to_hf.log | tail -20

# 查看成功上傳
grep "上傳成功" /data/.hermes/logs/sync_to_hf.log | tail -10

# 統計同步次數
grep "同步開始" /data/.hermes/logs/sync_to_hf.log | wc -l
```

## 恢復流程

### 完全恢復（災難恢復）
```bash
# 1. 清除本地所有會話
rm /data/.hermes/sessions/*.json

# 2. 從 HF 下載所有備份
python3 /data/.hermes/bin/sync_bidirectional.py --download-only

# 3. 驗證完整性
python3 /data/.hermes/bin/integrity_check.py

# 4. 重新開始同步
python3 /data/.hermes/bin/sync_to_hf.py
```

### 部分恢復
```bash
# 只恢復特定會話
python3 -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='milo0914/record-for-hermes',
    filename='sessions/session_xxx.json',
    repo_type='dataset',
    local_dir='/data/.hermes/sessions/'
)
"
```

## 聯繫支持

如果以上方法都無法解決問題：
1. 收集相關日誌
2. 記錄錯誤信息
3. 檢查 HF 服務狀態：https://status.huggingface.co/
4. 查看 HF 社區論壇：https://discuss.huggingface.co/
