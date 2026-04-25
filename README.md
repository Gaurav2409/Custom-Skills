# skills-repo

A catalog of reusable AI coding assistant skills.

## Skills

| Skill | Description |
|-------|-------------|
| **llm-knowledge-base** | Build and maintain a personal LLM-powered knowledge base — ingest raw documents, compile an Obsidian-compatible wiki, run Q&A, generate slide decks and charts, and lint the wiki for health |
| **web-clipper** | Clip web pages to local Markdown files with downloaded images — renders JS-heavy pages via Playwright, extracts article content, and saves clean `.md` files with locally referenced images |

Skills are located in `.claude/skills/` and can be invoked by AI coding assistants (e.g. Claude Code).

## Repository Structure

```
.claude/skills/
  <skill-name>/
    SKILL.md              # Main skill definition with frontmatter
    templates/            # Optional template files (scripts, configs) to copy into user projects
    references/           # Optional reference documentation
```

## Skill File Format

Each skill has a `SKILL.md` with YAML frontmatter:

```markdown
---
name: skill-name
description: When this skill should trigger and what it does
---
# Skill Title
[Instructions for the AI assistant]
```

## Usage

### Local (Claude Code)

Copy `.claude/skills/` into your project root or your global `~/.claude/` directory:

```bash
# Project-level (applies to this project only)
cp -r .claude/skills/<skill-name> /path/to/your/project/.claude/skills/

# Global (applies to all projects)
cp -r .claude/skills/<skill-name> ~/.claude/skills/
```

Then invoke the skill in Claude Code by describing what you want to do — Claude will automatically match the request to the skill.

### Skill Marketplaces

To publish a skill to a marketplace:

1. Ensure `SKILL.md` has complete frontmatter (`name`, `description`)
2. Include all supporting `templates/` and `references/` files
3. Package the skill directory as a zip or submit as a PR to the marketplace registry

## Adding a New Skill

1. Create directory: `.claude/skills/<skill-name>/`
2. Add `SKILL.md` with frontmatter and step-by-step instructions
3. Add `templates/` for files to copy into user projects
4. Add `references/` for supporting documentation
5. Update the skills table in this README
