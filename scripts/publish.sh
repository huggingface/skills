#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

GENERATED_FILES=(
  "agentsmd/AGENTS.md"
  "README.md"
  ".claude-plugin/marketplace-internal.json"
  ".cursor-plugin/plugin.json"
  ".mcp.json"
)

file_sig() {
  local path="$1"
  if [[ -f "$path" ]]; then
    sha256sum "$path" | awk '{print $1}'
  else
    echo "__MISSING__"
  fi
}

run_generate() {
  uv run scripts/generate_agents.py
  uv run scripts/generate_cursor_plugin.py
}

default_base_ref() {
  if [[ -n "${PUBLISH_BASE_REF:-}" ]]; then
    echo "$PUBLISH_BASE_REF"
  elif git rev-parse --verify --quiet origin/main >/dev/null; then
    echo "origin/main"
  else
    echo "main"
  fi
}

run_publish() {
  local base_ref
  base_ref="$(default_base_ref)"
  uv run scripts/plugin_versions.py bump-if-needed "$base_ref"
  run_generate
}

run_check() {
  local before=()
  local changed=()

  for path in "${GENERATED_FILES[@]}"; do
    before+=("$(file_sig "$path")")
  done

  run_generate

  for i in "${!GENERATED_FILES[@]}"; do
    local path="${GENERATED_FILES[$i]}"
    if [[ "${before[$i]}" != "$(file_sig "$path")" ]]; then
      changed+=("$path")
    fi
  done

  if [[ ${#changed[@]} -gt 0 ]]; then
    echo "Generated artifacts are outdated."
    echo "Run: ./scripts/publish.sh"
    echo
    echo "Changed files:"
    for path in "${changed[@]}"; do
      echo "$path"
    done
    exit 1
  fi

  # Extra explicit check for cursor-only artifacts
  uv run scripts/generate_cursor_plugin.py --check
  uv run scripts/plugin_versions.py check

  echo "All generated artifacts are up to date."
}

case "${1:-}" in
  "")
    run_publish
    echo "Publish artifacts generated successfully."
    ;;
  "--check")
    run_check
    ;;
  "-h"|"--help")
    cat <<'EOF'
Usage:
  ./scripts/publish.sh         Generate all publish artifacts
  ./scripts/publish.sh --check Verify generated artifacts are up to date

Set PUBLISH_BASE_REF to override the base used for automatic version bumps.

This script regenerates:
  - agentsmd/AGENTS.md
  - README.md (skills table section)
  - .claude-plugin/marketplace-internal.json
  - .cursor-plugin/plugin.json
  - .mcp.json

Versioned manifests are validated with scripts/plugin_versions.py.
EOF
    ;;
  *)
    echo "Unknown option: $1" >&2
    echo "Use --help for usage." >&2
    exit 2
    ;;
esac
