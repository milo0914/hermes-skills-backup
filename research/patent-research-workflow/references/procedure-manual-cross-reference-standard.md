# Procedure Manual Cross-Reference Standard

**Date**: 2026-06-04
**Applies to**: patent-research-procedure-manual.md and any future multi-chapter procedure docs

## Rule: Every operational chapter must explicitly cite its scripts and references

A centralized index chapter (e.g., "腳本索引") is necessary but NOT sufficient.
Each chapter that describes operations MUST end with a 📖 block listing:

1. **相關腳本** — exact path under `scripts/`, with one-line purpose
2. **相關 reference** — exact path under `references/` or `templates/`, with one-line summary

### Format

```
📖 **生產首選腳本**：`scripts/patent_extract_v11_1_improved.py` — Claim1 100%, 日期 100%
📖 **輔助腳本**：`scripts/_extract_single_patent.py` — 獨立進程單篇提取
📖 **相關 reference**：`references/v11_test_report.md` — v9/v10-A/v11 三版對比測試
```

### Which chapters need this

- Any chapter with procedural steps (search, extract, validate, generate, push)
- Any chapter with decision trees or method selection
- NOT needed for: classification chapters, prohibition lists, index tables, appendices

### Why this matters

Without per-chapter cross-references, an agent reading only one chapter cannot find
the relevant script without scanning the entire manual. This causes:
- Wrong script version used (e.g., v9 instead of v11.1)
- Missing reference docs with critical pitfall details
- Repeated mistakes that were already documented elsewhere

### Current coverage (2026-06-04)

| Chapter | 📖 refs | Status |
|---------|---------|--------|
| 1. 啟動前置作業 | 1 | OK |
| 2. 環境準備 | 3 | OK |
| 4. 搜索策略 | 6 | OK |
| 5. 數據提取 | 11 | OK |
| 6. Δε 正負介電判定 | 4 | OK |
| 7. EP 專利特殊處理 | 6 | OK |
| 8. Claim1 品質驗證 | 4 | OK |
| 9. 技術要點生成 | 6 | OK |
| 10. 進步性評判 | 2 | OK |
| 11. 報告生成 | 6 | OK |
| 12. GitHub 推送 | 7 | OK |
| 13. 多來源數據合併 | 4 | OK |

Total: 60 cross-references across 12 operational chapters.
