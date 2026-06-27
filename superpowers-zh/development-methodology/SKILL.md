---
name: development-methodology
description: 开发方法论集合——TDD、头脑风暴设计、GRPO 规划、技能编写。覆盖从需求探索到实现方法论的核心方法。
category: superpowers-zh
version: 1.0.0
created: 2026-06-03
---

# 开发方法论

核心开发方法论集合：如何用正确的方式做事。

## 何时使用

- 实现功能或修复 bug 前（TDD）
- 任何创造性工作前（头脑风暴）
- 需要智能任务分级和方案评估（GRPO 规划）
- 创建或编辑技能时（技能编写）

## 子方法论

### TDD 测试驱动开发（test-driven-development）

先写测试。看它失败。写最少的代码让它通过。

**核心原则：** 如果你没有看到测试失败，你就不知道它是否测试了正确的东西。

**详细参考：** `references/test-driven-development.md`

### 头脑风暴（brainstorming）

在任何创造性工作之前——创建功能、构建组件、添加功能或修改行为。在实现之前先探索用户意图、需求和设计。

**HARD GATE:** 在展示设计方案并获得用户批准之前，不写任何代码。

**详细参考：** `references/brainstorming.md`

### GRPO 规划（grpo-planning）

结合 GRPO 强化学习与 Planning 机制的 Agent 工作流程——智能任务分级路由，先画地圖再出發，群體採樣比較，規則獎勵評估，迭代優化策略。

**详细参考：** `references/grpo-planning.md`

### 技能编写（writing-skills）

编写技能就是将测试驱动开发应用于流程文档。包含技能创建、编辑、验证的完整流程。

**详细参考：** `references/writing-skills.md`

### Python 大段程式碼編輯（patch 限制與替代方案）

用 patch 工具替換 Python 中超過 30 行的程式碼區塊時，縮排可能靜默損壞（4-space → 1-space），導致 IndentationError。反覆用 patch 修復縮排只會越修越亂。

**正確做法**：
1. 用 search/read 定位受損區段的起迄行號
2. 用 Python 腳本讀取檔案、重寫整個受損區段（以周圍正確縮排為參照）
3. 每次修改後立即 `py_compile.compile(file, doraise=True)` 或 `ast.parse()` 驗證
4. 對於 >50 行的新方法，考慮直接用 write_file 寫入完整版本，再 Python 腳本替換

**適用場景**：任何需要插入或替換大段 Python 程式碼的情況（skill 腳本、notebook、配置生成器等）。

## 吸收记录

本技能于 2026-06-03 合并了以下独立技能：
- `test-driven-development` → references/test-driven-development.md
- `brainstorming` → references/brainstorming.md
- `grpo-planning` → references/grpo-planning.md
- `writing-skills` → references/writing-skills.md
