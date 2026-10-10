"""Offline scoring regressions. No job-board requests or submissions."""

import contextlib
import csv
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as import_state:
    with patch.dict(os.environ, {"STATE_DIR": import_state}):
        import main


ENTRY_TITLE = "Junior Data & Credit Reporting Specialist (part-time / student)"
REGULAR_TITLE = "Data & Credit Reporting Specialist (part-time)"


def vacancy(title=ENTRY_TITLE, location="Praha", job_id="2000000001"):
    # Synthetic reproduction of the logged 76/100 and five data signals.
    # The original log did not include the actual candidate-fit breakdown.
    description = (
        "SQL Excel reporting dashboards databases data quality English Czech "
        + ("Prague. " if location == "Praha" else "")
        + "Our team collaborates on daily tasks and shares clear documentation. " * 28
    )
    return {
        "source": "jobs.cz", "job_id": job_id,
        "title": title, "actual_title": title,
        "company": f"Example {job_id}",
        "url": f"https://www.jobs.cz/rpd/{job_id}/",
        "location": location, "description": description, "card_text": "",
        "role_class": main.role_class(title),
        "evidence_quality": main.evidence_quality_for_text(description),
    }


class ScoringDefaults:
    def setUp(self):
        super().setUp()
        self.state = tempfile.TemporaryDirectory()
        self.addCleanup(self.state.cleanup)
        state = Path(self.state.name)
        self.addCleanup(patch.stopall)
        patch.multiple(
            main, STATE_DIR=state, APPLICATIONS_FILE=state / "applications.csv",
            VACANCIES_FILE=state / "vacancies.jsonl", OVERRIDES_FILE=state / "overrides.json",
            EXPANDED_MIN_CANDIDATE_FIT=12, EXPANDED_ENTRY_MIN_CANDIDATE_FIT=10,
            EXPANDED_MIN_DATA_SIGNALS=3, EXPANDED_APPLY_SCORE=70,
            EXPANDED_REVIEW_SCORE=58, MIN_APPLY_SCORE=66, ENTRY_APPLY_SCORE=62,
            VERIFIED_TARGET_APPLY_SCORE=64, VERIFIED_TARGET_MIN_CANDIDATE_FIT=10,
            MIN_REVIEW_SCORE=55, MANUAL_REVIEW_APPLY_MIN_SCORE=65,
            LOCATION_MODE="prague", ALLOW_FULL_REMOTE_OUTSIDE_PRAGUE=True,
        ).start()


