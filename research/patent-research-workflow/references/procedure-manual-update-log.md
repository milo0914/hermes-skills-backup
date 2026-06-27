# v13 測試結果更新摘要

**Date**: 2026-06-04
**Updates Applied To**: SKILL.md (v5.2), references/v12-delta-epsilon-classifier.md, references/v13-offline-test-results.md

## SKILL.md Updates (patent-research-workflow v5.2)

1. **Pitfall 25**: Δε 分類器 Layer 4b "instead of" 正則中間隙文字未容納
   - 觸發條件：EP4400561A1 description 寫 "negative dielectric anisotropy instead of an LC medium with positive"
   - 根因：零間隙正則 `instead\s+of\s+positive` 無法匹配插入語 "an LC medium with"
   - 解決方案：改用 `.{0,40}?` 容納最多 40 字元間隙
   - 驗證：v13 離線測試 EP4400561A1 成功匹配

2. **Pitfall 26**: AMBIGUOUS 分類 — 不可為降低誤判率而強制二分
   - 觸發條件：abstract/claims/examples 均無法提供明確 DA 正負證據
   - 正確處理：標記 AMBIGUOUS + 手動複審路徑
   - 實例：EP4553132A1（微波應用，DA 無正負標示）、US20250085595A1（光散射元件，LC 為周邊組件）

3. **Version History**: 更新至 5.2 — v13 實作驗證、3 篇誤判修正（16.7%→0%）、AMBIGUOUS 從 5→2 合理案例

4. **Key Summary**: 新增 4 條失敗教訓（Δε 判定不做 description 次數統計、"instead of" 正則需容納間隙、AMBIGUOUS 不一定是缺陷、推薦腳本 v13）

## Reference Updates

1. **references/v12-delta-epsilon-classifier.md**: 新增 v13 Refinements 段落
   - Layer 1b: abstract 顯示模式縮寫匹配（VA/IPS/FFS/TN/PS-VA → implied DA, confidence 0.80）
   - Layer 4b: "instead of" 語義模式（confidence 0.70）
   - v13 離線測試結果表（v11/v12/v13 三版對比）
   - 3 篇誤判修正明細
   - v13 腳本路徑

2. **references/v13-offline-test-results.md**: 新建檔案
   - 18 篇專利逐篇 Δε 分類結果（含 Layer、Result、Confidence、Source）
   - 3 篇誤判修正明細
   - 5 篇 AMBIGUOUS 分析
   - 5 項關鍵發現
   - 下一步行動建議

## Cross-Reference Standard

手冊交叉引用標準已記錄在 `references/procedure-manual-cross-reference-standard.md`（60 條引用，12 個操作章節全覆蓋）。

## 手冊 (patent-research-procedure-manual.md) 狀態

手冊在先前 session 中寫入（38KB、985 行、16 章 + 4 附錄），但因跨 context 壓縮，檔案確切路徑未保留。已知資訊：
- 手冊涵蓋 v1-v11 的知識體系
- 60 條交叉引用已完成
- 需補充：v13 測試結果（3 篇誤判修正、AMBIGUOUS 統計、Layer 1b/4b 驗證結果）
- v13 結論已記錄在 references/v13-offline-test-results.md 和 references/v12-delta-epsilon-classifier.md 中，可作為手冊更新的來源
