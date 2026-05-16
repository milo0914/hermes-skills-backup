#!/bin/bash
# Hugging Face 同步驗證腳本
# 用於快速驗證同步狀態和完整性

set -e

HERMES_DIR="/data/.hermes"
SYNC_LOG="$HERMES_DIR/logs/sync_to_hf.log"
INTEGRITY_LOG="$HERMES_DIR/logs/integrity_check.log"
SYNC_STATE="$HERMES_DIR/sync_state.json"

echo "=========================================="
echo "Hugging Face 同步驗證工具"
echo "=========================================="
echo ""

# 1. 檢查必要文件
echo "1. 檢查必要文件..."
files_to_check=(
    "$HERMES_DIR/bin/sync_to_hf.py"
    "$HERMES_DIR/bin/integrity_check.py"
    "$HERMES_DIR/.env"
    "$SYNC_STATE"
)

for file in "${files_to_check[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✅ $file"
    else
        echo "  ❌ $file (缺失)"
    fi
done
echo ""

# 2. 檢查 Cron 任務
echo "2. 檢查 Cron 任務..."
if command -v hermes &> /dev/null; then
    hermes cron list 2>/dev/null | grep -q "同步會話到 HF Dataset" && echo "  ✅ 同步任務已安裝"
    hermes cron list 2>/dev/null | grep -q "每日完整性檢查" && echo "  ✅ 完整性檢查任務已安裝"
else
    echo "  ⚠️  hermes 命令不可用"
fi
echo ""

# 3. 檢查同步狀態
echo "3. 檢查同步狀態..."
if [ -f "$SYNC_STATE" ]; then
    LAST_SYNC=$(python3 -c "import json; print(json.load(open('$SYNC_STATE')).get('last_sync', '從不同步'))" 2>/dev/null || echo "無法讀取")
    SYNCED_COUNT=$(python3 -c "import json; print(len(json.load(open('$SYNC_STATE')).get('synced_files', {})))" 2>/dev/null || echo "0")
    echo "  最後同步時間：$LAST_SYNC"
    echo "  已同步文件數：$SYNCED_COUNT"
else
    echo "  ⚠️  同步狀態文件不存在"
fi
echo ""

# 4. 檢查日誌
echo "4. 檢查日誌..."
if [ -f "$SYNC_LOG" ]; then
    LAST_LINES=$(tail -3 "$SYNC_LOG")
    echo "  最近同步日誌："
    echo "$LAST_LINES" | sed 's/^/    /'
else
    echo "  ⚠️  同步日誌不存在"
fi
echo ""

if [ -f "$INTEGRITY_LOG" ]; then
    LAST_INTEGRITY=$(tail -3 "$INTEGRITY_LOG")
    echo "  最近完整性檢查："
    echo "$LAST_INTEGRITY" | sed 's/^/    /'
else
    echo "  ⚠️  完整性檢查日誌不存在"
fi
echo ""

# 5. 檢查 HF 連接
echo "5. 檢查 Hugging Face 連接..."
python3 -c "
from huggingface_hub import HfApi
import os

# 讀取 token
token = ''
with open('$HERMES_DIR/.env', 'r') as f:
    for line in f:
        if line.startswith('AUTH_TOKEN=hf_'):
            token = line.strip().split('=')[1]
            break

if token:
    try:
        api = HfApi(token=token)
        user = api.whoami()
        print(f'  ✅ 已登入：{user[\"name\"]}')
        
        # 檢查 dataset 是否存在
        try:
            files = api.list_repo_files('milo0914/record-for-hermes', repo_type='dataset')
            print(f'  ✅ Dataset 可訪問：{len(files)} 個文件')
        except Exception as e:
            print(f'  ⚠️  Dataset 訪問失敗：{e}')
    except Exception as e:
        print(f'  ❌ 登入失敗：{e}')
else:
    print('  ❌ 未找到 token')
" 2>/dev/null || echo "  ❌ Python 檢查失敗"
echo ""

# 6. 統計信息
echo "6. 統計信息..."
SESSIONS_COUNT=$(ls -1 "$HERMES_DIR/sessions/"*.json 2>/dev/null | wc -l)
SESSIONS_SIZE=$(du -sh "$HERMES_DIR/sessions/" 2>/dev/null | cut -f1)
echo "  本地會話數量：$SESSIONS_COUNT"
echo "  本地會話大小：$SESSIONS_SIZE"
echo ""

# 7. 建議
echo "=========================================="
echo "建議操作："
echo "=========================================="
echo ""
echo "手動同步："
echo "  python3 $HERMES_DIR/bin/sync_to_hf.py"
echo ""
echo "執行完整性檢查："
echo "  python3 $HERMES_DIR/bin/integrity_check.py"
echo ""
echo "查看完整日誌："
echo "  tail -50 $SYNC_LOG"
echo ""
echo "強制重新同步："
echo "  python3 $HERMES_DIR/bin/sync_to_hf.py --force"
echo ""
echo "=========================================="