class ExpandedScoringTests(ScoringDefaults, unittest.TestCase):

    def test_target_low_skill_match_is_review_even_with_high_role_score(self):
        job = vacancy("IT business analytik/analytička", job_id="2001438418")
        job["description"] = (
            "Our collaborative team handles daily reporting tasks. " * 32
            + "SQL Praha English Czech"
        )
        job["card_text"] = ""
        job["evidence_quality"] = "strong"
        result = main.score_job(job)
        self.assertEqual(result["role_class"] if "role_class" in result else main.role_class(job["title"]), "target")
        self.assertEqual(result["candidate_fit"], 6)
        self.assertGreaterEqual(result["score"], main.MIN_APPLY_SCORE)
        self.assertEqual(result["decision"], "REVIEW")
        self.assertEqual(result["target_candidate_fit_min"], 10)
        self.assertIn("candidate_fit=6 < 10", result["target_apply_blockers"])
        self.assertTrue(main.manual_review_apply_eligible(
            {**job, **result, "role_class": "target"}, True
        ))

    def test_target_with_more_skill_evidence_can_still_apply(self):
        job = vacancy("IT business analytik/analytička")
        job["description"] = (
            "Our collaborative team handles daily reporting tasks. " * 32
            + "SQL Excel Praha English Czech"
        )
        job["card_text"] = ""
        job["evidence_quality"] = "strong"
        result = main.score_job(job)
        self.assertEqual(result["candidate_fit"], 10)
        self.assertEqual(result["decision"], "APPLY")
        self.assertEqual(result["target_apply_blockers"], [])

    def test_entry_target_allows_six_skill_points_but_not_zero(self):
        job = vacancy("Junior Data Analyst")
        job["description"] = "Team tasks and documentation. " * 40 + "SQL Praha English Czech"
        job["card_text"] = ""
        job["evidence_quality"] = "strong"
        result = main.score_job(job)
        self.assertEqual(result["candidate_fit"], 6)
        self.assertEqual(result["target_candidate_fit_min"], 6)
        self.assertEqual(result["decision"], "APPLY")
        job["description"] = "Team tasks and documentation. " * 40 + "Praha English Czech"
        result = main.score_job(job)
        self.assertEqual(result["candidate_fit"], 0)
        self.assertNotEqual(result["decision"], "APPLY")

    def test_explicit_required_and_optional_skills_are_distinguished(self):
        required, preferred = main.explicit_skill_requirements(
            "We require SQL and Tableau. Nice to have Snowflake and Power BI."
        )
        self.assertEqual(required, ["sql", "tableau"])
        self.assertEqual(preferred, ["power bi", "snowflake"])
        self.assertTrue(main.skill_required("Must have Tableau", "tableau"))
        self.assertFalse(main.skill_required("Nice to have Tableau", "tableau"))
        self.assertEqual(
            main.explicit_skill_requirements(
                "What we expect: experience with Tableau. "
                "We offer training in Python and Excel."
            ),
            ([], []),
        )

    def test_mandatory_unfamiliar_technology_blocks_automatic_apply(self):
        job = vacancy("Group Reporting Specialist", job_id="2001431065")
        job["description"] = (
            "SQL Excel statistical analysis Power BI reporting "
            "data quality analytics Prague English Czech. "
            + "Our team prepares monthly dashboard reports. " * 40
            + "Must have Snowflake."
        )
        job["evidence_quality"] = "strong"
        result = main.score_job(job)
        self.assertEqual(result["candidate_fit"], 16)
        self.assertIn("snowflake", result["required_skills"])
        self.assertIn("snowflake", result["gaps"])
        self.assertEqual(result["decision"], "REVIEW")
        self.assertIn("missing_required_skills=snowflake",
                      result["expanded_apply_blockers"])

    def test_optional_or_unqualified_technology_does_not_block_apply(self):
        job = vacancy("Group Reporting Specialist", job_id="2001431065")
        job["description"] = (
            "SQL Excel statistical analysis Power BI reporting "
            "data quality analytics Prague English Czech. "
            + "Our team prepares monthly dashboard reports. " * 40
            + "Nice to have Snowflake."
        )
        job["evidence_quality"] = "strong"
        result = main.score_job(job)
        self.assertEqual(result["decision"], "APPLY")
        self.assertIn("snowflake", result["preferred_skills"])
        self.assertEqual(result["gaps"], [])
        job["description"] = job["description"].replace(
            "Nice to have Snowflake.", "Tools: Snowflake."
        )
        result = main.score_job(job)
        self.assertEqual(result["decision"], "APPLY")
        self.assertEqual(result["required_skills"], [])
        self.assertEqual(result["gaps"], [])

    def test_mandatory_basics_are_labelled_not_assumed_proficient(self):
        required, preferred = main.explicit_skill_requirements(
            "Požadujeme znalost SQL a Python. Výhodou Tableau."
        )
        self.assertEqual(required, ["python", "sql"])
        self.assertEqual(preferred, ["tableau"])
        job = vacancy("Junior Data Analyst")
        job["description"] += " Must have Power BI."
        result = main.score_job(job)
        self.assertIn("power bi (basic)", result["gaps"])
        self.assertEqual(result["decision"], "REVIEW")

    def test_manual_review_score_does_not_block_explicit_preparation(self):
        job = vacancy()
        job.update({
            "source": "jobs.cz", "decision": "REVIEW", "score": 42,
            "role_class": "expanded", "evidence_quality": "strong",
            "hard_experience": False,
        })
        self.assertTrue(main.manual_review_apply_eligible(job, True))
        self.assertFalse(main.manual_review_apply_eligible(job, False))
        job["evidence_quality"] = "weak"
        self.assertFalse(main.manual_review_apply_eligible(job, True))
        job["evidence_quality"] = "strong"
        job["source"] = "startupjobs.cz"
        self.assertFalse(main.manual_review_apply_eligible(job, True))

    def test_logged_score_shape_qualifies_with_entry_floor(self):
        result = main.score_job(vacancy())
        self.assertEqual(result["score"], 76)
        self.assertEqual(result["candidate_fit"], 10)
        self.assertEqual(len(result["expanded_signals"]), 5)
        self.assertEqual(result["expanded_candidate_fit_min"], 10)
        self.assertEqual(result["decision"], "APPLY")
        self.assertTrue(result["expanded_entry_promotion"])
        self.assertEqual(result["expanded_apply_blockers"], [])

    def test_explicit_entry_title_variants(self):
        for marker in ("Junior", "Student", "Intern", "Internship", "Trainee", "Graduate", "Absolvent", "Stáž"):
            with self.subTest(marker=marker):
                result = main.score_job(vacancy(f"{marker} Reporting Specialist"))
                self.assertEqual(result["expanded_candidate_fit_min"], 10)
                self.assertEqual(result["decision"], "APPLY")

    def test_regular_and_part_time_titles_keep_floor_12(self):
        for title in (REGULAR_TITLE, "Reporting Specialist", "Operations Analyst", "CRM Analyst"):
            with self.subTest(title=title):
                result = main.score_job(vacancy(title))
                if title != "CRM Analyst":
                    self.assertGreaterEqual(result["score"], 70)
                self.assertEqual(result["expanded_candidate_fit_min"], 12)
                self.assertEqual(result["decision"], "REVIEW")
                self.assertIn("candidate_fit=10 < 12", result["expanded_apply_blockers"])

    def test_entry_words_in_description_do_not_lower_floor(self):
        job = vacancy(REGULAR_TITLE)
        job["description"] += " Junior student intern trainee graduate welcome."
        result = main.score_job(job)
        self.assertEqual(result["expanded_candidate_fit_min"], 12)
        self.assertEqual(result["decision"], "REVIEW")

    def test_entry_skills_floor_has_a_lower_boundary(self):
        assessment = main.expanded_role_assessment(
            ENTRY_TITLE, vacancy()["description"], "strong", 9, False
        )
        self.assertFalse(assessment["eligible"])
        self.assertIn("candidate_fit=9 < 10", assessment["blockers"])

    def test_custom_regular_floor_is_never_raised_for_entry(self):
        with patch.object(main, "EXPANDED_MIN_CANDIDATE_FIT", 8):
            assessment = main.expanded_role_assessment(
                ENTRY_TITLE, vacancy()["description"], "strong", 8, False
            )
        self.assertEqual(assessment["candidate_fit_min"], 8)
        self.assertTrue(assessment["eligible"])

    def test_weak_and_medium_evidence_still_block_apply(self):
        for evidence in ("weak", "medium"):
            with self.subTest(evidence=evidence):
                job = vacancy()
                job["evidence_quality"] = evidence
                result = main.score_job(job)
                self.assertNotEqual(result["decision"], "APPLY")
                self.assertIn(f"evidence={evidence} (requires strong)", result["expanded_apply_blockers"])

    def test_hard_experience_and_seniority_still_block_apply(self):
        job = vacancy()
        job["description"] += " Minimum 3 years experience."
        result = main.score_job(job)
        self.assertTrue(result["hard_experience"])
        self.assertNotEqual(result["decision"], "APPLY")
        self.assertIn("hard 3+ years experience requirement", result["expanded_apply_blockers"])
        self.assertEqual(main.score_job(vacancy("Senior Junior Reporting Specialist"))["decision"], "SKIP")

    def test_signal_count_and_central_signal_still_required(self):
        assessment = main.expanded_role_assessment(
            ENTRY_TITLE, "SQL reporting", "strong", 10, False
        )
        self.assertFalse(assessment["eligible"])
        self.assertIn("data_signals=2 < 3", assessment["blockers"])
        with patch.object(main, "EXPANDED_MIN_DATA_SIGNALS", 2):
            assessment = main.expanded_role_assessment(
                "Junior Data Quality Specialist", "Excel data quality", "strong", 10, False
            )
        self.assertFalse(assessment["eligible"])
        self.assertIn("no central data signal", assessment["blockers"])

    def test_operations_and_crm_still_need_an_extra_signal(self):
        for title in ("Junior Operations Analyst", "Student CRM Analyst"):
            with self.subTest(title=title):
                eligible, signals = main.expanded_role_eligible(
                    title, "SQL Excel reporting", "strong", 12, False
                )
                self.assertEqual(len(signals), 3)
                self.assertFalse(eligible)

    def test_score_floor_is_not_relaxed(self):
        job = vacancy()
        job["description"] = "SQL Excel reporting " + "Team documentation. " * 90
        result = main.score_job(job)
        self.assertTrue(result["expanded_role_eligible"])
        self.assertLess(result["score"], 70)
        self.assertEqual(result["decision"], "REVIEW")
        self.assertIn(f"score={result['score']} < 70", result["expanded_apply_blockers"])

    def test_target_entry_scoring_remains_available(self):
        result = main.score_job(vacancy("Data Analytics Internship"))
        self.assertEqual(result["decision"], "APPLY")
        self.assertIsNone(result["expanded_candidate_fit_min"])
        self.assertFalse(result["expanded_entry_promotion"])

    def test_diagnostics_survive_snapshot_and_csv(self):
        job = vacancy(REGULAR_TITLE)
        job.update(main.score_job(job))
        job["location_gate"] = "prague_area"
        job["reasons"].append("location_gate:diagnostic_after_first_12_reasons")
        reason = "; ".join(job["reasons"])
        main.save_status(job, "REVIEW_PENDING", job["score"], reason)
        snapshot = json.loads(main.VACANCIES_FILE.read_text().splitlines()[-1])
        self.assertEqual(snapshot["candidate_fit"], 10)
        self.assertEqual(snapshot["expanded_candidate_fit_min"], 12)
        self.assertEqual(snapshot["expanded_apply_blockers"], ["candidate_fit=10 < 12"])
        self.assertEqual(snapshot["location_gate"], "prague_area")
        with main.APPLICATIONS_FILE.open(newline="", encoding="utf-8") as fh:
            record = list(csv.DictReader(fh))[-1]
        self.assertEqual(record["reason"], reason)
        self.assertEqual(main.load_processed(), set())


