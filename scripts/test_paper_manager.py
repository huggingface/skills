#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "huggingface_hub",
#     "pyyaml",
#     "requests",
#     "python-dotenv",
# ]
# ///
"""Offline tests for skills/huggingface-paper-publisher/scripts/paper_manager.py.

No network access and no HF token are needed: the README download is patched
and HfApi is replaced with a mock.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

from huggingface_hub import CommitInfo


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "huggingface-paper-publisher"
    / "scripts"
    / "paper_manager.py"
)

ARXIV_ID = "2301.12345"
REPO_ID = "user/model"
PR_URL = f"https://huggingface.co/{REPO_ID}/discussions/1"


def load_paper_manager() -> ModuleType:
    spec = importlib.util.spec_from_file_location("paper_manager", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


paper_manager = load_paper_manager()


class LinkPaperCreatePrTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        readme = Path(tmp.name) / "README.md"
        readme.write_text("---\nlicense: mit\n---\n\n# My model\n", encoding="utf-8")

        patcher = mock.patch.object(paper_manager, "hf_hub_download", return_value=str(readme))
        patcher.start()
        self.addCleanup(patcher.stop)

        self.manager = paper_manager.PaperManager(hf_token="dummy-token")
        self.manager.api = mock.Mock()

    def _link(self, commit_info: CommitInfo, **kwargs):
        self.manager.api.upload_file.return_value = commit_info
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = self.manager.link_paper_to_repo(repo_id=REPO_ID, arxiv_id=ARXIV_ID, **kwargs)
        return result, stdout.getvalue()

    def test_create_pr_forwards_flag_and_reports_pr_url(self) -> None:
        commit_info = CommitInfo(
            commit_url=f"https://huggingface.co/{REPO_ID}/commit/abc123",
            commit_message="msg",
            commit_description="",
            oid="abc123",
            pr_url=PR_URL,
        )

        result, output = self._link(commit_info, create_pr=True)

        self.manager.api.upload_file.assert_called_once()
        self.assertIs(self.manager.api.upload_file.call_args.kwargs.get("create_pr"), True)
        self.assertIn(PR_URL, output)
        self.assertNotIn("not yet implemented", output)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result.get("pr_url"), PR_URL)

    def test_default_commits_directly(self) -> None:
        commit_info = CommitInfo(
            commit_url=f"https://huggingface.co/{REPO_ID}/commit/abc123",
            commit_message="msg",
            commit_description="",
            oid="abc123",
        )

        result, output = self._link(commit_info)

        self.manager.api.upload_file.assert_called_once()
        kwargs = self.manager.api.upload_file.call_args.kwargs
        self.assertIsNot(kwargs.get("create_pr"), True)
        self.assertEqual(kwargs["repo_id"], REPO_ID)
        self.assertEqual(kwargs["path_in_repo"], "README.md")
        self.assertEqual(kwargs["commit_message"], f"Add paper reference: arXiv:{ARXIV_ID}")
        self.assertIn(f"https://arxiv.org/abs/{ARXIV_ID}", kwargs["path_or_fileobj"].decode("utf-8"))
        self.assertEqual(result["status"], "success")
        self.assertNotIn("pr_url", result)
        self.assertIn("Successfully linked paper", output)


if __name__ == "__main__":
    unittest.main()
