# FaceFusion Kaggle 模型預裝策略

## 問題
FaceFusion 的 headless-run 在 Kaggle GPU 上需要下載 ~1.6 GB 模型。
Kaggle 的 watchdog 會在 ~60 秒無 stdout 後 CANCEL kernel。
模型下載通常需要 30-60+ 秒，導致 kernel 在下載中途被取消。

## 解決方案：Kaggle Dataset 預裝模型 + 測試圖片

### 已建 Kaggle Datasets（2026-06-10）

**模型 Dataset**: `mhhuang14/facefusion-models-330`
- 26 檔案（13 .onnx + 13 .hash），總計 1,603 MB
- Private: https://www.kaggle.com/datasets/mhhuang14/facefusion-models-330

**測試圖片 Dataset**: `mhhuang14/facefusion-test-images`
- 2 檔案（source.jpg + target.jpg），真人臉部照片 512x512
- Private

### kernel-metadata.json 引用
```json
"dataset_sources": [
 "mhhuang14/facefusion-models-330",
 "mhhuang14/facefusion-test-images"
]
```

### Step 1：本地下載所有必要模型

```python
model_dir = '/tmp/facefusion_models'
os.makedirs(model_dir, exist_ok=True)

base_url = 'https://huggingface.co/facefusion/{repo}/resolve/main/{filename}'

# 完整 face_swapper=inswapper_128_fp16 + face_detector=yoloface_8n + face_masker
models = [
 # Content analyser (models-3.3.0)
 ('models-3.3.0', 'nsfw_1.hash'), ('models-3.3.0', 'nsfw_1.onnx'),  # 76.7 MB
 ('models-3.3.0', 'nsfw_2.hash'), ('models-3.3.0', 'nsfw_2.onnx'),  # 21.4 MB
 ('models-3.3.0', 'nsfw_3.hash'), ('models-3.3.0', 'nsfw_3.onnx'),  # 342 MB
 # Face classifier (models-3.0.0)
 ('models-3.0.0', 'fairface.hash'), ('models-3.0.0', 'fairface.onnx'),  # 81.2 MB
 # Face detector (models-3.0.0)
 ('models-3.0.0', 'yoloface_8n.hash'), ('models-3.0.0', 'yoloface_8n.onnx'),  # 12.1 MB
 # Face landmarker (models-3.0.0)
 ('models-3.0.0', '2dfan4.hash'), ('models-3.0.0', '2dfan4.onnx'),  # 93.4 MB
 ('models-3.0.0', 'fan_68_5.hash'), ('models-3.0.0', 'fan_68_5.onnx'),  # 0.9 MB
 # Face recognizer (models-3.0.0)
 ('models-3.0.0', 'arcface_w600k_r50.hash'), ('models-3.0.0', 'arcface_w600k_r50.onnx'),  # 166.3 MB
 # Face masker (models-3.1.0 + models-3.0.0)
 ('models-3.1.0', 'xseg_1.hash'), ('models-3.1.0', 'xseg_1.onnx'),  # 67.1 MB
 ('models-3.0.0', 'bisenet_resnet_34.hash'), ('models-3.0.0', 'bisenet_resnet_34.onnx'),  # 89.3 MB
 ('models-3.0.0', 'kim_vocal_2.hash'), ('models-3.0.0', 'kim_vocal_2.onnx'),  # 63.7 MB
 # Face swapper (models-3.0.0)
 ('models-3.0.0', 'inswapper_128_fp16.hash'), ('models-3.0.0', 'inswapper_128_fp16.onnx'),  # 264.8 MB
 # Face enhancer (models-3.0.0)
 ('models-3.0.0', 'gfpgan_1.4.hash'), ('models-3.0.0', 'gfpgan_1.4.onnx'),  # 324.5 MB
]

for repo, filename in models:
 url = base_url.format(repo=repo, filename=filename)
 filepath = os.path.join(model_dir, filename)
 # Use curl (not wget — wget fails on HF redirect)
 subprocess.run(['curl', '-sL', '-o', filepath, url], check=True)
```

**注意**：wget 在 HuggingFace 重定向下會失敗，必須用 `curl -sL`。

### Step 2：建立/更新 Kaggle Dataset