class PreparationGuardsTests(ScoringDefaults, unittest.IsolatedAsyncioTestCase):
    async def test_location_blocks_preparation_for_outside_and_unknown(self):
        for location, expected_status in (("Brno", "SKIPPED"), ("", "REVIEW_PENDING")):
            with self.subTest(location=location):
                job = vacancy(location=location)
                prepare = AsyncMock(return_value=("FORM_READY", "test", job["url"], {}))
                with patch.object(main, "enrich_job", side_effect=lambda j, _: j), \
                        patch.object(main, "prepare_application", prepare), \
                        contextlib.redirect_stdout(io.StringIO()):
                    status, reason, _, _ = await main.prepare_single_job(job)
                self.assertEqual(status, expected_status)
                self.assertIn("location_gate:", reason)
                prepare.assert_not_awaited()

    async def test_confirmed_submission_still_blocks_prepare_now(self):
        job = vacancy()
        job.update(main.score_job(job))
        main.save_status(job, "SUBMITTED_MANUALLY", job["score"], "Synthetic history")
        prepare = AsyncMock()
        with patch.object(main, "prepare_application", prepare), \
                patch.object(main, "enrich_job") as enrich, \
                contextlib.redirect_stdout(io.StringIO()):
            status, _, _, _ = await main.prepare_single_job(job)
        self.assertEqual(status, "ALREADY_SUBMITTED")
        enrich.assert_not_called()
        prepare.assert_not_awaited()

    async def test_full_run_routes_only_eligible_entry_to_preparation(self):
        jobs = [
            vacancy(),
            vacancy(REGULAR_TITLE, job_id="2000000002"),
            vacancy(location="", job_id="2000000003"),
            vacancy(location="Brno", job_id="2000000004"),
        ]
        cv = Path(self.state.name) / "synthetic-cv.txt"
        cv.write_text("Offline fixture", encoding="utf-8")
        prepare = AsyncMock(return_value=("FORM_READY", "Offline fixture", "", {}))
        log = io.StringIO()
        previous_cwd = Path.cwd()
        try:
            os.chdir(self.state.name)
            with patch.object(main, "CV_PATH", str(cv)), \
                    patch.object(main, "discover_all", AsyncMock(return_value=jobs)), \
                    patch.object(main, "enrich_job", side_effect=lambda j, _: j), \
                    patch.object(main, "browser_recover_weak_evidence", AsyncMock(side_effect=lambda j: j)), \
                    patch.object(main, "prepare_application", prepare), \
                    contextlib.redirect_stdout(log):
                await main.main()
        finally:
            os.chdir(previous_cwd)
        prepare.assert_awaited_once()
        self.assertEqual(prepare.await_args.args[0]["job_id"], "2000000001")
        snapshots = [json.loads(line) for line in main.VACANCIES_FILE.read_text().splitlines()]
        by_id = {j["job_id"]: j for j in snapshots}
        self.assertEqual(by_id["job:2000000002"]["decision"], "REVIEW")
        self.assertEqual(by_id["job:2000000003"]["decision"], "REVIEW")
        self.assertIn("location_gate:unknown_location", by_id["job:2000000003"]["reason"])
        self.assertEqual(by_id["job:2000000004"]["decision"], "SKIP")
        self.assertIn("candidate_fit=10", log.getvalue())
        self.assertIn("expanded_fit_min=12", log.getvalue())
        self.assertIn("candidate_fit=10 < 12", log.getvalue())


if __name__ == "__main__":
    unittest.main()
