---
name: chinese-conventions
description: 中文开发团队规范集合——代码审查、提交规范、文档排版、Git 工作流。覆盖国内团队常见的规范化需求。
category: superpowers-zh
version: 1.0.0
created: 2026-06-03
---

# 中文开发团队规范

整合中文团队开发中常用的规范和最佳实践，包括代码审查、提交规范、文档排版和 Git 工作流。

## 何时使用

- 国内团队需要代码审查沟通参考
- 需要中文 Conventional Commits 配置
- 编写中文技术文档需要排版规范
- 国内 Git 平台（Gitee、Coding.net 等）配置参考

## 子规范

### 1. 代码审查（chinese-code-review）

中文 review 沟通参考——话术模板、分级标注（必须修复/建议修改/仅供参考）、国内团队常见反模式应对。

**核心原则：** 用"建议"代替"命令"，用"提问"代替"否定"，但绝不因为面子而放过 bug。

**详细参考：** `references/chinese-code-review.md`

### 2. 提交规范（chinese-commit-conventions）

中文 Conventional Commits 适配——commitlint/husky/commitizen 中文模板、conventional-changelog 中文配置。

**详细参考：** `references/chinese-commit-conventions.md`

### 3. 文档排版（chinese-documentation）

中文文档排版参考——中英文空格、全半角标点、术语保留、链接格式、中文文案排版指北约定。

**详细参考：** `references/chinese-documentation.md`

### 4. Git 工作流（chinese-git-workflow）

国内 Git 平台配置参考——Gitee、Coding.net、极狐 GitLab、CNB 的 SSH/HTTPS/凭据/CI 接入差异与镜像同步配置。

**详细参考：** `references/chinese-git-workflow.md`

## 吸收记录

本技能于 2026-06-03 合并了以下独立技能：
- `chinese-code-review` → references/chinese-code-review.md
- `chinese-commit-conventions` → references/chinese-commit-conventions.md
- `chinese-documentation` → references/chinese-documentation.md
- `chinese-git-workflow` → references/chinese-git-workflow.md
