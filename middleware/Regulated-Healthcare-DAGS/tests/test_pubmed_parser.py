"""Stdlib unittest suite for the PubMed esearch XML parser.

The PubMed abstracts handler runs an esearch → efetch flow. esearch responses
carry PMIDs inside `<IdList><Id>...</Id></IdList>`; the parser MUST stay
tolerant of malformed XML (return []) and MUST NOT confuse <Id> nodes from
efetch payloads (which appear inside <ArticleIdList>) with PMIDs.

Run from repo root:

    python -m unittest discover -s middleware/Regulated-Healthcare-DAGS/tests -v
"""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

# Stub `requests` — handler imports it at module load.
sys.modules.setdefault("requests", types.ModuleType("requests"))


def _load_handler():
    path = (
        Path(__file__).parent.parent / "handlers" / "pubmed_abstracts_efetch_fetch.py"
    ).resolve()
    spec = importlib.util.spec_from_file_location("pubmed_abstracts_efetch_fetch", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestParsePMIDs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_handler()

    def test_realistic_esearch_response(self):
        xml = """<?xml version="1.0"?>
<eSearchResult>
  <Count>3</Count>
  <RetMax>3</RetMax>
  <IdList>
    <Id>34123456</Id>
    <Id>33987654</Id>
    <Id>32555555</Id>
  </IdList>
</eSearchResult>"""
        self.assertEqual(
            self.mod._parse_pmids(xml),
            ["34123456", "33987654", "32555555"],
        )

    def test_empty_idlist(self):
        xml = """<?xml version="1.0"?>
<eSearchResult><Count>0</Count><IdList></IdList></eSearchResult>"""
        self.assertEqual(self.mod._parse_pmids(xml), [])

    def test_malformed_xml_returns_empty(self):
        # Tolerance is required — esearch can return server errors as plain text.
        self.assertEqual(self.mod._parse_pmids("not xml at all"), [])
        self.assertEqual(self.mod._parse_pmids(""), [])
        self.assertEqual(self.mod._parse_pmids("<broken<xml>"), [])

    def test_ignores_id_outside_idlist(self):
        # Defensive: efetch responses also contain <Id> elements (inside
        # <ArticleIdList>) but those are DOIs / pubmed ids of related works —
        # not a search result. Parser must scope to <IdList>.
        xml = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>11111111</PMID>
      <Article>
        <ArticleIdList>
          <Id>10.1000/example</Id>
          <Id>doi-style-id</Id>
        </ArticleIdList>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>"""
        self.assertEqual(self.mod._parse_pmids(xml), [])

    def test_strips_whitespace_around_pmids(self):
        xml = """<?xml version="1.0"?>
<eSearchResult>
  <IdList>
    <Id>  12345  </Id>
    <Id>
      67890
    </Id>
  </IdList>
</eSearchResult>"""
        self.assertEqual(self.mod._parse_pmids(xml), ["12345", "67890"])

    def test_drops_empty_id_elements(self):
        xml = """<?xml version="1.0"?>
<eSearchResult>
  <IdList>
    <Id>123</Id>
    <Id></Id>
    <Id>   </Id>
    <Id>456</Id>
  </IdList>
</eSearchResult>"""
        self.assertEqual(self.mod._parse_pmids(xml), ["123", "456"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
