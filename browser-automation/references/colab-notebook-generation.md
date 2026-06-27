# Colab Notebook 生成模式參考

## 概述

當瀏覽器自動化在複雜多步驟的 Web UI 交互中卡住時（例如 Colab 介面操作），直接使用 Python 生成 `.ipynb` 文件是更可靠的方法。

## 技術細節

### Notebook 結構
```python
notebook_content = {
  "cells": [...],
  "metadata": {
    "accelerator": "GPU",
    "colab": {"gpuType": "T4"},
    "kernelspec": {"display_name": "Python 3", "name": "python3"}
  },
  "nbformat": 4,
  "nbformat_minor": 0
}
```

### 關鍵單元格類型

1. **Markdown 說明** - 說明 notebook 用途和注意事項
2. **環境檢查** - GPU 檢查、Drive 掛載
3. **依賴安裝** - git clone、pip install
4. **模型下載** - 從 HuggingFace 或其他源下載
5. **服務啟動** - 後台啟動 ComfyUI 等服務
6. **隧道設置** - ngrok 或 localtunnel 配置
7. **API 驗證** - 檢查服務正常運行
8. **使用範例** - 完整的 API 調用範例

### 生成範例

```python
import json

notebook_content = {
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": ["# Title\n", "Description\n"]
    },
    {
      "cell_type": "code",
      "execution_count": None,
      "metadata": {},
      "outputs": [],
      "source": ["import os\n", "print('Hello')"]
    }
  ],
  "metadata": {...},
  "nbformat": 4,
  "nbformat_minor": 0
}

with open("/tmp/MyNotebook.ipynb", "w", encoding="utf-8") as f:
    json.dump(notebook_content, f, indent=2, ensure_ascii=False)
```

## 使用場景

- ComfyUI 環境設置
- LTXV 視頻創作模型載入
- 需要特定 GPU 配置的工作流程
- 需要 ngrok/loctunnel 穿透防火牆的場景

## 相關 API Keys

| 項目 | 必要性 | 用途 |
|------|-------|------|
| HuggingFace Token | 選填 | 下載 LTXV 等模型 |
| ngrok Token | 選填 | 穿透防火牆連接服務 |
| Google 帳號 | 必需 | 使用 Colab |

## 文件位置

生成的 notebook 位於：`/tmp/ComfyUI_LTXV_Colab.ipynb`

## 參考資源

- [ComfyUI GitHub](https://github.com/comfyanonymous/ComfyUI)
- [LTXV 模型頁面](https://huggingface.co/LanguageBind/LTX-Video-7B-1.0)
- [Colab 官方文檔](https://colab.research.google.com/)
