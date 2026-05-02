"""Stdlib unittest suite for the AHPRA-shaped HTML → text pipeline.

The regulator corpus is the most compliance-critical of the three; chunk
quality on AHPRA pages directly affects which generated phrases pass the
guardrails. These tests lock in the pipeline's behavior on the kinds of
pages AHPRA / FTC / PMC actually serve.

Run from repo root:

    python -m unittest discover -s middleware/Regulated-Healthcare-DAGS/tests -v
"""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

# Stub `requests` — chunk_via_ragmgmt imports it at module load but we don't
# call any HTTP code in these tests.
sys.modules.setdefault("requests", types.ModuleType("requests"))


def _load_chunk_module():
    path = (
        Path(__file__).parent.parent / "handlers" / "chunk_via_ragmgmt.py"
    ).resolve()
    spec = importlib.util.spec_from_file_location("chunk_via_ragmgmt", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_AHPRA_FIXTURE = """<!DOCTYPE html>
<html><head>
<title>AHPRA: Advertising guidelines</title>
<style>.cookie { display:none; }</style>
<script>window.dataLayer=[];</script>
</head>
<body>
<a class="skip-link" href="#main">Skip to main content</a>
<header>
  <div class="masthead">AHPRA — Australian Health Practitioner Regulation Agency</div>
  <nav><ul class="breadcrumb"><li>Home</li><li>Resources</li><li>Advertising hub</li></ul></nav>
  <form class="site-search"><input name="q"/><button>Search</button></form>
</header>

<main>
  <article>
    <h1>Advertising guidelines for regulated health services</h1>
    <p>Health practitioners advertising regulated health services must comply with the National Law. Advertising must not include testimonials, must not be misleading, and must not create unrealistic expectations of beneficial treatment.</p>
    <h2>Testimonials</h2>
    <p>Section 133 of the National Law prohibits the use of testimonials in the advertising of a regulated health service.</p>
    <h2>Misleading claims</h2>
    <p>Advertising must not be false, misleading or deceptive, or likely to be misleading or deceptive. Practitioners are responsible for substantiating any claim made in advertising.</p>
  </article>
</main>

<aside class="sidebar">
  <h3>Related resources</h3>
  <ul><li>Self-assessment tool</li><li>Common breaches</li></ul>
</aside>

<footer>
  <div>About AHPRA · Site map · Privacy · Cookies</div>
</footer>

<dialog class="cookie-banner">We use cookies. <button>Accept</button></dialog>
</body></html>"""


class TestHtmlToText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_chunk_module()

    def test_substantive_regulator_content_preserved(self):
        text = self.mod._html_to_text(_AHPRA_FIXTURE)
        for phrase in (
            "National Law",
            "testimonials",
            "Section 133",
            "misleading or deceptive",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_chrome_dropped(self):
        text = self.mod._html_to_text(_AHPRA_FIXTURE)
        for noise in (
            "Skip to main content",
            "Home",
            "Resources",
            "Advertising hub",
            "Self-assessment",
            "Common breaches",
            "About AHPRA",
            "Site map",
            "Cookies",
            "We use cookies",
            "Accept",
        ):
            with self.subTest(noise=noise):
                self.assertNotIn(noise, text)

    def test_no_main_or_article_falls_through(self):
        # When neither <main> nor <article> exists the chrome stripper still runs
        # on the whole body, so headers/footers still go but the text flows from
        # raw <p> blocks.
        html = """<html><body>
            <header>nav junk</header>
            <p>Substantive paragraph one with regulatory content.</p>
            <p>Substantive paragraph two referencing the National Law.</p>
            <footer>copyright junk</footer>
          </body></html>"""
        text = self.mod._html_to_text(html)
        self.assertIn("Substantive paragraph one", text)
        self.assertIn("National Law", text)
        self.assertNotIn("nav junk", text)
        self.assertNotIn("copyright junk", text)

    def test_short_main_is_ignored_in_favor_of_full_doc(self):
        # Some sites wrap a header rail in <main>. The extractor should reject a
        # tiny <main> and fall through to the chrome-stripped whole document.
        html = """<html><body>
          <main>tiny</main>
          <article>
            <p>This is the actual article body and it is several hundred characters long because the substantive guidance lives here, not inside the misnamed main rail.""" + ("X" * 150) + """</p>
          </article>
        </body></html>"""
        text = self.mod._html_to_text(html)
        self.assertIn("substantive guidance", text)

    def test_paragraph_boundaries_preserved(self):
        # The chunker depends on \\n\\n boundaries to split parents.
        text = self.mod._html_to_text(_AHPRA_FIXTURE)
        # At least 4 paragraphs in our fixture: title, 2 body paras, 2 H2 + paras.
        self.assertGreaterEqual(text.count("\n\n"), 3)

    def test_html_entities_unescaped(self):
        html = "<html><body><article><p>What&#39;s required &amp; expected.</p></article></body></html>"
        text = self.mod._html_to_text(html)
        self.assertIn("What's required & expected.", text)

    def test_script_and_style_dropped(self):
        html = """<html><body>
          <script>var malicious = 1; alert('boom');</script>
          <style>.x { color: red; }</style>
          <article><p>Visible regulator content.</p></article>
        </body></html>"""
        text = self.mod._html_to_text(html)
        self.assertNotIn("malicious", text)
        self.assertNotIn("alert", text)
        self.assertNotIn("color: red", text)
        self.assertIn("Visible regulator content", text)

    def test_empty_input_returns_empty(self):
        self.assertEqual(self.mod._html_to_text(""), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
