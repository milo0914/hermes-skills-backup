# FaceFusion Kaggle Notebook: Video Auto-Scan Pattern

## 問題
Cell 4 中 `TARGET_VIDEO = None` 需手動設定，用戶不知道影片放哪裡、支援什麼格式。

## 解決方案：自動掃描 /kaggle/input/ 影片

在 Cell 4 加入以下邏輯，自動掃描 Kaggle Dataset 掛載的影片檔案：

```python
# Supported video formats (FaceFusion uses ffmpeg, all work)
VIDEO_EXTENSIONS = ('.mp4', '.avi', '.mov', '.mkv')
VIDEO_DIR = '/kaggle/working/sample_videos'
os.makedirs(VIDEO_DIR, exist_ok=True)

# --- Auto-scan for video files in Kaggle Datasets ---
print('\nScanning /kaggle/input/ for video files...')
video_candidates = []
for root, dirs, files in os.walk('/kaggle/input/'):
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        if ext in VIDEO_EXTENSIONS:
            video_candidates.append(os.path.join(root, f))

if video_candidates:
    # Sort by priority: mp4 first (best compatibility), then avi, mov, mkv
    # Within same extension, pick largest file
    ext_priority = {'.mp4': 0, '.avi': 1, '.mov': 2, '.mkv': 3}
    video_candidates.sort(key=lambda p: (ext_priority.get(os.path.splitext(p)[1].lower(), 9), -os.path.getsize(p)))
    TARGET_VIDEO = video_candidates[0]
    print(f'Found {len(video_candidates)} video(s), using: {TARGET_VIDEO}')
    for v in video_candidates:
        size_mb = os.path.getsize(v) / (1024**2)
        print(f'  {os.path.basename(v)} ({size_mb:.1f} MB) — {v}')
else:
    print('No video files found in /kaggle/input/.')
    print('To use video face swap:')
    print('  1. Upload your video to a Kaggle Dataset')
    print('  2. Add the dataset as a Data Source in Kaggle Settings')
    print('  3. Supported formats: mp4, avi, mov, mkv')
    print('  4. Re-run this cell')
```

## 使用方式
1. 把影片上傳到任意 Kaggle Dataset（private 即可）
2. 在 Kaggle notebook Settings → Data → Add Data Source 加入該 Dataset
3. Cell 4 執行時自動掃描找到影片，設到 TARGET_VIDEO
4. Cell 6 的 `run_video_faceswap()` 和 `run_video_in_segments()` 直接使用 TARGET_VIDEO

## 格式支援
| 格式 | 相容性 | 建議 |
|------|--------|------|
| .mp4 | 最佳 | 首選，通用性最高 |
| .avi | 良好 | 可用，檔案通常較大 |
| .mov | 良好 | Apple 格式，ffmpeg 支援 |
| .mkv | 良好 | 開源容器，ffmpeg 支援 |

FaceFusion 底層用 ffmpeg 讀取影片，四種格式皆可。排序優先選 mp4 是因為相容性最好且通常檔案最小。

## 修改記錄
- v3 kernel: Cell 4 從 `TARGET_VIDEO = None` 改為自動掃描
- Push 為 Kernel version 3 (2026-06-10)
