#!/usr/bin/env python3
"""check_toc — validate every internal anchor link in kit/AGENTS.md.

AGENTS.md is ASSEMBLED (skeleton + section fragments) and its table of
contents lives in the skeleton — heading edits in any fragment can silently
break TOC anchors (this exact drift shipped once: acceptance round R1,
2026-09-26). This checker makes drift loud.

What it validates (against the SPLICED kit/AGENTS.md, i.e. what consumers read):
  1. every markdown link of the form ](#anchor) resolves to a real heading
     (GitHub-style slug: lowercase, punctuation stripped, spaces -> hyphens,
     duplicates get -1/-2 suffixes; headings inside fenced code blocks don't
     count — GitHub doesn't anchor them either)
  2. the Contents TOC exists at all (>= 1 internal anchor link) — a splice
     that dropped the skeleton would otherwise pass silently

Exit codes: 0 = all anchors resolve; 1 = drift (stale/broken anchor, duplicate
heading slug, or no TOC found). Run after EVERY `splice_agents_md.py`:

    python3 kit/tools/splice_agents_md.py && python3 kit/tools/check_toc.py
"""
from __future__ import annotations

import os
import re
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(KIT, "AGENTS.md")


def github_slug(text: str) -> str:
    """GitHub's anchor algorithm (github-slugger): lowercase; drop anything
    that is not a word char, hyphen or space; EACH space becomes one hyphen
    (no collapsing). 'TL;DR — the free stack' -> 'tldr--the-free-stack'
    (the em-dash drops, leaving 'dr' + space + space + 'the' -> 'dr--the')."""
    s = text.strip().lower()
    s = re.sub(r"[^\w\- ]", "", s, flags=re.UNICODE)
    return s.replace(" ", "-").strip("-")


def strip_code_fences(doc: str) -> str:
    """Remove fenced code blocks — GitHub creates no anchors for # lines
    inside them (AGENTS.md quick-wins blocks are full of those)."""
    out, in_fence = [], False
    for line in doc.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def heading_slugs(doc: str) -> dict[str, str]:
    """{slug: heading text} with GitHub's duplicate rule (-1, -2, ...)."""
    slugs: dict[str, str] = {}
    for m in re.finditer(r"^(#{1,6})\s+(.+?)\s*#*\s*$", doc, flags=re.MULTILINE):
        slug = github_slug(m.group(2))
        if not slug:
            continue
        if slug in slugs:  # GitHub appends -1, -2, ... on repeats
            n = 1
            while f"{slug}-{n}" in slugs:
                n += 1
            slug = f"{slug}-{n}"
        slugs[slug] = m.group(2)
    return slugs


def main() -> int:
    if not os.path.isfile(DOC):
        print(f"check_toc: {DOC} not found — run splice_agents_md.py first",
              file=sys.stderr)
        return 1
    with open(DOC, encoding="utf-8") as f:
        doc = f.read()

    prose = strip_code_fences(doc)
    slugs = heading_slugs(prose)

    # every internal anchor link in the doc (TOC + any in-body ](#...) links)
    links = re.findall(r"\]\(#([^)]+)\)", doc)
    if not links:
        print("check_toc: FAIL — no internal anchor links found (Contents TOC "
              "missing? skeleton not spliced in?)", file=sys.stderr)
        return 1

    broken = []
    for anchor in links:
        if anchor not in slugs:
            broken.append(anchor)

    dup_sources = len(slugs) != len({github_slug(t) for t in slugs.values()})
    print(f"check_toc: {len(links)} internal anchor link(s) vs "
          f"{len(slugs)} heading(s) — "
          + ("ALL RESOLVE" if not broken else f"{len(broken)} BROKEN"))
    for anchor in broken:
        # help the fixer: nearest real heading by prefix
        hint = [s for s in slugs if s.startswith(anchor[:12])] or \
               [s for s in slugs if anchor[:8] in s]
        extra = f" (closest heading: #{hint[0]})" if hint else ""
        print(f"  BROKEN: #{anchor}{extra}", file=sys.stderr)
    if dup_sources:
        print("check_toc: NOTE — duplicate headings present; GitHub appends "
              "-1/-2 suffixes to their anchors (handled)", file=sys.stderr)
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
