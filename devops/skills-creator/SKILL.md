---
name: skills-creator
description: Create, manage, and maintain Hermes Agent skills. Use when creating new skills, updating existing skills, or managing skill structure and best practices.
tags: [skills, creation, management, devops]
---

# Skills Creator

This skill provides guidance for creating and managing Hermes Agent skills effectively.

## When to Use

- Creating a new skill for a recurring task type
- Updating an existing skill that has issues or missing steps
- Organizing skills into categories
- Managing skill files (SKILL.md, references, templates, scripts)

## Skill Creation Guidelines

### When to Create a Skill

Create a skill when:
1. A complex task (5+ tool calls) succeeds after iteration
2. You overcome significant errors or pitfalls
3. A user-corrected approach works well
4. A non-trivial workflow is discovered
5. User explicitly asks you to remember a procedure

### Skill Structure

A well-structured skill should have:

1. **Frontmatter** (YAML):
   - `name`: lowercase, hyphens, max 64 chars
   - `description`: Clear, actionable description
   - `tags`: Relevant keywords for discovery

2. **Body** (Markdown):
   - **Trigger conditions**: When to use this skill
   - **Numbered steps**: Exact commands and tool calls
   - **Pitfalls section**: Common mistakes and how to avoid them
   - **Verification steps**: How to confirm success
   - **Examples**: Sample usage if helpful

### File Organization

Skills live in `/data/.hermes/skills/`. Structure:

```
/data/.hermes/skills/
├── skill-name/
│   ├── SKILL.md          # Main skill file
│   ├── references/       # Reference docs
│   ├── templates/        # Reusable templates
│   ├── scripts/          # Helper scripts
│   └── assets/           # Other assets
```

## Skill Management Commands

### Create a Skill
```
skill_manage(action='create', name='skill-name', content='...', category='devops')
```

### View a Skill
```
skill_view(name='skill-name')
```

### Update a Skill (patch - preferred for fixes)
```
skill_manage(action='patch', name='skill-name', old_string='...', new_string='...')
```

### Update a Skill (edit - full rewrite)
```
skill_manage(action='edit', name='skill-name', content='...')
```

### Delete a Skill
```
skill_manage(action='delete', name='skill-name')
```

## Best Practices

1. **Naming**: Use lowercase with hyphens (e.g., `browser-automation`, `web-researcher`)
2. **Descriptions**: Be specific about what the skill does and when to use it
3. **Pinned skills**: Don't modify pinned skills - they're off-limits
4. **Maintenance**: Update skills when you find issues during use
5. **Categories**: Use categories to organize skills (devops, research, creative, etc.)

## Common Pitfalls

1. **Not saving skills**: After complex tasks, always offer to save as a skill
2. **Outdated instructions**: Patch skills immediately when finding wrong/missing steps
3. **Imperative phrasing in memory**: Use declarative facts in memory, keep procedures in skills
4. **Over-categorization**: Don't create skills for simple one-off tasks

## Verification

After creating or updating a skill:
1. Load it with `skill_view(name='skill-name')`
2. Verify the structure is correct
3. Test that it would guide someone through the task successfully
4. Ensure pitfalls and verification steps are documented
