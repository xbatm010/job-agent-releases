"""Role-specific PDF routing regression tests (no browser or mailbox access)."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from resume_routes import normalize_title, resume_group_for_job, choose_resume


class ResumeRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data-analyst.pdf"
        self.support = Path(self.temp.name) / "it-support-qa.pdf"
        self.data.write_bytes(b"%PDF-test-primary")
        self.support.write_bytes(b"%PDF-test-secondary")

    def test_data_and_reporting_keep_existing_primary_cv(self):
        titles = [
            "Junior Data Analyst", "BI Analyst",
            "Junior Reporting Specialist", "Business Data Analyst",
            "Datový analytik", "Reporting Analyst",
            "Business Intelligence Analyst", "CRM Data Analyst",
            "Finance Analyst", "Unknown Entry Level Role",
        ]
        for title in titles:
            with self.subTest(title=title):
                group, selected = choose_resume(
                    {"title": title}, self.data, self.support
                )
                self.assertEqual(group, "data")
                self.assertEqual(selected, str(self.data))

    def test_support_and_testing_use_secondary_cv(self):
        titles = [
            "IT Support Specialist", "Application Support Engineer",
            "Technical Support Analyst", "Service Desk Analyst",
            "Helpdesk Technician", "IT podpora", "Technická podpora",
            "Manual QA Tester", "Junior QA Engineer", "Junior Tester",
            "Software Tester", "Test Analyst", "Test Engineer",
            "Manuální tester", "QA Trainee",
        ]
        for title in titles:
            with self.subTest(title=title):
                group, selected = choose_resume(
                    {"title": title}, self.data, self.support
                )
                self.assertEqual((group, selected), ("support_qa", str(self.support)))

    def test_actual_title_overrides_portal_generic_title(self):
        group, chosen = choose_resume(
            {"title": "Detail pozice", "actual_title": "Junior QA Tester"},
            self.data, self.support,
        )
        self.assertEqual((group, chosen), ("support_qa", str(self.support)))

    def test_security_tester_not_assumed_to_be_qa(self):
        self.assertEqual(
            resume_group_for_job({"title": "Penetration Tester"}), "data"
        )

    def test_no_secondary_cv_fails_closed_without_primary_fallback(self):
        with self.assertRaisesRegex(ValueError, "IT Support / QA"):
            choose_resume({"title": "Service Desk Analyst"}, self.data, "")
        with self.assertRaises(FileNotFoundError):
            choose_resume({"title": "Service Desk Analyst"}, self.data, self.support.parent / "missing.pdf")

    def test_primary_and_secondary_both_must_be_pdf(self):
        with self.assertRaises(ValueError):
            choose_resume({"title": "Data Analyst"}, self.support.with_suffix(".docx"), self.support)
        with self.assertRaises(ValueError):
            choose_resume({"title": "QA Tester"}, self.data, self.data.with_suffix(".png"))

    def test_unicode_czech_normalization(self):
        self.assertEqual(normalize_title("Technická podpora / PRAHA"), "technicka podpora praha")

    def test_scoring_role_class_is_not_changed_by_resume_choice(self):
        # Routing never modifies job attributes nor claims it can score a role.
        original = {"job_id": "123", "title": "IT Support Specialist", "decision": "REVIEW"}
        copy = dict(original)
        choose_resume(original, self.data, self.support)
        self.assertEqual(original, copy)


class ResumeUploadSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_secondary_cv_never_uses_unverified_saved_profile_cv(self):
        from unittest.mock import AsyncMock, patch
        import main
        with tempfile.TemporaryDirectory() as tmp:
            cv = Path(tmp) / "qa.pdf"
            cv.write_bytes(b"%PDF-test")
            with patch.object(main, "CV_PATH", str(cv)), \
                    patch.object(main, "ACTIVE_CV_GROUP", "support_qa"), \
                    patch.object(main, "direct_file_upload", new_callable=AsyncMock, return_value=False), \
                    patch.object(main, "select_saved_cv_control", new_callable=AsyncMock, return_value=(True, "saved")) as saved, \
                    patch.object(main, "discover_cv_controls", new_callable=AsyncMock, return_value=(False, "no_control")), \
                    patch.object(main, "cv_attachment_detected", new_callable=AsyncMock, return_value=False), \
                    patch.object(main, "manual_cv_fallback", new_callable=AsyncMock, return_value=(False, "manual_expired")):
                ok, reason = await main.upload_cv_adaptive(object())
                self.assertFalse(ok)
                self.assertEqual(reason, "cv_attachment_not_detected")
                saved.assert_not_awaited()

    async def test_data_cv_retains_prior_saved_profile_behavior(self):
        from unittest.mock import AsyncMock, patch
        import main
        with tempfile.TemporaryDirectory() as tmp:
            cv = Path(tmp) / "data.pdf"
            cv.write_bytes(b"%PDF-test")
            with patch.object(main, "CV_PATH", str(cv)), \
                    patch.object(main, "ACTIVE_CV_GROUP", "data"), \
                    patch.object(main, "direct_file_upload", new_callable=AsyncMock, return_value=False), \
                    patch.object(main, "select_saved_cv_control", new_callable=AsyncMock, return_value=(True, "saved")) as saved:
                ok, reason = await main.upload_cv_adaptive(object())
                self.assertTrue(ok)
                self.assertEqual(reason, "saved")
                saved.assert_awaited_once()

if __name__ == "__main__":
    unittest.main()
