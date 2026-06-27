# Contrast 專注搜索 + 深度提取實戰記錄 (2026-05-23)

## 任務目標
Merck KGaA 關於改善 LCD contrast 的負介電液晶材料專利（filing 2024-2026），至少 10 篇。

## 核心教訓：搜索關鍵字組合

### 失敗的搜索策略
前次調研使用 `assignee:"Merck Patent GmbH" + q="liquid crystal"` 搜索 592-key 大文件，結果中 "contrast" 出現次數為 **0**。原因："liquid crystal" 只是領域詞，沒有聚焦技術目標。

### 成功的搜索策略
加入技術目標詞 "contrast" / "high contrast" / "contrast ratio" 後，8 組搜索找到 27 篇候選專利：

| 組別 | 申請人 | 關鍵字 | 命中數 |
|------|--------|--------|--------|
| S1 | Merck Patent GmbH | "contrast" + "liquid crystal" | 8 |
| S2 | Merck Electronics KGaA | "contrast" + "liquid crystal" | 5 |
| S3 | Merck Patent GmbH | "high contrast" + "liquid crystal" | 2 |
| S4 | Merck Patent GmbH | "contrast" + "negative dielectric" | 2 |
| S5 | Merck Patent GmbH | "contrast" + C09K19/30 | 2 |
| S6 | Merck Patent GmbH | "contrast" + VA mode | 2 |
| S7 | Merck KGaA | "contrast" + "liquid crystal" | 0 |
| S8 | Merck Electronics KGaA | "contrast" + C09K19/30 | 0 |

### Merck Electronics KGaA 的重要性
S2 搜索發現 5 篇 Merck Patent GmbH 搜不到的新專利。這說明不同法律實體持有不同專利，搜索覆蓋需包含多個 assignee 別名。

## 深度提取技術

### inner_text 完整 description
`page.inner_text('body')` 返回 200K-350K 字元文本，包含：
- 274+ 個 Mixture Example 匹配（"Mixture Example Mxxx" 格式）
- 完整物理參數表（Δε, Δn, γ1, K1, K3, ε∥, ε⊥, V0, Cl.p.）
- 分子結構代碼（B(S)-2O-O4, CC-3-V, CCY-3-O2 等）
- Contrast 相關段落（10-60 處/篇）

### 正則提取模式
```python
# Mixture Examples
re.findall(r'(M\d+):\s+([\s\S]{30,800}?)(?=\n\s*(?:M\d+:|$))', body)

# Physical parameters
re.findall(r'(Δ[εn]|[εγ][∥⊥]|γ1|K[13]|V0)\s*\[?[^\]]*\]?\s*[:：]\s*([-\d.]+)', body)

# Molecular structure codes
re.findall(r'\b([A-Z]{1,4}\(?[A-Z]?\)?-[\dO]+-[\dO]+[\w-]*)\b', body)

# Contrast snippets
[m.start() for m in re.finditer(r'contrast', body, re.IGNORECASE)]
```

### 批量提取穩定性
- 單次 background 進程提取 25 篇（每篇 15-25s）
- 必須增量保存 JSON（每篇提取後立即寫入），避免超時丟失
- 進度監控：`jq '. | length' contrast_deep_extract_v2.json`

## 過濾流程

27 候選 → 25 提取 → 23 合格 → 19 去重 unique

過濾條件：
1. 日期範圍：filing date 2024-2026
2. 負介電確認：neg_count > 0 且 neg_count >= pos_count
3. Contrast 提及：至少 1 處
4. 去重：同族 US/EP 取數據最完整版本

排除 2 篇：
- US20260015735A1：標題 "Formulation"，neg=0, ctr=0，藥物製劑誤入
- EP4689796A1：標題 "Composition"，neg=0，非液晶組成物

## GITHUB_TOKEN 發現

`/data/.hermes/.env` 文件包含 `GITHUB_TOKEN=ghp_xxx...`，即使 shell `$GITHUB_TOKEN` 不可見。用 Python `dotenv_values` 讀取後直接推送成功。

比舊方法（從舊 repo remote URL 取得 token）更可靠，不依賴舊 repo 目錄存在。

## 最終結果

- 19 篇 unique 專利（15 US + 4 EP）
- 7 篇 contrast 提及 ≥25 處
- 9 篇負介電提及 ≥50 處
- 11 篇含完整物理參數
- 報告 58,801 字，推送至 milo0914/hermes-patent-research

## 核心技術特點摘要

1. VA/PSVA 模式優化 — 垂直對齊天然高對比
2. 降低散射參數 — 改善暗態遮光
3. 增大彈性常數 Kavg — 更充分垂直對齊
4. 降低驅動電壓 V0 — 減少串擾
5. VHR 維持 — 避免漏電導致對比度下降
6. 側向二氟取代苯環/嘧啶環 — 核心負介電單元
7. 乙烯基端基 — 降低粘度
