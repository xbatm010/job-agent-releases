"""Conservative description-derived entry-level evidence for Support/QA.

These tests protect the final manual submission boundary and deliberately
differentiate a clear 'graduates welcome' requirement from generic benefits.
"""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support_qa_tracks import support_qa_entry_evidence

with tempfile.TemporaryDirectory() as directory:
    with patch.dict(os.environ, {"STATE_DIR": directory}):
        import main


SUPPORT = (
    "Our IT support team resolves user incidents, investigates troubleshooting "
    "tickets, supports Windows/macOS and writes technical documentation. "
) * 18
QA = (
    "The role includes manual testing, functional testing, regression checks, "
    "test cases, reproduction of bugs, defect tracking and web application checks. "
) * 16


def vacancy(title, description, quality="strong"):
    return {
        "title": title, "actual_title": title, "source": "jobs.cz",
        "description": description, "card_text": "",
        "location": "Praha", "evidence_quality": quality,
    }


class DescriptionEntryPromotion(unittest.TestCase):
    def test_english_support_without_junior_when_no_experience_needed(self):
        for line in (
            "No previous professional experience is required.",
            "No experience required.",
            "We welcome graduates.",
            "This position is suitable for graduates.",
            "Prior work experience is not required.",
        ):
            with self.subTest(line=line):
                score = main.score_job(vacancy("IT Support Technician", SUPPORT + line))
                self.assertEqual(score["decision"], "APPLY")
                self.assertEqual(score["entry_evidence"], "description")
                self.assertTrue(score["entry_role"])
                self.assertEqual(score["target_apply_blockers"], [])

    def test_czech_support_without_junior_when_graduates_welcome(self):
        for line in (
            "Pozice je vhodná i pro absolventy.",
            "Praxe není podmínkou.",
            "Předchozí praxe není nutná.",
            "Vítáme i absolventy.",
        ):
            with self.subTest(line=line):
                score = main.score_job(vacancy("IT podpora uživatelů", SUPPORT + line))
                self.assertEqual(score["decision"], "APPLY")
                self.assertEqual(score["entry_evidence"], "description")

    def test_qa_without_junior_promoted_on_description_only(self):
        for line in (
            "No prior experience necessary.",
            "Suitable for graduates.",
            "Praxe není vyžadována.",
        ):
            with self.subTest(line=line):
                score = main.score_job(vacancy("QA Analyst", QA + line))
                self.assertEqual(score["decision"], "APPLY")
                self.assertEqual(score["role_track"], "qa")
                self.assertIn("manual_testing", score["matched"])
                self.assertIn("regression", score["matched"])

    def test_no_promotion_for_generic_training_or_missing_entry_language(self):
        for line in (
            "Training is provided.",
            "We have experienced engineers and a training program.",
            "Nice to have experience in service desk.",
            "Use SQL, Postman and issue tracking every day.",
        ):
            with self.subTest(line=line):
                job = vacancy("QA Analyst", QA + line)
                result = main.score_job(job)
                self.assertEqual(result["decision"], "REVIEW")
                self.assertEqual(result["entry_evidence"], "none")
                self.assertIn("junior/trainee/L1 marker absent",
                              result["target_apply_blockers"])

    def test_medium_or_weak_evidence_is_never_ready(self):
        for quality in ("weak", "medium"):
            with self.subTest(quality=quality):
                result = main.score_job(vacancy(
                    "IT Support Specialist", SUPPORT + "No experience required.", quality
                ))
                self.assertEqual(result["decision"], "REVIEW")
                self.assertIn("strong description evidence required",
                              result["target_apply_blockers"])

    def test_negative_graduate_language_cannot_qualify(self):
        for line in (
            "We welcome graduates. Not suitable for graduates.",
            "No experience required. Graduates not accepted.",
            "Vhodné i pro absolventy. Není vhodné pro absolventy.",
        ):
            with self.subTest(line=line):
                result = main.score_job(vacancy("QA Analyst", QA + line))
                self.assertNotEqual(result["decision"], "APPLY")
                self.assertEqual(result["entry_evidence"], "none")

    def test_mandatory_one_or_two_years_stays_review(self):
        lines = (
            "No experience required. Minimum 2 years of experience.",
            "We welcome graduates. At least 1 year of work experience.",
            "Vhodné pro absolventy. Minimálně 2 roky praxe.",
            "Vítáme absolventy. Požadujeme 1 rok praxe.",
            "No experience required. 2+ years of experience.",
            "Praxe není nutná. 1-2 roky praxe.",
        )
        for line in lines:
            with self.subTest(line=line):
                score = main.score_job(vacancy("IT Support", SUPPORT + line))
                self.assertNotEqual(score["decision"], "APPLY")
                self.assertTrue(score["junior_experience_requirement"])
                self.assertIn(
                    "1-2 years experience requirement or ambiguous range",
                    score["target_apply_blockers"],
                )

    def test_title_junior_is_not_override_for_required_experience(self):
        result = main.score_job(vacancy(
            "Junior QA Tester", QA + "Minimálně 2 roky praxe."
        ))
        self.assertEqual(result["decision"], "REVIEW")
        self.assertEqual(result["entry_evidence"], "title")
        self.assertTrue(result["junior_experience_requirement"])

    def test_optional_two_years_is_not_silently_mandatory(self):
        result = main.score_job(vacancy(
            "QA Analyst", QA +
            "Graduates welcome. Two years of experience is a plus, not required."
        ))
        self.assertEqual(result["decision"], "APPLY")
        self.assertFalse(result["junior_experience_requirement"])

    def test_advanced_technical_requirement_still_blocks(self):
        result = main.score_job(vacancy(
            "IT Support Specialist", SUPPORT +
            "No experience required. Required Active Directory administration."
        ))
        self.assertEqual(result["decision"], "REVIEW")
        self.assertIn(
            "advanced mandatory technical requirements", result["target_apply_blockers"]
        )

    def test_three_year_requirement_blocks_even_graduate_language(self):
        result = main.score_job(vacancy(
            "IT Support", SUPPORT + "Graduates welcome. Minimum 3 years experience."
        ))
        self.assertNotEqual(result["decision"], "APPLY")
        self.assertIn("experience 3+ years requirement", result["target_apply_blockers"])

    def test_no_practical_signals_still_block(self):
        result = main.score_job(vacancy(
            "IT Support Specialist",
            ("We offer basic Windows IT support and user communication. " * 20)
            + "No experience required."
        ))
        self.assertNotEqual(result["decision"], "APPLY")
        self.assertIn("no concrete diagnostic/test evidence",
                      result["target_apply_blockers"])

    def test_consistent_resume_selection_for_promoted_roles(self):
        from resume_routes import resume_group_for_job
        for title in ("IT Support Specialist", "QA Analyst"):
            with self.subTest(title=title):
                self.assertEqual(resume_group_for_job({"title": title}), "support_qa")

    def test_data_scoring_unchanged(self):
        job = vacancy("Junior Data Analyst", "SQL Python, data validation and statistical analysis.")
        score = main.score_job(job)
        self.assertNotIn("entry_evidence", score)
        self.assertNotIn("role_track", score)

    def test_description_entry_uses_only_vacancy_description(self):
        job = vacancy("QA Analyst", QA)
        job["card_text"] = "Graduates welcome."
        score = main.score_job(job)
        self.assertEqual(score["decision"], "REVIEW")
        self.assertEqual(score["entry_evidence"], "none")

    def test_support_qa_entry_evidence_is_pure(self):
        self.assertEqual(support_qa_entry_evidence("IT Support", "IT role"), (False, "none", False))
        self.assertEqual(support_qa_entry_evidence(
            "Junior IT Support", "No prior experience needed"
        ), (True, "title", False))


if __name__ == "__main__":
    unittest.main()
