"""Offline checks for separate Support/Manual QA discovery and CV safety."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support_qa_tracks import support_qa_assessment, support_qa_track
from resume_routes import resume_group_for_job

with tempfile.TemporaryDirectory() as directory:
    with patch.dict(os.environ, {"STATE_DIR": directory}):
        import main


def vacancy(title, description=None, evidence="strong"):
    if description is None:
        description = (
            "We support customers and investigate tickets using clear "
            "technical documentation and browser troubleshooting. "
        ) * 20
    return {
        "title": title, "actual_title": title, "source": "jobs.cz",
        "description": description, "card_text": "",
        "evidence_quality": evidence,
        "location": "Praha",
    }


SUPPORT_DESCRIPTION = (
    "You will help internal users with technical troubleshooting, "
    "incident tickets, macOS issues and technical documentation. "
) * 20
QA_DESCRIPTION = (
    "You will do manual functional testing, regression checks, bug "
    "reproduction, test cases and Playwright web app testing. "
) * 20


class SupportQaTrackTests(unittest.TestCase):
    def test_support_titles_and_matching_secondary_cv(self):
        titles = [
            "Junior IT Support Specialist", "IT podpora", "Technická podpora",
            "Application Support Engineer", "Service Desk Analyst",
            "Helpdesk Technician", "L1 Support",
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertEqual(support_qa_track(title), "support")
                self.assertEqual(resume_group_for_job({"title": title}), "support_qa")
                self.assertEqual(main.role_class(title), "target")

    def test_qa_titles_and_matching_secondary_cv(self):
        titles = [
            "Junior QA Tester", "Manual Tester", "Software Tester",
            "Test Analyst", "Tester aplikací", "Manuální tester",
            "QA Trainee", "QA Engineer",
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertEqual(support_qa_track(title), "qa")
                self.assertEqual(resume_group_for_job({"title": title}), "support_qa")
                self.assertEqual(main.role_class(title), "target")

    def test_exclusions_do_not_misroute_unrelated_titles(self):
        for title in [
            "Senior IT Support", "Customer Service Agent", "Sales Support",
            "Penetration Tester", "Cybersecurity QA Tester", "Business Analyst",
            "Data Analyst", "IT Administrator",
        ]:
            with self.subTest(title=title):
                self.assertNotEqual(
                    main.role_class(title) == "target"
                    and main.score_job(vacancy(title)).get("role_track") in {"support", "qa"},
                    True,
                )

    def test_junior_support_can_apply_on_strong_verified_familiar_evidence(self):
        result = main.score_job(vacancy("Junior IT Support", SUPPORT_DESCRIPTION))
        self.assertEqual(result["decision"], "APPLY")
        self.assertEqual(result["role_track"], "support")
        self.assertGreaterEqual(len(result["matched"]), 2)
        self.assertEqual(result["target_apply_blockers"], [])

    def test_junior_qa_can_apply_on_strong_verified_familiar_evidence(self):
        result = main.score_job(vacancy("Junior QA Tester", QA_DESCRIPTION))
        self.assertEqual(result["decision"], "APPLY")
        self.assertEqual(result["role_track"], "qa")
        self.assertIn("regression", result["matched"])
        self.assertIn("defect_tracking", result["matched"])

    def test_unknown_or_medium_evidence_never_prepares_automatically(self):
        for title, content, quality in [
            ("IT Support Specialist", SUPPORT_DESCRIPTION, "strong"),
            ("QA Engineer", QA_DESCRIPTION, "strong"),
            ("Junior QA Tester", QA_DESCRIPTION, "medium"),
            ("Junior IT Support", "We offer support and learning.", "strong"),
        ]:
            with self.subTest(title=title, quality=quality):
                result = main.score_job(vacancy(title, content, quality))
                self.assertNotEqual(result["decision"], "APPLY")
                self.assertTrue(result["target_apply_blockers"])

    def test_advanced_mandatory_requirement_blocks_automatic_preparation(self):
        description = SUPPORT_DESCRIPTION + (
            " Required active directory and Windows Server experience. "
        ) * 3
        result = main.score_job(vacancy("Junior IT Support", description))
        self.assertNotEqual(result["decision"], "APPLY")
        self.assertIn("advanced mandatory technical requirements", result["target_apply_blockers"])

    def test_hard_experience_gate(self):
        job = vacancy("Junior QA Tester", QA_DESCRIPTION)
        result = support_qa_assessment(job, hard_experience=True)
        self.assertNotEqual(result["decision"], "APPLY")
        self.assertIn("experience 3+ years requirement", result["target_apply_blockers"])

    def test_qa_and_data_require_different_matching_skills(self):
        qa = main.score_job(vacancy("Junior QA Tester", QA_DESCRIPTION))
        self.assertTrue(qa["decision"] in {"APPLY", "REVIEW"})
        self.assertNotIn("sql", qa.get("required_skills", []))
        self.assertEqual(main.role_class("Junior Data Analyst"), "target")

    def test_enable_toggle_controls_discovery_and_scoring(self):
        with patch.object(main, "SEARCH_SUPPORT_QA", False):
            self.assertNotEqual(main.role_class("Junior QA Tester"), "target")
            result = main.score_job(vacancy("Junior QA Tester", QA_DESCRIPTION))
            self.assertNotIn("role_track", result)
        self.assertIn("Junior IT Support", main.SUPPORT_QA_SEARCH_QUERIES)
        self.assertTrue(any(r == "/nabidky/tester/" for _,r in main.SUPPORT_QA_PRACE_SEARCH_ROUTES))

    def test_search_prioritization_includes_qa_support(self):
        job = vacancy("Junior QA Tester", QA_DESCRIPTION)
        self.assertGreater(main.discovery_priority(job), main.discovery_priority(vacancy("Accountant", "Accounts payable.")))
        selected = main.select_discovery_candidates([
            {**vacancy("Junior IT Support", SUPPORT_DESCRIPTION), "job_id": "A1", "url": "https://www.jobs.cz/rpd/2000000001/"},
            {**vacancy("Junior QA Tester", QA_DESCRIPTION), "job_id": "A2", "url": "https://www.jobs.cz/rpd/2000000002/"},
        ], set(), set(), 2)
        self.assertEqual(len(selected), 2)


if __name__ == "__main__":
    unittest.main()
