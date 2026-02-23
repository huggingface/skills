<skills>

You have additional SKILLs documented in directories containing a "SKILL.md" file.

These skills are:
{{#skills}}
 - {{name}} -> "{{path}}/SKILL.md"
{{/skills}}

IMPORTANT: You MUST read the SKILL.md file whenever the description of the skills matches the user intent, or may help accomplish their task. 

<available_skills>

{{#skills}}
{{name}}: `{{description}}`

{{/skills}}
</available_skills>

<skill_tools>

Skills with structured tool definitions (for efficient agent tool selection):
{{#skills}}
{{#has_tools}}
- **{{name}}**: {{tool_count}} tools available ({{tool_categories}})
{{/has_tools}}
{{/skills}}

</skill_tools>

<skill_dependencies>

Dependency resolution available via command:
- `uv run scripts/skill_resolver.py resolve --skill <skill-name>` - Get full dependency tree
- `uv run scripts/skill_resolver.py tools --skill <skill-name> --format json` - Get structured tool manifest
- `uv run scripts/skill_resolver.py check-deps` - Validate all skill dependencies
- `uv run scripts/skill_resolver.py graph` - Generate dependency graph

</skill_dependencies>

Paths referenced within SKILL folders are relative to that SKILL. For example the hf-datasets `scripts/example.py` would be referenced as `hf-datasets/scripts/example.py`. 

</skills>
