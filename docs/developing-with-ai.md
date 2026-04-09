# Developing with AI

This repository supports Claude Code out of the box via a top-level `CLAUDE.md` file and
team plugins from our shared marketplace.

## Getting Started

For complete setup instructions, security best practices, and workflow guidance, see the
**[Getting Started with Claude Code](https://github.com/edx/ai-devtools-internal/blob/main/docs/getting-started.md)**
guide in our team's ai-devtools-internal repository.

## Quick Reference

### Available Skills

| Skill | Command | Description |
|-------|---------|-------------|
| Unit Tests | `unit-tests` | Run Django tests in Docker |
| Quality Tests | `quality-tests` | Run linting and style checks |

### Key Files

- `CLAUDE.md` - Project context and instructions for Claude
- `.claude/settings.json` - Plugin and permission configuration
- `.claude/settings.local.json` - Personal overrides (gitignored)

### Enabled Plugins

This repo uses the `edx-enterprise-backend` plugin which provides skills for:
- Django model and query patterns
- Celery task patterns
- Security best practices
- System integration patterns

## Security Reminder

Always ensure you have [gitleaks](https://github.com/gitleaks/gitleaks) installed with a
pre-commit hook to prevent accidental credential commits. See the
[Getting Started guide](https://github.com/edx/ai-devtools-internal/blob/main/docs/getting-started.md#security-best-practices)
for setup instructions.
