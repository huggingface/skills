#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Offline paper-manager contracts; no credentials, network or package installs."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch


SCRIPT = Path(__file__).resolve().parent.parent / "skills/huggingface-paper-publisher/scripts/paper_manager.py"


class PaperManagerReliabilityTests(unittest.TestCase):
    def setUp(self):
        hub = types.ModuleType("huggingface_hub")
        hub.HfApi = MagicMock()
        hub.hf_hub_download = MagicMock()
        hub.get_token = lambda: None
        requests = types.ModuleType("requests")
        requests.RequestException = RuntimeError
        requests.get = MagicMock()
        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = lambda: False
        with patch.dict(sys.modules, {
            "huggingface_hub": hub, "requests": requests,
            "dotenv": dotenv, "yaml": types.ModuleType("yaml"),
        }):
            spec = importlib.util.spec_from_file_location("paper_manager_under_test", SCRIPT)
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
        self.manager = self.module.PaperManager(hf_token="offline-test-token")
        self.manager.api.upload_file.return_value = types.SimpleNamespace(
            commit_url="https://huggingface.co/fake/model/commit/test",
            pr_url="https://huggingface.co/fake/model/discussions/1",
        )
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.readme = self.root / "README.md"
        self.readme.write_text("---\nlanguage: en\n---\n# Model\nOriginal content\n", encoding="utf-8")
        hub.hf_hub_download.return_value = str(self.readme)
        self.output = io.StringIO()
        self.addCleanup(patch.stopall)
        patch("socket.socket.connect", side_effect=AssertionError("network forbidden")).start()
        patch("socket.create_connection", side_effect=AssertionError("network forbidden")).start()

    def response(self, status):
        response = MagicMock(status_code=status)
        if status >= 400:
            response.raise_for_status.side_effect = RuntimeError(f"HTTP {status}")
        self.module.requests.get.return_value = response

    def cli(self, *args):
        code = 0
        manager = self.manager
        def init(instance):
            instance.__dict__.update(manager.__dict__)
        with patch.object(sys, "argv", [str(SCRIPT), *args]), patch.object(
            self.module.PaperManager, "__init__", init
        ), redirect_stdout(self.output), redirect_stderr(self.output):
            try:
                result = self.module.main()
                code = result if result is not None else 0
            except SystemExit as error:
                code = error.code
        return code

    def test_requested_pr_is_forwarded_and_result_identifies_review(self):
        with redirect_stdout(self.output):
            result = self.manager.link_paper_to_repo("fake/model", "2301.12345", create_pr=True)
        kwargs = self.manager.api.upload_file.call_args.kwargs
        self.assertIs(kwargs.get("create_pr"), True)
        self.assertEqual(result["pr_url"], "https://huggingface.co/fake/model/discussions/1")
        self.assertIn("Original content", kwargs["path_or_fileobj"].decode())

    def test_direct_link_remains_a_direct_commit(self):
        with redirect_stdout(self.output):
            result = self.manager.link_paper_to_repo("fake/model", "2301.12345")
        self.assertFalse(self.manager.api.upload_file.call_args.kwargs.get("create_pr", False))
        self.assertEqual(result["status"], "success")

    def test_rejected_pr_never_falls_back_to_direct_upload(self):
        self.manager.api.upload_file.side_effect = PermissionError("denied")
        with redirect_stdout(self.output):
            result = self.manager.link_paper_to_repo("fake/model", "2301.12345", create_pr=True)
        self.assertEqual(result["status"], "error")
        self.manager.api.upload_file.assert_called_once()
        self.assertIs(self.manager.api.upload_file.call_args.kwargs.get("create_pr"), True)

    def test_missing_pr_url_is_not_a_success(self):
        self.manager.api.upload_file.return_value = types.SimpleNamespace(pr_url=None)
        with redirect_stdout(self.output):
            result = self.manager.link_paper_to_repo("fake/model", "2301.12345", create_pr=True)
        self.assertEqual(result["status"], "error")
        self.assertIn("before retrying", result["message"])
        self.manager.api.upload_file.assert_called_once()

    def test_cli_upload_failure_is_nonzero(self):
        self.manager.api.upload_file.side_effect = PermissionError("denied")
        self.assertNotEqual(self.cli("link", "--repo-id", "fake/model", "--arxiv-id", "2301.12345"), 0)

    def test_cli_batch_reports_any_failed_item(self):
        self.assertNotEqual(self.cli("link", "--repo-id", "fake/model", "--arxiv-ids", "2301.12345,invalid"), 0)

    def test_http_service_failure_is_not_missing_paper(self):
        self.response(503)
        with redirect_stdout(self.output):
            index = self.manager.index_paper("2301.12345")
        check = self.manager.check_paper("2301.12345")
        self.assertEqual(index["status"], "error")
        self.assertIn("error", check)
        self.assertIsNone(check["exists"])
        self.assertIn("503", check["error"])

    def test_not_found_preserves_explicit_pending_index_action(self):
        self.response(404)
        with redirect_stdout(self.output):
            index = self.manager.index_paper("2301.12345")
        self.assertEqual(index["status"], "not_indexed")
        self.assertFalse(self.manager.check_paper("2301.12345")["exists"])
        self.assertNotEqual(self.cli("index", "--arxiv-id", "2301.12345"), 0)

    def test_cli_http_failure_is_nonzero(self):
        self.response(429)
        self.assertNotEqual(self.cli("check", "--arxiv-id", "2301.12345"), 0)
        self.assertNotEqual(self.cli("index", "--arxiv-id", "2301.12345"), 0)

    def test_cli_existing_paper_succeeds(self):
        self.response(200)
        self.assertEqual(self.cli("check", "--arxiv-id", "2301.12345"), 0)
        self.assertEqual(self.cli("index", "--arxiv-id", "2301.12345"), 0)

    def test_legacy_arxiv_citation_uses_year_after_category(self):
        self.manager.get_arxiv_info = MagicMock(return_value={"title": "Legacy Paper", "authors": ["Alice"]})
        citation = self.manager.generate_citation("hep-th/9901001")
        self.assertIn("year={1999}", citation)
        self.assertIn("title={Legacy Paper}", citation)
        self.assertIn("author={Alice}", citation)

    def test_modern_citation_keeps_year(self):
        self.manager.get_arxiv_info = MagicMock(return_value={"title": "Modern Paper", "authors": ["Alice"]})
        self.assertIn("year={2023}", self.manager.generate_citation("2301.12345v2"))

    def test_versioned_legacy_citation_keeps_year(self):
        self.manager.get_arxiv_info = MagicMock(return_value={"title": "Legacy", "authors": ["Alice"]})
        self.assertIn("year={2001}", self.manager.generate_citation("math/0101001v2"))

    def test_cli_invalid_citation_is_nonzero(self):
        self.assertNotEqual(self.cli("citation", "--arxiv-id", "invalid"), 0)

    def test_unimplemented_citation_formats_are_nonzero(self):
        self.manager.get_arxiv_info = MagicMock(return_value={"title": "Paper", "authors": ["Alice"]})
        for style in ("apa", "mla"):
            with self.subTest(style=style):
                self.assertNotEqual(self.cli("citation", "--arxiv-id", "2301.12345", "--format", style), 0)

    def test_cli_missing_template_is_nonzero_without_output(self):
        output = self.root / "paper.md"
        self.assertNotEqual(self.cli("create", "--template", "missing", "--title", "Local", "--output", str(output)), 0)
        self.assertFalse(output.exists())

    def test_local_creation_still_succeeds(self):
        output = self.root / "paper.md"
        self.assertEqual(self.cli("create", "--template", "standard", "--title", "Local", "--output", str(output)), 0)
        self.assertIn("# Local", output.read_text(encoding="utf-8"))

    def test_search_stub_cannot_report_command_success(self):
        self.assertNotEqual(self.cli("search", "--query", "local query"), 0)

    def test_fresh_process_entrypoint_propagates_failure_exit(self):
        bootstrap = """
import runpy, sys, types
from unittest.mock import Mock
hub = types.ModuleType('huggingface_hub')
hub.HfApi = Mock()
hub.get_token = lambda: None
hub.hf_hub_download = Mock(side_effect=PermissionError('synthetic denied'))
requests = types.ModuleType('requests')
requests.RequestException = RuntimeError
dotenv = types.ModuleType('dotenv')
dotenv.load_dotenv = lambda: False
sys.modules.update(huggingface_hub=hub, requests=requests, dotenv=dotenv, yaml=types.ModuleType('yaml'))
sys.argv = [sys.argv[1], 'link', '--repo-id', 'fake/model', '--arxiv-id', '2301.12345']
runpy.run_path(sys.argv[0], run_name='__main__')
"""
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-B", "-X", "utf8", "-c", bootstrap, str(SCRIPT)],
            cwd=self.root, capture_output=True, text=True, timeout=30,
            env={key: value for key, value in os.environ.items() if key != "HF_TOKEN"},
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('"status": "error"', result.stdout)
        self.assertIn("synthetic denied", result.stdout)


if __name__ == "__main__":
    unittest.main()
