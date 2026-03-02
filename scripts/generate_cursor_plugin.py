#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Generate Cursor plugin artifacts from existing repo metadata.

Outputs:
- .cursor-plugin/plugin.json
- .mcp.json

Design goals:
- Keep Claude + Cursor metadata in sync.
- Reuse .claude-plugin/plugin.json as primary metadata source.
- Discover skills from skills/*/SKILL.md.
- Reuse MCP URL from gemini-extension.json when available.
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
CURSOR_PLUGIN_DIR = ROOT / ".cursor-plugin"
CURSOR_PLUGIN_MANIFEST = CURSOR_PLUGIN_DIR / "plugin.json"
CURSOR_MCP_CONFIG = ROOT / ".mcp.json"

DEFAULT_MCP_SERVER_NAME = "huggingface-skills"
DEFAULT_MCP_URL = "https://huggingface.co/mcp?login"

PLUGIN_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")


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
        data[key.strip()] = value.strip()
    return data


def collect_skills() -> list[str]:
    skills: list[str] = []
    for skill_md in sorted(ROOT.glob("skills/*/SKILL.md")):
        meta = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        name = meta.get("name", "").strip()
        if not name:
            continue
        skills.append(name)
    return skills


def validate_plugin_name(name: str) -> None:
    if not PLUGIN_NAME_RE.match(name):
        raise ValueError(
            "Invalid plugin name in .claude-plugin/plugin.json: "
            f"'{name}'. Must be lowercase and match {PLUGIN_NAME_RE.pattern}"
        )


def build_cursor_plugin_manifest() -> dict:
    src = load_json(CLAUDE_PLUGIN_MANIFEST)

    name = src.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError(".claude-plugin/plugin.json must define a non-empty 'name'")
    validate_plugin_name(name)

    skills = collect_skills()
    if not skills:
        raise ValueError("No skills discovered under skills/*/SKILL.md")

    manifest: dict = {"name": name, "skills": "skills", "mcpServers": ".mcp.json"}

    # Copy optional metadata fields when present.
    for key in [
        "description",
        "version",
        "author",
        "homepage",
        "repository",
        "license",
        "keywords",
        "logo",
    ]:
        if key in src:
            manifest[key] = src[key]

    return manifest


def extract_mcp_from_gemini() -> tuple[str, str]:
    """Return (server_name, url) from gemini-extension when available."""
    if not GEMINI_EXTENSION.exists():
        return DEFAULT_MCP_SERVER_NAME, DEFAULT_MCP_URL

    data = load_json(GEMINI_EXTENSION)
    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        return DEFAULT_MCP_SERVER_NAME, DEFAULT_MCP_URL

    # Use first configured server as source of truth.
    server_name = next(iter(servers.keys()))
    server_cfg = servers[server_name]
    if not isinstance(server_cfg, dict):
        return DEFAULT_MCP_SERVER_NAME, DEFAULT_MCP_URL

    url = server_cfg.get("url") or server_cfg.get("httpUrl") or DEFAULT_MCP_URL
    if not isinstance(url, str) or not url.strip():
        url = DEFAULT_MCP_URL

    return server_name, url


def build_mcp_config() -> dict:
    server_name, url = extract_mcp_from_gemini()
    return {
        "mcpServers": {
            server_name: {
                "url": url,
            }
        }
    }


def render_json(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_or_check(path: Path, content: str, check: bool) -> bool:
    """Return True when file is already up-to-date (or after writing in non-check mode)."""
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current == content:
        return True

    if check:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Cursor plugin manifest + MCP config")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate generated files are up-to-date without writing changes.",
    )
    args = parser.parse_args()

    plugin_manifest = render_json(build_cursor_plugin_manifest())
    mcp_config = render_json(build_mcp_config())

    ok_plugin = write_or_check(CURSOR_PLUGIN_MANIFEST, plugin_manifest, check=args.check)
    ok_mcp = write_or_check(CURSOR_MCP_CONFIG, mcp_config, check=args.check)

    if args.check:
        outdated = []
        if not ok_plugin:
            outdated.append(str(CURSOR_PLUGIN_MANIFEST.relative_to(ROOT)))
        if not ok_mcp:
            outdated.append(str(CURSOR_MCP_CONFIG.relative_to(ROOT)))

        if outdated:
            print("Generated Cursor artifacts are out of date:", file=sys.stderr)
            for item in outdated:
                print(f"  - {item}", file=sys.stderr)
            print("Run: uv run scripts/generate_cursor_plugin.py", file=sys.stderr)
            sys.exit(1)

        print("Cursor plugin artifacts are up to date.")
        return

    print(f"Wrote {CURSOR_PLUGIN_MANIFEST.relative_to(ROOT)}")
    print(f"Wrote {CURSOR_MCP_CONFIG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
