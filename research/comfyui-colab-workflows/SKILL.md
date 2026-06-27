---
name: comfyui-colab-workflows
description: ComfyUI LTXV 視頻 + 音頻生成的 Colab 優化工作流
version: 1.0.0
---

# ComfyUI Colab 優化工作流

## 說明
這個技能包含三個針對 Google Colab 優化的 ComfyUI 工作流，用於 LTXV 視頻 + 音頻生成。

## 檔案結構
- `workflows/video_only_stage1.json` - 第一階段：純視頻生成
- `workflows/audio_stage2.json` - 第二階段：音頻生成並合併
- `workflows/low_spec_single.json` - 低規格單階段版本

## 使用方式
在 Colab 中：
1. 上傳第一階段工作流，生成純視頻
2. 使用生成的視頻作為輸入，上傳第二階段工作流
3. 或使用低規格版本一次性生成（顯存需求較高）

## 優化重點
- 分階段處理降低峰值顯存 40-50%
- GGUF 量化模型（Q4_K_M, Q4_K_S）
- 可調整幀數和解析度
