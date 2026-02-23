# Skill Framework Schema v2.0

This document defines the enhanced skill schema for improved agent autonomous decision-making.

## Extended Frontmatter Schema

```yaml
---
name: skill-name
description: Human-readable description for skill selection
version: "2.0.0"

# NEW: Structured tool definitions for efficient agent parsing
tools:
  - name: tool_name
    category: cli | mcp | script | api
    description: "What this tool does - used for tool selection"
    command: "actual command or function name"
    parameters:
      - name: param1
        type: string | int | bool | list | dict
        required: true | false
        default: null
        description: "Parameter description"
    examples:
      - "example command usage"
    aliases: [alt_name1, alt_name2]

# NEW: Explicit skill dependencies with resolution hints
dependencies:
  skills:
    - name: required-skill-name
      required: true | false
      reason: "Why this dependency is needed"
      auto_load: true | false
  packages:
    - name: package-name
      version: ">=1.0.0"
      install: "pip install package-name"
  environment:
    - name: HF_TOKEN
      required: true | false
      description: "Hugging Face API token"
  
# NEW: Prerequisites for autonomous validation
prerequisites:
  auth:
    - hf_authenticated
    - hf_write_access
  resources:
    - type: gpu
      required: false
      recommendation: "t4-small for demos, a10g-large for production"
  knowledge:
    - "Python basics"
    - "Hugging Face Hub concepts"

# NEW: Performance hints for decision-making
performance:
  typical_duration: "5m - 2h"
  cost_range: "$0.50 - $20"
  complexity: low | medium | high
---
```

## Tool Categories

| Category | Description | Example |
|----------|-------------|---------|
| `cli` | Command-line tools | `hf download` |
| `mcp` | MCP server tools | `hf_jobs()` |
| `script` | Python/UV scripts | `uv run script.py` |
| `api` | REST API endpoints | Direct API calls |

## Dependency Resolution Rules

1. **Required dependencies** must be available before skill activation
2. **Optional dependencies** enhance functionality but aren't blocking
3. **Auto-load dependencies** are automatically activated with the parent skill
4. **Circular dependencies** are detected and reported as errors

## Validation Commands

```bash
# Validate single skill schema
uv run scripts/skill_resolver.py validate --skill hugging-face-model-trainer

# Check all skill dependencies
uv run scripts/skill_resolver.py check-deps

# Get dependency graph
uv run scripts/skill_resolver.py graph

# Resolve and load dependencies for a skill
uv run scripts/skill_resolver.py resolve --skill hugging-face-model-trainer
```

## Agent Integration

When an agent loads a skill with this schema:

1. **Parse frontmatter** to extract tools and dependencies
2. **Validate prerequisites** before execution
3. **Auto-load dependent skills** marked with `auto_load: true`
4. **Register tools** with structured metadata for efficient selection
5. **Check environment** variables and auth status
