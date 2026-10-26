"""Regression fixtures from the real 3.1.1 macOS search log.

No live job-board traffic and no applicant information.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as state:
    with patch.dict(os.environ, {"STATE_DIR": state}):
        import main


class RelevanceDataQualityTests(unittest.TestCase):
    def test_jihlava_and_vysocina_are_outside_prague_gate(self):
        examples = [
            {"title": "Tester/ Junior Tester - Jihlava - i absolventi",
             "location": "Vysočina", "description": ""},
            {"title": "Tester/ Junior Tester - Jihlava - i absolventi",
             "location": "", "description": ""},
            {"title": "QA Engineer", "location": "Vysočina", "description": ""},
        ]
        with patch.object(main, "LOCATION_MODE", "prague"):
            for row in examples:
                with self.subTest(row=row):
                    allowed, reason, _ = main.location_gate(row)
                    self.assertIs(allowed, False)
                    self.assertIn("outside_prague", reason)

    def test_prague_or_genuine_full_remote_still_allowed(self):
        with patch.object(main, "LOCATION_MODE", "prague"):
            self.assertIs(main.location_gate(
                {"title": "QA Engineer", "location": "Praha"})[0], True)
            self.assertIs(main.location_gate(
                {"title": "Junior Tester Jihlava", "location": "Vysočina",
                 "description": "The job is fully remote across Czechia."})[0], True)
            self.assertIsNone(main.location_gate(
                {"title": "QA Engineer", "location": ""})[0])

    def test_contract_labels_never_become_company(self):
        for value in ("Full-time", "Part-time", "Full time", "Plný úvazek",
                      "Částečný úvazek"):
            for source in ("structured", "search_card", "browser_render"):
                with self.subTest(value=value, source=source):
                    self.assertFalse(main.valid_company(value, source))
        for name in ("Chci do O2", "Full Time Solutions s.r.o.", "Home Credit"):
            self.assertTrue(main.valid_company(name, "structured"))

    def test_invalid_hiring_organization_is_ignored_during_http_enrichment(self):
        structured = json.dumps({
            "@context": "https://schema.org", "@type": "JobPosting",
            "title": "Junior Tester", "hiringOrganization": {
                "@type": "Organization", "name": "Full-time",
            },
        })
        html = (f'<html><head><script type="application/ld+json">{structured}</script>'
                '</head><body><h1>Junior Tester</h1><main>' +
                "Assist QA team with simple tasks. " * 55 +
                '</main></body></html>')
        session = Mock()
        session.get.return_value = Mock(text=html)
        job = {"title": "Junior Tester", "job_id": "synthetic",
               "source": "jobs.cz", "url": "https://example.invalid/job"}
        result = main.enrich_job(job, session)
        self.assertFalse(result.get("company"))
        self.assertNotEqual(result.get("company_source"), "http_jsonld")


if __name__ == "__main__":
    unittest.main()
