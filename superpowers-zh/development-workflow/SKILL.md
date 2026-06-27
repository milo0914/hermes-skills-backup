---
name: development-workflow
description: 软件开发完整工作流——从计划编写、并行分派、子代理驱动开发、Git 工作树隔离，到分支收尾和完成前验证。覆盖从规划到交付的全流程。
category: superpowers-zh
version: 1.0.0
created: 2026-06-03
---

# 开发工作流

从规划到交付的完整软件开发工作流，包含计划编写、执行、子代理分派、Git 隔离、验证和收尾。

## 何时使用

- 需要编写实现计划（多步骤任务）
- 执行已有计划并设置检查点
- 使用子代理并行执行独立任务
- 创建 Git 工作树进行隔离开发
- 完成分支开发需要决定如何集成
- 在宣称完成前需要验证证据

## 工作流阶段

### 阶段 1: 规划
- **writing-plans**: 编写全面的实现计划，拆分小步骤任务
- **using-git-worktrees**: 创建隔离工作区

**详细参考：** `references/writing-plans.md`, `references/using-git-worktrees.md`

### 阶段 2: 执行
- **subagent-driven-development**: 为每个任务分派子代理
- **dispatching-parallel-agents**: 独立任务并行执行
- **executing-plans**: 在会话中顺序执行计划

**详细参考：** `references/subagent-driven-development.md`, `references/dispatching-parallel-agents.md`, `references/executing-plans.md`

### 阶段 3: 收尾与验证
- **verification-before-completion**: 用证据支撑完成断言
- **finishing-a-development-branch**: 结构化选项引导工作收尾

**详细参考：** `references/verification-before-completion.md`, `references/finishing-a-development-branch.md`

## 吸收记录

本技能于 2026-06-03 合并了以下独立技能：
- `writing-plans` → references/writing-plans.md
- `executing-plans` → references/executing-plans.md
- `finishing-a-development-branch` → references/finishing-a-development-branch.md
- `subagent-driven-development` → references/subagent-driven-development.md
- `dispatching-parallel-agents` → references/dispatching-parallel-agents.md
- `verification-before-completion` → references/verification-before-completion.md
- `using-git-worktrees` → references/using-git-worktrees.md
