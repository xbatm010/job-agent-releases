"""User-confirmed rejection closure cannot fake a Jobs.cz final submission."""
import csv
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import desktop
import main


def sanofi():
    return {
        "job_id": "job:2001443223",
        "title": "Analytics and PowerBI Development Intern",
        "company": "Sanofi",
        "source": "jobs.cz",
        "status": "PRE_APPLY_CONFIRMATION_REQUIRED",
        "decision": "APPLY",
        "url": "https://www.jobs.cz/rpd/2001443223/",
        "handoff_url": "https://www.jobs.cz/externi-jof/2001443223/",
    }


class RejectedHandoffSafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.history = root / "applications.csv"
        self.overrides = root / "job_overrides.json"
        for module in (desktop, main):
            for attribute, value in (
                ("HISTORY_FILE" if module is desktop else "APPLICATIONS_FILE", self.history),
                ("OVERRIDES_FILE", self.overrides),
            ):
                p = patch.object(module, attribute, value)
                p.start()
                self.addCleanup(p.stop)
        with self.history.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=["job_id", "title", "company", "url", "score",
                                 "role_class", "decision", "status", "reason"]
            )
            writer.writeheader()
            writer.writerow({
                "job_id": "job:2001443223",
                "title": "Analytics and PowerBI Development Intern",
                "company": "Sanofi",
                "url": sanofi()["url"],
                "score": "83",
                "role_class": "target",
                "decision": "APPLY",
                "status": "PRE_APPLY_CONFIRMATION_REQUIRED",
            })
            writer.writerow({
                "job_id": "job:2001467931",
                "title": "ServiceDesk",
                "company": "2. lékařská fakulta",
                "status": "SUBMITTED_MANUALLY",
            })
        self.original_history = self.history.read_bytes()

    def test_closure_is_atomic_and_does_not_rewrite_submission_history(self):
        self.assertEqual(main.load_pending_manual_handoffs(), {"job:2001443223"})
        self.assertEqual(desktop.processed_count(), 1)
        self.assertEqual(main.load_processed(), {"job:2001467931"})
        entry = desktop.close_rejected_handoff(sanofi(), "Отказ по email")
        self.assertEqual(entry["decision"], "CLOSED_REJECTED")
        self.assertEqual(entry["reason"], "employer_rejection_reported_by_user")
        self.assertEqual(entry["note"], "Отказ по email")
        self.assertTrue(entry["closed_at"])
        self.assertEqual(self.original_history, self.history.read_bytes())
        self.assertEqual(main.load_pending_manual_handoffs(), set())
        self.assertEqual(main.load_processed(), {"job:2001467931"})
        self.assertEqual(desktop.processed_count(), 1)
        stored = json.loads(self.overrides.read_text())
        self.assertEqual(stored["job:2001443223"]["decision"], "CLOSED_REJECTED")

    def test_closed_handoff_cannot_be_rediscoved_for_enrichment(self):
        desktop.close_rejected_handoff(sanofi())
        closed = {
            key for key, value in main.load_job_overrides().items()
            if value.get("decision") in {"INACTIVE", "CLOSED_REJECTED"}
        }
        self.assertEqual(closed, {"job:2001443223"})
        listings = [
            {"source": "jobs.cz", "job_id": "2001443223",
             "title": "Analytics and PowerBI Development Intern", "location": "Praha"},
            {"source": "jobs.cz", "job_id": "2001600001",
             "title": "Junior Data Analyst", "location": "Praha"},
        ]
        selected = main.select_discovery_candidates(listings, main.load_processed(), closed, 10)
        self.assertEqual([x["job_id"] for x in selected], ["2001600001"])
        counts = main.discovery_filter_breakdown(listings, main.load_processed(), closed, set())
        self.assertEqual(counts["data"]["inactive"], 1)

    def test_other_pending_handoffs_are_preserved(self):
        with self.history.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["job:2001400100", "Other handoff", "", "", "", "",
                             "APPLY", "PRE_APPLY_CONFIRMATION_REQUIRED", ""])
        self.assertEqual(len(main.load_pending_manual_handoffs()), 2)
        desktop.close_rejected_handoff(sanofi())
        self.assertEqual(main.load_pending_manual_handoffs(), {"job:2001400100"})

    def test_rejects_non_pending_and_submitted_without_modifying_history(self):
        with self.assertRaises(ValueError):
            desktop.close_rejected_handoff(dict(sanofi(), status="SUBMITTED_MANUALLY"))
        with self.assertRaises(ValueError):
            desktop.close_rejected_handoff(dict(sanofi(), source="startupjobs.cz"))
        with self.assertRaises(ValueError):
            desktop.close_rejected_handoff(dict(sanofi(), job_id="job:2001467931"))
        with self.assertRaises(ValueError):
            desktop.close_rejected_handoff(sanofi(), "x" * 1001)
        self.assertEqual(self.history.read_bytes(), self.original_history)
        self.assertFalse(self.overrides.exists())

    def test_reclosing_does_not_erase_original_note_or_date(self):
        first = desktop.close_rejected_handoff(sanofi(), "Первый ответ")
        second = desktop.close_rejected_handoff(sanofi(), "Попытка изменить")
        self.assertEqual(first, second)
        self.assertEqual(second["note"], "Первый ответ")
        self.assertEqual(main.load_pending_manual_handoffs(), set())

    def test_reopen_restores_pending_without_inventing_submission(self):
        desktop.close_rejected_handoff(sanofi())
        self.assertTrue(desktop.delete_job_override(sanofi()["job_id"]))
        self.assertEqual(main.load_pending_manual_handoffs(), {"job:2001443223"})
        self.assertEqual(main.load_processed(), {"job:2001467931"})


if __name__ == "__main__":
    unittest.main()
