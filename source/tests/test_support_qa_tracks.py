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

    def test_sales_support_in_czech_is_not_it_helpdesk(self):
        for title in (
            "Technická podpora prodeje - Specialista/ka technických nabídek",
            "TECHNICKÁ PODPORA PRODEJE",
            "Sales Support Specialist",
            "Presales IT Support",
        ):
            with self.subTest(title=title):
                self.assertIsNone(support_qa_track(title))
                self.assertNotIn(
                    main.score_job(vacancy(title)).get("role_track"),
                    {"support", "qa"},
                )

    def test_non_junior_support_review_is_not_misleadingly_88_points(self):
        result = main.score_job(vacancy("IT podpora uživatelů", SUPPORT_DESCRIPTION))
        self.assertEqual(result["decision"], "REVIEW")
        self.assertLessEqual(result["score"], 69)
        self.assertIn("junior/trainee/L1 marker absent", result["target_apply_blockers"])

    def test_generic_l1_support_requires_actual_practical_signal(self):
        text = ("L1 IT support to end users with user support, "
                "technical documentation, Windows and macOS. ") * 30
        result = main.score_job(vacancy("L1 IT Support Specialist", text))
        self.assertEqual(result["decision"], "REVIEW")
        self.assertLessEqual(result["score"], 69)
        self.assertIn("no concrete diagnostic/test evidence", result["target_apply_blockers"])

    def test_review_shortlist_reserves_data_support_and_qa_slots(self):
        jobs = []
        for group, name, count, score in [
            ("data", "Junior Data Analyst", 35, 60),
            ("support", "IT Support Technician", 35, 69),
            ("qa", "Manual Tester", 12, 68),
        ]:
            for idx in range(count):
                jobs.append({
                    "title": name, "job_id": f"{group}-{idx}",
                    "role_track": group, "decision": "REVIEW", "score": score,
                })
        shortlist = main.select_review_shortlist(jobs, 36)
        self.assertEqual(len(shortlist), 36)
        self.assertEqual(
            {group: sum(x["role_track"] == group for x in shortlist)
             for group in ("data", "support", "qa")},
            {"data": 18, "support": 12, "qa": 6},
        )
        with patch.object(main, "SEARCH_SUPPORT_QA", False):
            unbalanced = main.select_review_shortlist(jobs, 36)
        self.assertEqual(unbalanced[0]["role_track"], "support")

    def test_shortlist_unused_qa_quota_fills_with_other_jobs(self):
        jobs = []
        for group, count in [("data", 25), ("support", 25), ("qa", 2)]:
            for idx in range(count):
                jobs.append({
                    "title": group, "role_track": group,
                    "job_id": f"{group}-{idx}",
                    "decision": "REVIEW", "score": 60 + idx,
                })
        shortlist = main.select_review_shortlist(jobs, 36)
        self.assertEqual(len(shortlist), 36)
        self.assertEqual(len(set(x["job_id"] for x in shortlist)), 36)
        self.assertGreaterEqual(sum(x["role_track"] == "data" for x in shortlist), 18)
        self.assertEqual(sum(x["role_track"] == "qa" for x in shortlist), 2)

    def test_shortlist_does_not_fill_reserved_slots_with_skip(self):
        rows = [
            {"title": "Junior Data Analyst", "job_id": f"skip-{i}",
             "role_track": "data", "decision": "SKIP", "score": 0}
            for i in range(30)
        ] + [
            {"title": "Junior QA Tester", "job_id": f"qa-{i}",
             "role_track": "qa", "decision": "REVIEW", "score": 65}
            for i in range(40)
        ]
        shortlist = main.select_review_shortlist(rows, 36)
        self.assertTrue(all(r["decision"] == "REVIEW" for r in shortlist))

    def test_track_diagnostics_distinguish_candidate_supply_from_rejections(self):
        jobs = [
            {"title": "Junior Data Analyst", "decision": "REVIEW"},
            {"title": "Junior QA Tester", "role_track": "qa", "decision": "SKIP"},
            {"title": "IT Support Specialist", "role_track": "support", "decision": "REVIEW"},
            {"title": "Finance Clerk", "decision": "SKIP"},
        ]
        self.assertEqual(
            main.search_track_counts(jobs),
            {"data": 1, "support": 1, "qa": 1, "other": 1},
        )
        self.assertEqual(
            main.search_track_counts(jobs, {"APPLY", "REVIEW"}),
            {"data": 1, "support": 1, "qa": 0, "other": 0},
        )

    def test_manual_review_suggestions_are_diverse_when_safe(self):
        def job(title, track, score):
            return {
                "title": title, "role_track": track,
                "source": "jobs.cz", "role_class": "target",
                "evidence_quality": "strong", "location_gate": "prague_area",
                "hard_experience": False, "decision": "REVIEW",
                "score": score, "candidate_fit": 20, "job_id": title,
            }
        candidates = [
            job("IT Support Specialist", "support", 69),
            job("IT podpora", "support", 69),
            job("Helpdesk", "support", 69),
            job("Junior Data Analyst", "data", 67),
            job("QA Analyst", "qa", 65),
        ]
        selected = main.safe_manual_review_candidates(candidates, 3)
        self.assertEqual(
            [x["role_track"] for x in selected],
            ["data", "qa", "support"],
        )
        self.assertEqual(len(selected), 3)
        # Never present weak-evidence QA only to satisfy track diversity.
        candidates[-1]["evidence_quality"] = "weak"
        selected = main.safe_manual_review_candidates(candidates, 3)
        self.assertEqual(
            [x["role_track"] for x in selected],
            ["data", "support", "support"],
        )

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
