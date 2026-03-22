#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Generate OpenCode configuration from existing repo metadata.

Outputs:
- opencode.json

Design goals:
- Keep OpenCode configuration in sync with other agent formats.
- Reuse .claude-plugin/plugin.json as primary metadata source.
- Discover skills from skills/*/SKILL.md.
- Include AGENTS context from agents/AGENTS.md.
- Align MCP server settings with .mcp.json / gemini-extension.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CLAUDE_PLUGIN_MANIFEST = ROOT / ".claude-plugin" / "plugin.json"
GEMINI_EXTENSION = ROOT / "gemini-extension.json"
MCP_CONFIG = ROOT / ".mcp.json"
AGENTS_CONTEXT = ROOT / "agents" / "AGENTS.md"
OPENCODE_CONFIG = ROOT / "opencode.json"

DEFAULT_MCP_SERVER_NAME = "huggingface-skills"
DEFAULT_MCP_URL = "https://huggingface.co/mcp?login"


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def parse_frontmatter(text: str) -> dict[str, str]:
    match = re.search(r"^---\s*\n(.*?)\n---\s*", text, re.DOTALL)
    if not match:
        return {}
    data: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"')
    return data


def collect_skills() -> list[dict[str, str]]:
    """Collect all skills from skills/*/SKILL.md"""
    skills: list[dict[str, str]] = []
    for skill_md in sorted(ROOT.glob("skills/*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        meta = parse_frontmatter(text)
        name = meta.get("name", "").strip()
        description = meta.get("description", "").strip()
        if not name:
            continue
        
        skills.append({
            "name": name,
            "description": description,
            "path": str(skill_md.parent.relative_to(ROOT)),
        })
    return skills


def get_mcp_server_url() -> str:
    """Extract MCP server URL from gemini-extension.json or use default"""
    try:
        gemini = load_json(GEMINI_EXTENSION)
        servers = gemini.get("mcpServers", {})
        hf_server = servers.get(DEFAULT_MCP_SERVER_NAME, {})
        return hf_server.get("url", DEFAULT_MCP_URL)
    except (FileNotFoundError, KeyError):
        return DEFAULT_MCP_URL


def build_opencode_config() -> dict:
    """Build opencode.json configuration"""
    try:
        claude = load_json(CLAUDE_PLUGIN_MANIFEST)
    except FileNotFoundError:
        claude = {}
    
    skills = collect_skills()
    mcp_url = get_mcp_server_url()
    
    config = {
        "name": claude.get("name", "huggingface-skills"),
        "version": claude.get("version", "1.0.0"),
        "description": claude.get("description", "Hugging Face ecosystem skills for OpenCode"),
        "skills": {
            "discovery": {
                "locations": [
                    "skills/"
                ],
                "format": "agent-skills"
            },
            "entries": [
                {
                    "name": skill["name"],
                    "description": skill["description"],
                    "path": skill["path"]
                }
                for skill in skills
            ]
        },
        "context": {
            "agentsFile": "agents/AGENTS.md" if AGENTS_CONTEXT.exists() else None
        },
        "mcpServers": {
            DEFAULT_MCP_SERVER_NAME: {
                "url": mcp_url,
                "description": "Hugging Face MCP server for dataset/model operations"
            }
        }
    }
    
    # Remove None values
    if not config["context"]["agentsFile"]:
        del config["context"]
    
    return config


def write_opencode_config(config: dict) -> None:
    """Write opencode.json with pretty formatting"""
    OPENCODE_CONFIG.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate OpenCode configuration from skill metadata"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if generated config matches existing (exit 1 if different)"
    )
    args = parser.parse_args()
    
    try:
        new_config = build_opencode_config()
        
        if args.check:
            if not OPENCODE_CONFIG.exists():
                print(f"Missing: {OPENCODE_CONFIG}", file=sys.stderr)
                print("Run: ./scripts/publish.sh", file=sys.stderr)
                return 1
            
            existing = load_json(OPENCODE_CONFIG)
            if existing != new_config:
                print(f"Outdated: {OPENCODE_CONFIG}", file=sys.stderr)
                print("Run: ./scripts/publish.sh", file=sys.stderr)
                return 1
            
            print(f"✓ {OPENCODE_CONFIG.name} is up to date")
            return 0
        
        write_opencode_config(new_config)
        print(f"Generated: {OPENCODE_CONFIG}")
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
