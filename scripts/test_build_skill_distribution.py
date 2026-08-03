#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml==6.0.3"]
# ///

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from urllib.parse import unquote


SCRIPT_PATH = Path(__file__).with_name("build_skill_distribution.py")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def load_builder() -> ModuleType:
	spec = importlib.util.spec_from_file_location("build_skill_distribution", SCRIPT_PATH)
	if spec is None or spec.loader is None:
		raise RuntimeError(f"could not load {SCRIPT_PATH}")
	module = importlib.util.module_from_spec(spec)
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)
	return module


builder = load_builder()


def write_skill(skill_dir: Path, description: str = "Test skill") -> None:
	skill_dir.mkdir(parents=True)
	(skill_dir / "SKILL.md").write_text(
		f"---\nname: {skill_dir.name}\ndescription: {description}\nlicense: Apache-2.0\n---\n\n# Test\n",
		encoding="utf-8",
	)


class BuildSkillDistributionTest(unittest.TestCase):
	def test_writes_complete_sep_2640_resource_manifests(self) -> None:
		with tempfile.TemporaryDirectory() as temp_dir:
			root = Path(temp_dir)
			skills_dir = root / "skills"
			out_dir = root / "out"

			single = skills_dir / "single"
			write_skill(single, "Single-file skill")

			multi = skills_dir / "multi"
			write_skill(multi, "Multi-file skill")
			(multi / "references").mkdir()
			(multi / "references" / "guide.md").write_text("# Guide\r\n", encoding="utf-8", newline="")
			(multi / "assets").mkdir()
			binary_payload = b"line1\r\nline2\x00\xff\n"
			(multi / "assets" / "raw data.bin").write_bytes(binary_payload)
			(multi / "node_modules").mkdir()
			(multi / "node_modules" / "ignored.js").write_text("ignored", encoding="utf-8")
			(multi / ".DS_Store").write_bytes(b"ignored")

			builder.build_distribution(skills_dir, out_dir, "skill://")

			payload = json.loads((out_dir / "skills.json").read_text(encoding="utf-8"))
			entries = {entry["frontmatter"]["name"]: entry for entry in payload["skills"]}
			self.assertEqual(set(entries), {"multi", "single"})

			for skill_name, expected_paths in {
				"single": {"SKILL.md"},
				"multi": {"SKILL.md", "assets/raw data.bin", "references/guide.md"},
			}.items():
				entry = entries[skill_name]
				self.assertEqual(set(entry), {"uri", "frontmatter", "resources"})
				self.assertEqual(entry["uri"], f"skill://{skill_name}/SKILL.md")
				self.assertEqual(entry["frontmatter"]["license"], "Apache-2.0")

				resources = entry["resources"]
				self.assertEqual(len(resources), len(expected_paths))
				self.assertEqual(len({resource["uri"] for resource in resources}), len(resources))
				self.assertIn(entry["uri"], {resource["uri"] for resource in resources})

				actual_paths = {
					unquote(resource["uri"].split(f"skill://{skill_name}/", maxsplit=1)[1])
					for resource in resources
				}
				self.assertEqual(actual_paths, expected_paths)

				for resource in resources:
					self.assertRegex(resource["digest"], DIGEST_RE)
					relative_uri = resource["uri"].split(f"skill://{skill_name}/", maxsplit=1)[1]
					relative_path = unquote(relative_uri)
					source_bytes = (skills_dir / skill_name / relative_path).read_bytes()
					published_path = out_dir / skill_name / relative_path
					self.assertEqual(published_path.read_bytes(), source_bytes)
					expected_digest = "sha256:" + hashlib.sha256(published_path.read_bytes()).hexdigest()
					self.assertEqual(resource["digest"], expected_digest)

			binary_resource = next(
				resource for resource in entries["multi"]["resources"] if resource["uri"].endswith("raw%20data.bin")
			)
			self.assertEqual(binary_resource["digest"], "sha256:" + hashlib.sha256(binary_payload).hexdigest())
			self.assertFalse((out_dir / "multi" / "node_modules").exists())
			self.assertFalse((out_dir / "multi" / ".DS_Store").exists())

			legacy = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))
			self.assertEqual(len(legacy["skills"]), 2)
			self.assertTrue((out_dir / "multi.tar.gz").is_file())

			manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
			self.assertEqual(manifest["artifacts"]["skills_catalog"], "skills.json")

	def test_rejects_non_string_metadata_values(self) -> None:
		with tempfile.TemporaryDirectory() as temp_dir:
			root = Path(temp_dir)
			skill_dir = root / "skills" / "invalid"
			skill_dir.mkdir(parents=True)
			(skill_dir / "SKILL.md").write_text(
				"---\n"
				"name: invalid\n"
				"description: Invalid metadata fixture\n"
				"metadata:\n"
				"  tags:\n"
				"    - one\n"
				"---\n",
				encoding="utf-8",
			)
			with self.assertRaisesRegex(ValueError, "metadata must map string keys to string values"):
				builder.build_distribution(root / "skills", root / "out", "skill://")


if __name__ == "__main__":
	unittest.main()
