# Kaggle CLI 命令參考

版本：2.2.1（2026-06-06 測試）

## 全域命令

```bash
kaggle -h          # 幫助
kaggle -v          # 版本
```

## Auth

```bash
kaggle auth login               # OAuth 互動式登入
kaggle auth print-access-token  # 列印 access token
kaggle auth revoke              # 撤銷 refresh token
```

## Config

```bash
kaggle config view              # 查看當前配置
kaggle config set -n NAME -v VALUE  # 設定配置值
kaggle config unset -n NAME     # 移除配置值
```

## Competitions

```bash
kaggle competitions list                     # 列出競賽
kaggle competitions list -s "search term"    # 搜尋競賽
kaggle competitions download SLUG            # 下載競賽資料
kaggle competitions submit SLUG -f FILE -m "msg"  # 提交
kaggle competitions leaderboard SLUG         # 排行榜
kaggle competitions leaderboard SLUG -d      # 下載排行榜 CSV
```

## Datasets

```bash
kaggle datasets list                         # 列出公開資料集
kaggle datasets list -m                      # 列出自己的資料集
kaggle datasets list -s "search"             # 搜尋
kaggle datasets list --sort-by votes         # 排序（hotness/votes/updated等）
kaggle datasets download OWNER/SLUG          # 下載
kaggle datasets download OWNER/SLUG --unzip  # 下載並解壓
kaggle datasets download OWNER/SLUG -f FILE  # 下載特定檔案
kaggle datasets files -d OWNER/SLUG          # 列出檔案
kaggle datasets create -p /path              # 建立新資料集
kaggle datasets version -p /path -m "msg"    # 更新版本
kaggle datasets metadata OWNER/SLUG          # 查看 metadata
```

## Kernels (Notebooks)

```bash
kaggle kernels list                          # 列出 kernels
kaggle kernels list -m                       # 列出自己的
kaggle kernels list --user USERNAME          # 特定用戶的
kaggle kernels list --language python        # 篩選語言
kaggle kernels list --kernel-type notebook   # 篩選類型
kaggle kernels list --sort-by dateRun        # 排序
kaggle kernels list --page-size 10           # 每頁數量（非 --max）
kaggle kernels pull OWNER/SLUG              # 下載原始碼
kaggle kernels pull OWNER/SLUG -m           # 下載含 metadata
kaggle kernels pull OWNER/SLUG -p /path     # 指定下載路徑
kaggle kernels push -p /path                # 推送執行
kaggle kernels push -p /path --accelerator GPU_T4  # 指定加速器
kaggle kernels push -p /path -t 3600        # 設定超時秒數
kaggle kernels status OWNER/SLUG            # 查看執行狀態
kaggle kernels output OWNER/SLUG            # 下載執行輸出
```

### 參數注意

- 沒有 `--max` 參數（舊版有，2.2.1 已移除），用 `--page-size` 替代
- `--sort-by` 選項：hotness, commentCount, dateCreated, dateRun, relevance, scoreAscending, scoreDescending, viewCount, voteCount
- `--language` 選項：all, python, r, sqlite, julia
- `--kernel-type` 選項：all, script, notebook
- `--accelerator` 選項：GPU_T4, GPU_P100 等

## Models

```bash
kaggle models list                           # 列出模型
kaggle models instances list MODEL-SLUG      # 列出模型版本
kaggle models instances download OWNER/MODEL/INSTANCE  # 下載模型
```

## Files

```bash
kaggle files list OWNER/SLUG                 # 列出 notebook 檔案
```

## Forums

```bash
kaggle forums list SLUG                      # 列出論壇主題
kaggle forums submissions SLUG               # 列出提交討論
```

## Benchmarks

```bash
kaggle benchmarks list                       # 列出基準測試
```

## Quota

```bash
kaggle quota                                 # 查看 API 配額
```
