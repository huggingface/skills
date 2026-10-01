#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Generate OpenCode configuration from existing repo metadata.

Outputs:
- opencode.json (root config for OpenCode agent integration)

Design goals:
- First-class OpenCode integration consistent with Claude/Cursor/Gemini
- Auto-discover skills from skills/*/SKILL.md
- Reuse MCP configuration from gemini-extension.json
- Wire into scripts/publish.sh for drift prevention
- Support --check mode for CI validation

OpenCode config structure:
{
  "name": "huggingface-skills",
  "description": "...",
  "version": "0.1.0",
  "context": {
    "agents": "agents/AGENTS.md",
    "skills": "skills/"
  },
  "mcpServers": {
    "huggingface-skills": {
      "url": "https://huggingface.co/mcp?login"
    }
  },
  "skills": ["gradio", "hf-cli", ...],
  "metadata": {
    "author": "Hugging Face",
    "homepage": "https://huggingface.co",
    "repository": "https://github.com/huggingface/skills",
    "license": "Apache-2.0"
  }
}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
CLAUDE_PLUGIN_MANIFEST = ROOT / ".claude-plugin" / "plugin.json"
GEMINI_EXTENSION = ROOT / "gemini-extension.json"
OPENCODE_CONFIG = ROOT / "opencode.json"

DEFAULT_MCP_SERVER_NAME = "huggingface-skills"
DEFAULT_MCP_URL = "https://huggingface.co/mcp?login"


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse YAML frontmatter from SKILL.md files."""
    match = re.search(r"^---\s*\n(.*?)\n---\s*", text, re.DOTALL)
    if not match:
        return {}
    data: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def collect_skills() -> list[dict[str, str]]:
    """Discover all skills from skills/*/SKILL.md with metadata."""
    skills: list[dict[str, str]] = []
    for skill_md in sorted(ROOT.glob("skills/*/SKILL.md")):
        meta = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        name = meta.get("name", "").strip()
        if not name:
            # Fallback to directory name
            name = skill_md.parent.name
        
        description = meta.get("description", "")
        if not description:
            # Extract first paragraph from SKILL.md
            content = skill_md.read_text(encoding="utf-8")
            # Remove frontmatter
            content = re.sub(r"^---\s*\n.*?\n---\s*", "", content, flags=re.DOTALL)
            # Get first non-empty paragraph
            paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
            if paragraphs:
                description = paragraphs[0][:200]
        
        skills.append({
            "name": name,
            "path": str(skill_md.parent.relative_to(ROOT)),
            "description": description
        })
    return skills


def extract_mcp_from_gemini() -> tuple[str, str]:
    """Return (server_name, url) from gemini-extension when available."""
    if not GEMINI_EXTENSION.exists():
        return DEFAULT_MCP_SERVER_NAME, DEFAULT_MCP_URL

    data = load_json(GEMINI_EXTENSION)
    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        return DEFAULT_MCP_SERVER_NAME, DEFAULT_MCP_URL

    server_name = next(iter(servers.keys()))
    server_cfg = servers[server_name]
    if not isinstance(server_cfg, dict):
        return DEFAULT_MCP_SERVER_NAME, DEFAULT_MCP_URL

    url = server_cfg.get("url") or server_cfg.get("httpUrl") or DEFAULT_MCP_URL
    if not isinstance(url, str) or not url.strip():
        url = DEFAULT_MCP_URL

    return server_name, url


def build_opencode_config() -> dict[str, Any]:
    """Build complete OpenCode configuration."""
    # Get base metadata from Claude plugin manifest
    claude_meta = {}
    if CLAUDE_PLUGIN_MANIFEST.exists():
        claude_meta = load_json(CLAUDE_PLUGIN_MANIFEST)
    
    # Get MCP config from Gemini extension
    server_name, mcp_url = extract_mcp_from_gemini()
    
    # Discover all skills
    skills = collect_skills()
    if not skills:
        raise ValueError("No skills discovered under skills/*/SKILL.md")
    
    skill_names = [s["name"] for s in skills]
    
    config: dict[str, Any] = {
        "name": claude_meta.get("name", "huggingface-skills"),
        "description": claude_meta.get(
            "description", 
            "Hugging Face Agent Skills - specialized instructions for AI agents"
        ),
        "version": claude_meta.get("version", "0.1.0"),
        "context": {
            "agents": "agents/AGENTS.md",
            "skills": "skills/"
        },
        "mcpServers": {
            server_name: {
                "url": mcp_url
            }
        },
        "skills": skill_names,
        "skillDetails": skills,  # Full metadata for advanced use
        "metadata": {
            "author": claude_meta.get("author", "Hugging Face"),
            "homepage": claude_meta.get("homepage", "https://huggingface.co"),
            "repository": claude_meta.get("repository", "https://github.com/huggingface/skills"),
            "license": claude_meta.get("license", "Apache-2.0"),
            "keywords": claude_meta.get("keywords", ["ai", "llm", "skills", "huggingface", "agents"])
        }
    }
    
    return config


def render_json(data: dict) -> str:
    """Render JSON with consistent formatting."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_or_check(path: Path, content: str, check: bool) -> bool:
    """Return True when file is up-to-date (or after writing in non-check mode)."""
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current == content:
        return True

    if check:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate OpenCode configuration from repo metadata"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate generated config is up-to-date without writing changes.",
    )
    args = parser.parse_args()

    opencode_config = render_json(build_opencode_config())
    ok = write_or_check(OPENCODE_CONFIG, opencode_config, check=args.check)

    if args.check:
        if not ok:
            print("Generated OpenCode config is out of date:", file=sys.stderr)
            print(f"  - {OPENCODE_CONFIG.relative_to(ROOT)}", file=sys.stderr)
            print("Run: uv run scripts/generate_opencode_config.py", file=sys.stderr)
            sys.exit(1)

        print("OpenCode configuration is up to date.")
        return

    print(f"Wrote {OPENCODE_CONFIG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
