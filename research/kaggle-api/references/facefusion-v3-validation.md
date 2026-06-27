# FaceFusion v3/v4 Kaggle 驗證結果 (2026-06-10)

## 結論
v4 Dataset 預裝模型 + 真人測試圖片 = 完全離線執行 + 換臉成功。

## v4 最終驗證結果

| 指標 | v3 (Dataset 22 files) | v4 (Dataset 26 files + test images) |
|------|----------------------|--------------------------------------|
| 模型數量 | 22 (缺 bisenet_resnet_34, kim_vocal_2) | 26 (完整) |
| HuggingFace 下載 | 2 個模型 ~153MB 即時下載 | **0 — 完全離線** |
| 模型載入時間 | 19-22s | 25.9s |
| 測試圖片 | placeholder (無人臉) | 真人照片 (source.jpg + target.jpg) |
| Face Swap 結果 | "no source face detected" | **成功！ result.jpg 12.6 KB, 6.32s** |
| 總執行時間 | ~70-80s | 79.7s |
| Cell 完成 | 10/10 | 10/10 |

## v4 關鍵改動 (vs v3)

### 1. Dataset 更新：22 → 26 檔案
新增 4 個檔案（來自 facefusion/models-3.0.0 repo）：
- bisenet_resnet_34.onnx (89.3 MB) — face_masker 分割模型
- bisenet_resnet_34.hash (8 B)
- kim_vocal_2.onnx (63.7 MB) — face_masker 相關模型
- kim_vocal_2.hash (8 B)

### 2. 新增測試圖片 Dataset
新建 `mhhuang14/facefusion-test-images`（private）：
- source.jpg (51,239 bytes, 512x512) — Unsplash 男子人臉
- target.jpg (34,172 bytes, 512x512) — Unsplash 女子人臉

### 3. Notebook Cell 4 更新
從 placeholder 圖片改為從 Dataset 載入真人照片：
```python
# --- Load real face test images from Kaggle Dataset ---
test_img_dir = None
for root, dirs, files in os.walk('/kaggle/input/'):
 if 'source.jpg' in files and 'target.jpg' in files:
  test_img_dir = root
  break

if test_img_dir:
 shutil.copy2(os.path.join(test_img_dir, 'source.jpg'), SOURCE_IMAGE)
 shutil.copy2(os.path.join(test_img_dir, 'target.jpg'), TARGET_IMAGE)
 print(f'Loaded real face images from dataset: {test_img_dir}')
else:
 # Fallback: placeholder (face swap will fail with "no face detected")
 ...
```

### 4. kernel-metadata.json 更新
```json
"dataset_sources": [
 "mhhuang14/facefusion-models-330",
 "mhhuang14/facefusion-test-images"
]
```

## v4 執行時間線 (79.7s)

| 時間 | 事件 |
|------|------|
| 0-10s | Cell 1: GPU env check (Tesla T4 x2, 15GB VRAM) |
| 10-35s | Cell 2-3: Clone FaceFusion + pip install |
| 35-61s | Cell 4: Scan 26 models (1603 MB) → cp to .assets/models/ + load face images |
| 61-75s | Cell 5: Face swap headless-run (6.32s processing) |
| 75-76s | Cell 6-8: Video pipeline, GPU diagnostics, preview |
| 76-80s | Cell 9-10: Display result, save output |

## 模型清單（26 檔案，1603 MB）

| 模型 | 大小 | 用途 | 來源 Repo |
|------|------|------|-----------|
| nsfw_3.onnx | 342 MB | Content analyser | models-3.3.0 |
| gfpgan_1.4.onnx | 324.5 MB | Face enhancer | models-3.0.0 |
| inswapper_128_fp16.onnx | 264.8 MB | Face swapper | models-3.0.0 |
| arcface_w600k_r50.onnx | 166.3 MB | Face recognizer | models-3.0.0 |
| **bisenet_resnet_34.onnx** | **89.3 MB** | **Face masker** | **models-3.0.0** |
| fairface.onnx | 81.2 MB | Face classifier | models-3.0.0 |
| nsfw_1.onnx | 76.7 MB | Content analyser | models-3.3.0 |
| xseg_1.onnx | 67.1 MB | Face masker | models-3.1.0 |
| **kim_vocal_2.onnx** | **63.7 MB** | **Face masker** | **models-3.0.0** |
| 2dfan4.onnx | 93.4 MB | Face landmarker | models-3.0.0 |
| nsfw_2.onnx | 21.4 MB | Content analyser | models-3.3.0 |
| yoloface_8n.onnx | 12.1 MB | Face detector | models-3.0.0 |
| fan_68_5.onnx | 0.9 MB | Face landmarker | models-3.0.0 |
| 13 .hash 檔案 | ~0 MB | 驗證檔 | 各 repo |

## 注意事項

1. **Title/slug 不匹配** — 推送時 title "FaceFusion Kaggle GPU T4 v4" 會產生新 slug `facefusion-kaggle-gpu-t4-v4`，與 v3 的 `facefusion-kaggle-gpu-t3` 不同。保持用 v3 的 title/slug 可避免此問題。
2. **kaggle kernels pull 回傳的 metadata 會遺失 GPU 設定** — `enable_gpu` 會變 false，需手動修正。
3. **kaggle datasets files --csv 可能需要翻頁** — 26 個檔案超過單頁 20 個限制，需用 `--page-token` 或 Python API。
