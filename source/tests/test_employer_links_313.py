"""Conservative employer-profile extraction before the application stage."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as directory:
    with patch.dict(os.environ, {"STATE_DIR": directory}):
        import main


class EmployerProfileLinkTests(unittest.TestCase):
    def parse(self, html):
        return main.BeautifulSoup(html, "html.parser")

    def test_explicit_jobs_employer_profile_can_reveal_company(self):
        soup = self.parse(
            '<main><h1>IT Support Technik</h1>'
            '<a href="/fp/ipodnik-cloud-12345/">iPodnik cloud s.r.o.</a></main>'
        )
        self.assertEqual(
            main.extract_company_from_employer_profile_link(soup, "IT Support Technik"),
            "iPodnik cloud s.r.o.",
        )

    def test_employer_link_uses_displayed_name_not_guessed_slug(self):
        soup = self.parse(
            '<main><a href="/fp/long-unknown-slug-123456/">2. lékařská fakulta</a></main>'
        )
        self.assertEqual(
            main.extract_company_from_employer_profile_link(soup),
            "2. lékařská fakulta",
        )

    def test_generic_or_navigation_profile_links_do_not_count(self):
        samples = (
            '<main><nav><a href="/fp/example-12/">Unrelated Inc.</a></nav></main>',
            '<main><a href="/fp/example-12/">Zobrazit profil firmy</a></main>',
            '<main><a href="/fp/example-12/">Full-time</a></main>',
            '<main><a href="/rpd/2001441236/">iPodnik cloud s.r.o.</a></main>',
            '<main><a href="/fp/example-12/">IT Support Technik</a></main>',
        )
        for html in samples:
            with self.subTest(html=html):
                self.assertEqual(
                    main.extract_company_from_employer_profile_link(
                        self.parse(html), "IT Support Technik"
                    ), ""
                )

    def test_employer_profile_is_extracted_during_http_enrichment(self):
        html = ('<html><main><h1>IT Support Technik</h1>'
                '<a href="/fp/ipodnik-cloud-12345/">iPodnik cloud s.r.o.</a>'
                + ('Support users with Windows and tickets. ' * 70)
                + '</main></html>')
        response = Mock(text=html)
        session = Mock()
        session.get.return_value = response
        row = {
            "source": "jobs.cz",
            "job_id": "2001441236",
            "title": "IT Support Technik",
            "url": "https://www.jobs.cz/rpd/2001441236/",
        }
        result = main.enrich_job(row, session)
        self.assertEqual(result["company"], "iPodnik cloud s.r.o.")
        self.assertEqual(result["company_source"], "http_employer_profile")
        self.assertEqual(result["evidence_quality"], "strong")

    def test_existing_employer_from_card_is_not_overwritten(self):
        html = ('<html><main><h1>IT Support Technik</h1>'
                '<a href="/fp/example-12345/">Other Company s.r.o.</a>'
                + ('Technical support for users. ' * 80)
                + '</main></html>')
        response = Mock(text=html)
        session = Mock()
        session.get.return_value = response
        row = {
            "source": "jobs.cz", "title": "IT Support Technik",
            "job_id": "2001441236",
            "url": "https://www.jobs.cz/rpd/2001441236/",
            "company": "Trusted Employer s.r.o.",
            "company_source": "search_card",
        }
        result = main.enrich_job(row, session)
        self.assertEqual(result["company"], "Trusted Employer s.r.o.")


if __name__ == "__main__":
    unittest.main()
