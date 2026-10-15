"""Ensure Support/QA entry evidence is actually present in the employer advert."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support_qa_tracks import support_qa_entry_details, support_qa_assessment
from PySide6.QtWidgets import QApplication
from desktop_widgets import VacancyDetail

with tempfile.TemporaryDirectory() as directory:
    with patch.dict(os.environ, {"STATE_DIR": directory}):
        import main

DETAIL = (
    "Handle internal IT support tickets. Diagnose Windows issues and "
    "communicate with users. " * 12
)


def job(desc, structured=""):
    return {
        "title": "IT Support Technician",
        "description": desc,
        "jobposting_description": structured,
        "evidence_quality": "strong",
        "source": "jobs.cz",
    }


class EntryEvidenceAuditTests(unittest.TestCase):
    def test_literal_czech_quote_and_origin(self):
        result = support_qa_entry_details(
            job("Požadavky: Praxe není podmínkou. " + DETAIL)
        )
        self.assertEqual(result["basis"], "description")
        self.assertEqual(result["quote"], "Praxe není podmínkou")
        self.assertEqual(result["origin"], "vacancy page")

    def test_structured_description_takes_precedence_over_page_navigation(self):
        result = support_qa_entry_details(job(
            "Doporučené pozice: No experience required. " + DETAIL,
            "Requirements: Ticket support, troubleshooting. Graduates welcome."
        ))
        self.assertEqual(result["basis"], "description")
        self.assertEqual(result["quote"], "Graduates welcome")
        self.assertEqual(result["origin"], "JobPosting")

    def test_related_jobs_footer_not_allowed_to_promote(self):
        result = support_qa_assessment(job(
            DETAIL + " Related jobs: QA Intern, no experience required."
        ))
        self.assertEqual(result["decision"], "REVIEW")
        self.assertEqual(result["entry_evidence"], "none")
        self.assertEqual(result["entry_evidence_quote"], "")

    def test_unstructured_late_entry_claim_cannot_promote(self):
        result = support_qa_assessment(job(
            DETAIL * 20 + " No prior experience required."
        ))
        self.assertNotEqual(result["decision"], "APPLY")
        self.assertEqual(result["entry_evidence"], "none")

    def test_title_entry_remains_accepted_without_extra_quote(self):
        record = job(DETAIL)
        record["title"] = "Junior IT Support"
        result = support_qa_assessment(record)
        self.assertEqual(result["entry_evidence"], "title")
        self.assertEqual(result["entry_evidence_quote"], "Junior IT Support")
        self.assertEqual(result["decision"], "APPLY")

    def test_one_two_years_in_full_ad_still_blocks_structured_positive(self):
        record = job(
            DETAIL + " Minimum 2 years of work experience.",
            "Graduates welcome. " + DETAIL
        )
        result = support_qa_assessment(record)
        self.assertEqual(result["decision"], "REVIEW")
        self.assertTrue(result["junior_experience_requirement"])

    def test_snapshot_keeps_citation_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(main, "APPLICATIONS_FILE", Path(directory) / "applications.csv"), \
                 patch.object(main, "VACANCIES_FILE", Path(directory) / "vacancies.jsonl"):
                record = job(DETAIL + " No experience required.")
                record.update({"job_id":"2000991234","url":"https://www.jobs.cz/rpd/2000991234/"})
                assessment = main.score_job(record)
                record.update(assessment)
                main.save_status(record, "READY_TO_PREPARE", record["score"], "test")
                import json
                saved = json.loads((Path(directory) / "vacancies.jsonl").read_text().splitlines()[0])
                self.assertEqual(saved["entry_evidence"], "description")
                self.assertEqual(saved["entry_evidence_quote"], "No experience required")
                self.assertEqual(saved["entry_evidence_origin"], "vacancy page")

    def test_dashboard_shows_employer_phrase_and_blocker(self):
        instance = QApplication.instance() or QApplication([])
        detail = VacancyDetail()
        record = {
            "title": "QA Analyst", "company": "Demo", "source": "jobs.cz",
            "score": 69, "role_track": "qa", "entry_role": True,
            "entry_evidence": "description",
            "entry_evidence_quote": "Vítáme i absolventy",
            "target_apply_blockers": ["advanced mandatory technical requirements"],
            "description": "QA",
        }
        detail.set_record(record, "REVIEW")
        from PySide6.QtWidgets import QLabel
        text = "\n".join(w.text() for w in detail.findChildren(QLabel))
        self.assertIn("Вітаме", text.replace("Vítáme", "Вітаме"))
        self.assertIn("advanced mandatory technical requirements", text)
        detail.close()


if __name__ == "__main__":
    unittest.main()
