#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = ["huggingface_hub", "pyyaml", "requests", "python-dotenv"]
# ///

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

import requests


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "skills/huggingface-paper-publisher/scripts/paper_manager.py"
)
spec = importlib.util.spec_from_file_location("paper_manager", SCRIPT_PATH)
paper_manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paper_manager)

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>arXiv Query: id_list=1706.03762</title>
  <entry>
    <id>http://arxiv.org/abs/1706.03762v1</id>
    <title> A &amp; B </title>
    <summary> An &lt;example&gt; abstract. </summary>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
  </entry>
</feed>
"""


class PaperManagerTest(unittest.TestCase):
    def setUp(self):
        self.manager = paper_manager.PaperManager(hf_token="test-token")
        self.get = patch.object(paper_manager.requests, "get").start()
        self.addCleanup(patch.stopall)
        self.set_response(FEED)

    def set_response(self, xml):
        response = requests.Response()
        response.status_code = 200
        response.encoding = "utf-8"
        response._content = xml.encode("utf-8")
        self.get.return_value = response

    def test_reads_paper_entry_instead_of_feed_metadata(self):
        info = self.manager.get_arxiv_info("https://arxiv.org/abs/1706.03762")
        self.assertEqual(info, {
            "arxiv_id": "1706.03762",
            "title": "A & B",
            "authors": ["Alice Smith", "Bob Jones"],
            "abstract": "An <example> abstract.",
            "arxiv_url": "https://arxiv.org/abs/1706.03762",
            "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf",
        })
        self.get.assert_called_once_with(
            "https://export.arxiv.org/api/query?id_list=1706.03762", timeout=10
        )

    def test_keeps_single_author(self):
        self.set_response(FEED.replace("<author><name>Bob Jones</name></author>", ""))
        self.assertEqual(self.manager.get_arxiv_info("1706.03762")["authors"], ["Alice Smith"])

    def test_supports_prefixed_atom_elements(self):
        self.set_response("""<a:feed xmlns:a="http://www.w3.org/2005/Atom">
          <a:title>Feed title</a:title>
          <a:entry>
            <a:title type="text">Paper title</a:title>
            <a:author><a:name>René Smith</a:name></a:author>
            <a:summary>Paper abstract</a:summary>
          </a:entry>
        </a:feed>""")
        info = self.manager.get_arxiv_info("1706.03762")
        self.assertEqual(info["title"], "Paper title")
        self.assertEqual(info["authors"], ["René Smith"])
        self.assertEqual(info["abstract"], "Paper abstract")

    def test_citation_uses_paper_title_and_all_authors(self):
        citation = self.manager.generate_citation("1706.03762")
        self.assertIn("title={A & B}", citation)
        self.assertIn("author={Alice Smith and Bob Jones}", citation)
        self.assertNotIn("arXiv Query", citation)

    def test_sanitizes_text_after_decoding_xml_entities(self):
        self.set_response(FEED.replace("A &amp; B", "&#96;&#96;&#96;\n---\nA &amp; B"))
        self.assertEqual(
            self.manager.get_arxiv_info("1706.03762")["title"],
            "\\`\\`\\`\n\\---\nA & B",
        )

    def test_empty_feed_returns_error(self):
        self.set_response('<feed xmlns="http://www.w3.org/2005/Atom"><title>Feed</title></feed>')
        self.assertIn("error", self.manager.get_arxiv_info("1706.03762"))
        self.assertTrue(self.manager.generate_citation("1706.03762").startswith("Error fetching paper info:"))

    def test_arxiv_error_entry_returns_error(self):
        self.set_response("""<feed xmlns="http://www.w3.org/2005/Atom"><entry>
          <id>http://arxiv.org/api/errors#incorrect_id_format_for_1706.03762</id>
          <title>Error</title><summary>Incorrect id format</summary>
        </entry></feed>""")
        self.assertIn("error", self.manager.get_arxiv_info("1706.03762"))

    def test_malformed_xml_returns_error(self):
        self.set_response("<feed><entry>")
        self.assertIn("error", self.manager.get_arxiv_info("1706.03762"))

    def test_http_error_is_preserved(self):
        self.get.return_value.status_code = 429
        self.assertIn("429", self.manager.get_arxiv_info("1706.03762")["error"])


if __name__ == "__main__":
    unittest.main()
