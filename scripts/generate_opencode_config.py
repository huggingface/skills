#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Generate OpenCode config from existing repo metadata.

Output:
- opencode.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CLAUDE_PLUGIN_MANIFEST = ROOT / ".claude-plugin" / "plugin.json"
GEMINI_EXTENSION = ROOT / "gemini-extension.json"
MCP_CONFIG = ROOT / ".mcp.json"
OPENCODE_CONFIG = ROOT / "opencode.json"

OPENCODE_CONFIG_VERSION = "0.1.0"
DEFAULT_CONTEXT_FILE = "agents/AGENTS.md"


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def collect_skill_paths() -> list[str]:
    paths: list[str] = []
    for skill_md in sorted(ROOT.glob("skills/*/SKILL.md")):
        paths.append(str(skill_md.parent.relative_to(ROOT)))
    return paths


def extract_context_file() -> str:
    if not GEMINI_EXTENSION.exists():
        return DEFAULT_CONTEXT_FILE

    data = load_json(GEMINI_EXTENSION)
    context_file = data.get("contextFileName")
    if not isinstance(context_file, str) or not context_file.strip():
        return DEFAULT_CONTEXT_FILE

    return context_file


def extract_mcp_servers() -> dict:
    if MCP_CONFIG.exists():
        data = load_json(MCP_CONFIG)
        mcp_servers = data.get("mcpServers")
        if isinstance(mcp_servers, dict) and mcp_servers:
            return mcp_servers

    if GEMINI_EXTENSION.exists():
        data = load_json(GEMINI_EXTENSION)
        mcp_servers = data.get("mcpServers")
        if isinstance(mcp_servers, dict) and mcp_servers:
            normalized = {}
            for server_name, cfg in mcp_servers.items():
                if not isinstance(cfg, dict):
                    continue
                url = cfg.get("url") or cfg.get("httpUrl")
                if isinstance(url, str) and url.strip():
                    normalized[server_name] = {"url": url}
            if normalized:
                return normalized

    return {}


def build_opencode_config() -> dict:
    plugin_manifest = load_json(CLAUDE_PLUGIN_MANIFEST)
    skill_paths = collect_skill_paths()
    if not skill_paths:
        raise ValueError("No skills discovered under skills/*/SKILL.md")

    name = plugin_manifest.get("name")
    description = plugin_manifest.get("description")
    if not isinstance(name, str) or not name:
        raise ValueError(".claude-plugin/plugin.json must define a non-empty 'name'")
    if not isinstance(description, str) or not description:
        raise ValueError(".claude-plugin/plugin.json must define a non-empty 'description'")

    config = {
        "name": name,
        "description": description,
        "version": OPENCODE_CONFIG_VERSION,
        "skills": "skills",
        "skillPaths": skill_paths,
        "contextFileName": extract_context_file(),
        "mcpServers": extract_mcp_servers(),
    }

    for key in ["homepage", "repository", "license", "keywords", "author"]:
        if key in plugin_manifest:
            config[key] = plugin_manifest[key]

    return config


def render_json(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_or_check(path: Path, content: str, check: bool) -> bool:
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current == content:
        return True

    if check:
        return False

    path.write_text(content, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate OpenCode config")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate opencode.json is up-to-date without writing changes.",
    )
    args = parser.parse_args()

    content = render_json(build_opencode_config())
    ok = write_or_check(OPENCODE_CONFIG, content, check=args.check)

    if args.check:
        if not ok:
            print("OpenCode config is out of date:", file=sys.stderr)
            print(f"  - {OPENCODE_CONFIG.relative_to(ROOT)}", file=sys.stderr)
            print("Run: uv run scripts/generate_opencode_config.py", file=sys.stderr)
            sys.exit(1)
        print("OpenCode config is up to date.")
        return

    print(f"Wrote {OPENCODE_CONFIG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
