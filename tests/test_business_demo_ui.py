"""Static contract of the new LD demo page; no browser network is required."""
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from nomenclature_matcher.business_demo import business_page

PAGE = Path(__file__).resolve().parents[1] / "src" / "nomenclature_matcher" / "business_demo.html"


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = {}
        self.links = []
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if "id" in d:
            if d["id"] in self.ids:
                raise AssertionError("Duplicate HTML id: " + d["id"])
            self.ids[d["id"]] = (tag, d)
        if tag == "script":
            self.links.append(d)


def test_page_contains_functional_input_results_details_and_local_history():
    html = PAGE.read_text(encoding="utf-8")
    parser = Elements()
    parser.feed(html)
    for node_id in (
        "query", "go", "file", "upload", "results", "results-summary",
        "history-open", "history-pane", "history-list",
        "history-clear", "history-close", "history-shade", "clear-input"
    ):
        assert node_id in parser.ids
    assert parser.ids["query"][0] == "textarea"
    assert parser.ids["results"][0] == "div"
    assert parser.ids["history-pane"][1].get("role") == "dialog"
    assert "INSUFFICIENT_PARAMETERS" in html
    assert "missing_fields" in html
    assert "other_candidates" in html
    assert "comparison" in html
    assert "localStorage" in html
    assert 'fetch("/v1/demo/match"' in html
    assert "Точность" not in html
    assert "retrieval_score" not in html
    assert "llm_confidence" not in html
    assert "innerHTML" not in html
    assert "<script src=" not in html
    assert "/v1/demo/match" in html


def test_ui_source_is_valid_javascript(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node.js not installed")
    source = PAGE.read_text(encoding="utf-8")
    scripts = re.findall(r"<script(?:\s[^>]*)?>([\s\S]*?)</script>", source)
    assert len(scripts) == 1
    script = tmp_path / "page.js"
    script.write_text(scripts[0], encoding="utf-8")
    checked = subprocess.run(
        ["node", "--check", str(script)],
        check=False, capture_output=True, text=True,
    )
    assert checked.returncode == 0, checked.stderr


def test_public_page_uses_static_template():
    response = business_page()
    assert response.status_code == 200
    assert "charset=utf-8" in response.media_type + ";" + (response.charset or "") or response.charset == "utf-8"
    assert b"LD" in response.body
