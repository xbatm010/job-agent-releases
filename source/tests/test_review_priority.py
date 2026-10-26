"""Offline REVIEW tie-breaking regression."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as folder:
    with patch.dict(os.environ, {"STATE_DIR": folder}):
        import main


class RankingTests(unittest.TestCase):
    def test_equal_scores_sort_by_verified_constraints_not_input_order(self):
        def row(name, fit, blockers=(), exp=False):
            return dict(job_id=name, title="Junior Tester", source="jobs.cz",
                        role_class="target", decision="REVIEW", score=69,
                        candidate_fit=fit, evidence_quality="strong",
                        location_gate="prague_area", hard_experience=False,
                        junior_experience_requirement=exp,
                        entry_role=True, target_apply_blockers=list(blockers))
        risky = row("risky", 24, ("1-2 years experience requirement or ambiguous range",), True)
        qualified = row("better", 16, ("fewer than 2 familiar skill signals",))
        weaker = row("weaker", 8, ("fewer than 2 familiar skill signals",
                                   "fewer than 2 independent role signals"))
        with patch.object(main, "SEARCH_SUPPORT_QA", False):
            result = main.select_review_shortlist([risky, weaker, qualified], 3)
        self.assertEqual([job["job_id"] for job in result],
                         ["better", "weaker", "risky"])
        self.assertTrue(all(job["decision"] == "REVIEW" for job in result))
