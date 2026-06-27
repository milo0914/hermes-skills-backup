# v5 報告修正工作流 — 完整記錄 (2026-06-04)

## 背景

v4 報告 (`report_merck_neg_da_elastic_scattering_v4.md`) 使用簡易 neg/pos 計數法
（陷阱 23），導致 7/18 篇專利的 Δε 判定與分析文字出現系統性錯誤。

## v13 重跑結果

| 專利號 | v4 判定 | v13 判定 | v13 confidence | v13 layer |
|--------|---------|----------|---------------|-----------|
| US12612551B2 | neg | confirmed_pos | 0.95 | abstract |
| US20250207032A1 | neg | confirmed_pos | 0.95 | abstract |
| US20250361444A1 | neg | confirmed_pos | 0.95 | abstract |
| EP4553132A1 | neg | AMBIGUOUS | 0.00 | none |
| US20250085595A1 | neg | AMBIGUOUS | 0.00 | none |
| US20250136868A1 | neg | likely_pos | 0.80 | claim1_display_mode |
| US20250197723A1 | neg | likely_pos | 0.80 | claim1_display_mode |

## 修正方法

### Python 批量修正策略

1. 用 `build_sections()` 建立各專利 section 的 position map
2. 用 `replace_in_section()` 限制修正範圍在目標專利 section 內
3. 分三類處理：POS 誤判、AMBIGUOUS 誤判、化合物級保留
4. 修正後掃描驗證零遺留

### 關鍵 replace 對

POS-DA 誤判修正：
- 「負介電各向異性」→「正介電各向異性」(系統級斷言)
- 「負Δε化合物在配方中」→「正Δε化合物在配方中」
- 「棒狀負Δε液晶分子」→「棒狀正Δε液晶分子」
- 「負Δε提Kavg」→「正Δε提Kavg」
- 「負介電材料體系」→「正介電材料體系」

AMBIGUOUS 修正：
- 刪除確定性斷言，改為「v13: AMBIGUOUS」+ 原因說明
- EP4553132A1: 微波應用，abstract 不涉及 DA 正負
- US20250085595A1: 光散射器件，LC 介質僅為周邊組件

化合物級保留不動：
- 「負Δε化合物」指個別化合物時保留
- 「正Δε + 負Δε混合」描述配方組成時保留

### 跨章節修正

- Ch3 趨勢分析：neg/pos 分布統計更新
- Ch4 參數表：Δε 值正負號修正
- Ch5 方法論：新增 v13 分類器說明

## Git 推送步驟

```bash
# 1. clone repo (或用現有 clone)
cd /tmp/hermes-patent-research

# 2. 複製修正後報告
cp /tmp/report_v4.md report_merck_neg_da_elastic_scattering_v5.md

# 3. git config (避免 "Author identity unknown")
git config user.email "milo0914@users.noreply.github.com"
git config user.name "milo0914"

# 4. 注入 token (避免 HTTPS 認證失敗)
git remote set-url origin https://<TOKEN>@github.com/milo0914/hermes-patent-research.git

# 5. commit & push
git add report_merck_neg_da_elastic_scattering_v5.md
git commit -m "patent-research: v5 報告 — v13四層分類器修正 Δε 判定"
git push origin main
```

## 結果

- 修正 7 篇專利的 Δε 分類
- 修正 30+ 處分析文字
- 跨章節修正 4 處趨勢統計
- 新增附錄：v13 分類修正一覽表
- GitHub commit: `7b92021`
