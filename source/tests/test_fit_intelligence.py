"""Offline Fit Intelligence diagnostics; no network calls or application actions."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fit_intelligence import (
    blocker_categories, format_fit_summary, save_fit_report, summarize_fit,
)


class FitIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.stages = {
            "discovered": 180, "selected_for_enrichment": 108,
            "deduplicated": 105, "scored": 105, "shortlisted": 36,
        }

    def test_all_scored_tracks_and_primary_blockers_without_false_promotions(self):
        rows = [
            {"track": "data", "decision": "REVIEW",
             "evidence_quality": "weak", "target_apply_blockers": [
                 "candidate_fit=4 < 6",
             ], "title": "PRIVATE TITLE", "description": "PRIVATE DESCRIPTION",
             "job_id": "PRIVATE-ID", "url": "https://example.invalid/private"},
            {"track": "qa", "decision": "REVIEW", "evidence_quality": "strong",
             "target_apply_blockers": ["junior/trainee/L1 marker absent",
                                       "fewer than 2 independent role signals"]},
            {"track": "support", "decision": "REVIEW", "evidence_quality": "strong",
             "hard_experience": True, "target_apply_blockers": [
                 "experience 3+ years requirement"]},
            {"track": "data", "decision": "REVIEW", "evidence_quality": "strong",
             "source": "startupjobs.cz", "role_class": "target"},
            {"track": "data", "decision": "APPLY", "evidence_quality": "strong",
             "target_apply_blockers": []},
            {"track": "other", "decision": "SKIP", "evidence_quality": "strong",
             "reasons": ["desktop_override:SKIP"]},
        ]
        original_decisions = [r["decision"] for r in rows]
        report = summarize_fit(rows, self.stages, recorded_at="2026-10-26T12:00:00+01:00")
        self.assertEqual(report["decisions"], {"APPLY": 1, "REVIEW": 4, "SKIP": 1})
        self.assertEqual(report["by_track"]["data"], {"APPLY": 1, "REVIEW": 2, "SKIP": 0})
        self.assertEqual(report["primary_blockers"], {
            "entry_level": 1, "evidence": 1, "experience": 1, "manual": 1, "source": 1,
        })
        self.assertEqual(report["all_blockers"]["skills_fit"], 1)
        self.assertEqual(report["stages"]["selected_for_enrichment"], 108)
        self.assertEqual(original_decisions, [r["decision"] for r in rows])
        as_json = json.dumps(report, ensure_ascii=False)
        for forbidden in ("PRIVATE TITLE", "PRIVATE DESCRIPTION", "PRIVATE-ID", "example.invalid"):
            self.assertNotIn(forbidden, as_json)

    def test_explicit_requirements_and_unknown_location(self):
        blocked = {
            "decision": "REVIEW", "evidence_quality": "strong",
            "location_gate": "location_unknown",
            "target_apply_blockers": [
                "missing_required_skills=tableau",
                "candidate_fit=4 < 6",
                "candidate_fit=4 < 6",
            ],
        }
        self.assertEqual(blocker_categories(blocked),
                         ["location", "required_skills", "skills_fit"])
        self.assertEqual(blocker_categories(
            {"decision": "APPLY", "evidence_quality": "weak"}
        ), [])

    def test_zero_apply_and_empty_rows_are_explained(self):
        report = summarize_fit(
            [{"decision": "REVIEW", "evidence_quality": "medium",
              "target_apply_blockers": ["candidate_fit=0 < 6"]}],
            self.stages, recorded_at="2026-10-26T12:00:00+01:00",
        )
        self.assertIn("APPLY 0", format_fit_summary(report))
        self.assertIn("недостаточно данных вакансии", format_fit_summary(report))
        empty = summarize_fit([], {}, recorded_at="2026-10-26T12:00:00+01:00")
        self.assertEqual(empty["decisions"]["APPLY"], 0)
        self.assertEqual(empty["stages"]["scored"], 0)
        self.assertIn("не обнаружены", format_fit_summary(empty))
        self.assertEqual(format_fit_summary({"schema": 99}), "")

    def test_local_report_is_atomic_aggregate_and_valid_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "local" / "fit_report.json"
            report = summarize_fit([], {}, recorded_at="2026-10-26T12:00:00+01:00")
            save_fit_report(report, path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), report)
            self.assertEqual(list(path.parent.glob("*.tmp")), [])
            self.assertEqual(list(path.parent.glob(".fit-report-*")), [])


if __name__ == "__main__":
    unittest.main()
