#!/usr/bin/env python3
"""splice AGENTS.md — IDEMPOTENT: rebuilds kit/AGENTS.md from
kit/docs/AGENTS-skeleton.md + kit/docs/sections/*.md fragments.

The skeleton carries <!-- SECTION:name --> markers; each fragment file
sections/<name>.md is inserted after its marker. Run as often as you like —
output is always freshly rebuilt, never duplicated.
"""
import os
import re
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
skeleton = os.path.join(KIT, "docs", "AGENTS-skeleton.md")
sections_dir = os.path.join(KIT, "docs", "sections")
out_path = os.path.join(KIT, "AGENTS.md")

with open(skeleton, encoding="utf-8") as f:
    doc = f.read()

markers = re.findall(r"<!-- SECTION:([a-z-]+) -->", doc)
missing = [n for n in markers
           if not os.path.isfile(os.path.join(sections_dir, f"{n}.md"))]
for name in markers:
    path = os.path.join(sections_dir, f"{name}.md")
    if not os.path.isfile(path):
        continue
    with open(path, encoding="utf-8") as f:
        frag = f.read().strip()
    # fragments may carry their own SECTION markers — strip them (the skeleton
    # provides the marker; duplicates confused readers and grep tooling)
    frag = re.sub(r"<!--\s*/?\s*SECTION:[a-z-]+\s*-->\n?", "", frag).strip()
    doc = doc.replace(f"<!-- SECTION:{name} -->",
                      f"<!-- SECTION:{name} -->\n\n{frag}\n")

extra = sorted(f[:-3] for f in os.listdir(sections_dir)
               if f.endswith(".md") and f[:-3] not in markers
               and f != "AGENTS-skeleton.md")

with open(out_path, "w", encoding="utf-8") as f:
    f.write(doc)

print(f"spliced {len(markers)} sections -> {out_path} "
      f"({os.path.getsize(out_path)} bytes, {len(doc.splitlines())} lines)")
if missing:
    print(f"WARN missing fragments: {missing}")
if extra:
    print(f"WARN fragments without markers (NOT included): {extra}")
sys.exit(1 if (missing or extra) else 0)