```bash
# 首次建立
KAGGLE_API_TOKEN="***" kaggle datasets create -p /tmp/facefusion-dataset/

# 版本更新（加入新模型）
KAGGLE_API_TOKEN="***" kaggle datasets version -p /tmp/facefusion-dataset/ -m "Add bisenet_resnet_34 + kim_vocal_2 face_masker models"
```

### Step 3：Notebook 中掛載 Dataset + 預裝模型

```python
import os, shutil, glob

# Kaggle Dataset 掛載路徑（注意三層巢狀）
src_dir = None
for root, dirs, files in os.walk('/kaggle/input/'):
 if 'inswapper_128_fp16.onnx' in files:
  src_dir = root
  break

if src_dir:
 dst_dir = '/kaggle/working/facefusion/.assets/models'
 os.makedirs(dst_dir, exist_ok=True)
 count = 0
 total_mb = 0
 for f in glob.glob(os.path.join(src_dir, '*.onnx')) + glob.glob(os.path.join(src_dir, '*.hash')):
  shutil.copy2(f, dst_dir)
  count += 1
  if f.endswith('.onnx'):
   total_mb += os.path.getsize(f) / 1024 / 1024
 print(f'Found {count} model files ({total_mb:.0f} MB) in: {src_dir}')
 print(f'All models pre-loaded — no HuggingFace download needed!')
```

### Step 4：載入真人測試圖片

```python
# Find test images dataset
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
 create_placeholder(SOURCE_IMAGE)
 create_placeholder(TARGET_IMAGE)
```

## 模型大小參考（26 檔案，1603 MB）

| 模型 | 大小 | 用途 | Repo |
|------|------|------|------|
| nsfw_3.onnx | 342 MB | Content analyser | models-3.3.0 |
| gfpgan_1.4.onnx | 324.5 MB | Face enhancer (optional) | models-3.0.0 |
| inswapper_128_fp16.onnx | 264.8 MB | Face swapper | models-3.0.0 |
| arcface_w600k_r50.onnx | 166.3 MB | Face recognizer | models-3.0.0 |
| bisenet_resnet_34.onnx | 89.3 MB | Face masker | models-3.0.0 |
| 2dfan4.onnx | 93.4 MB | Face landmarker | models-3.0.0 |
| fairface.onnx | 81.2 MB | Face classifier | models-3.0.0 |
| nsfw_1.onnx | 76.7 MB | Content analyser | models-3.3.0 |
| xseg_1.onnx | 67.1 MB | Face masker | models-3.1.0 |
| kim_vocal_2.onnx | 63.7 MB | Face masker | models-3.0.0 |
| nsfw_2.onnx | 21.4 MB | Content analyser | models-3.3.0 |
| yoloface_8n.onnx | 12.1 MB | Face detector | models-3.0.0 |
| fan_68_5.onnx | 0.9 MB | Face landmarker | models-3.0.0 |
| **Total (13 onnx)** | **~1,503 MB** | | |
| + 13 .hash files | ~0 MB | | |
| **Grand total** | **~1,603 MB** | | |

## HuggingFace Repo 分佈

- `facefusion/models-3.0.0` — 58 .onnx（核心 face 模型：inswapper, arcface, fairface, yoloface, 2dfan4, fan_68_5, gfpgan_1.4, bisenet_resnet_34, kim_vocal_2）
- `facefusion/models-3.1.0` — 11 .onnx（xseg_1 face masker）
- `facefusion/models-3.3.0` — 8 .onnx（nsfw_1/2/3, hyperswap, ultra_sharp）
- `facefusion/models-3.4.0` — 6 .onnx（crossface, yunet）
- `facefusion/models-3.5.0` — 15 .onnx（background removers）
- `facefusion/models-3.6.0` — 3 .onnx（fran, corridor_key）

## v4 驗證結果摘要

- 26 模型全部從 Dataset 載入（25.9s），零 HuggingFace 下載
- 真人照片 face swap 成功：result.jpg 12.6 KB, 6.32 秒
- 全部 10 cell DONE，總執行 79.7 秒

## Debug 歷史

1. v1-v3: placeholder 圖片無人臉 → facefusion 靜默退出 → CANCEL
2. v4 (舊): argparse 格式錯誤 → 預下載失敗
3. v5: capture_output=True 吞掉 stdout → watchdog CANCEL
4. v3 修復：Dataset 預裝 + capture_output=False + [Cell N DONE] 標記
5. v4 最終：補足 2 個缺失模型 + 真人照片 → 完全離線換臉成功
