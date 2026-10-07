"""Exercise the real Qt widgets offscreen with isolated local history."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
import desktop
from desktop_theme import vacancy_detail_html


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(patch.stopall)
        self.records = [
            dict(job_id="job:2000000001", title="Junior Reporting Specialist", company="Example", score=76, decision="APPLY", status="READY_TO_PREPARE", source="jobs.cz", url="https://www.jobs.cz/rpd/2000000001/", evidence_quality="strong", description="SQL Excel reporting", candidate_fit=10, expanded_candidate_fit_min=10, entry_role=True),
            dict(job_id="job:2000000002", title="Submitted analyst", company="Example", score=81, decision="REVIEW", status="REVIEW_PENDING", source="jobs.cz", url="https://www.jobs.cz/rpd/2000000002/"),
            dict(job_id="startupjobs.cz:3", title="Data Analyst", company="Example", score=75, decision="REVIEW", status="REVIEW_PENDING", source="startupjobs.cz", url="https://www.startupjobs.cz/nabidka/3/data-analyst"),
        ]
        self.overrides = {"job:2000000002": {"decision": "REVIEW"}}
        patch.object(desktop, "load_settings", return_value=dict(desktop.DEFAULTS, auto_check_updates=False)).start()
        patch.object(desktop, "load_vacancy_records", side_effect=lambda: copy.deepcopy(self.records)).start()
        patch.object(desktop, "terminal_job_ids", return_value={"job:2000000002"}).start()
        patch.object(desktop, "load_job_overrides", side_effect=lambda: self.overrides).start()
        patch.object(desktop, "processed_count", return_value=1).start()
        patch.object(desktop, "HISTORY_FILE", Path(self.temp.name) / "applications.csv").start()
        patch.object(desktop, "SETTINGS_FILE", Path(self.temp.name) / "settings.json").start()
        self.window = desktop.JobAgentWindow()
        self.window.timer.stop()
        self.window.stats_timer.stop()
        self.addCleanup(self.window.deleteLater)

    def filter(self, value):
        combo = self.window.dashboard_decision_filter
        combo.setCurrentIndex(combo.findData(value))

    def test_history_and_translated_filters_keep_submitted_out_of_apply(self):
        self.filter("APPLY")
        self.assertEqual([r["job_id"] for r in self.window.dashboard_records], ["job:2000000001"])
        self.filter("SUBMITTED")
        self.assertEqual(len(self.window.dashboard_records), 1)
        self.assertFalse(self.window.prepare_now_btn.isEnabled())
        self.assertEqual(self.window.applications_table.rowCount(), 1)

    def test_search_matches_description_and_empty_state_disables_actions(self):
        self.window.dashboard_search.setText("SQL")
        self.assertEqual(len(self.window.dashboard_records), 1)
        self.window.dashboard_search.setText("No such vacancy")
        self.assertEqual(len(self.window.dashboard_records), 0)
        self.assertFalse(self.window.prepare_now_btn.isEnabled())
        self.assertFalse(self.window.open_job_btn.isEnabled())

    def test_search_only_requires_no_profile_but_explicit_preparation_does(self):
        settings = self.window._collect_settings()
        self.assertTrue(settings["search_only"])
        self.assertEqual(self.window._validate_settings(settings), "")
        self.assertNotEqual(self.window._validate_settings(settings, require_application=True), "")
        self.assertEqual(desktop.child_env(settings)["SEARCH_ONLY"], "true")
        self.assertEqual(desktop.child_env(settings)["AUTO_SUBMIT"], "false")
        self.window.search_only_check.setChecked(False)
        self.assertEqual(self.window.start_btn.text(), "Найти и подготовить")

    def test_startupjobs_preparation_is_disabled(self):
        combo = self.window.dashboard_source_filter
        combo.setCurrentIndex(combo.findData("startupjobs.cz"))
        self.assertFalse(self.window.prepare_now_btn.isEnabled())
        self.assertTrue(self.window.open_job_btn.isEnabled())

    def test_live_log_and_vacancy_html_do_not_interpret_external_markup(self):
        self.window._append_log("<b>literal text</b>")
        self.assertIn("<b>literal text</b>", self.window.log.toPlainText())
        html = vacancy_detail_html({"title": "<script>alert(1)</script>", "description": '<img src="file:///private">'}, "REVIEW")
        self.assertNotIn("<script>", html)
        self.assertNotIn('<img src=', html)

    def test_source_status_is_visible_and_has_diagnostics_tooltip(self):
        path = Path(self.temp.name) / "discovery_status.json"
        path.write_text(json.dumps({"saved_at": "2026-10-07", "sources": {"startupjobs.cz": {"status": "empty", "count": 0, "details": ["HTTP 200; parsed=0"]}}}))
        self.window._refresh_source_status()
        badge = self.window.source_badges["startupjobs.cz"]
        self.assertIn("нужна проверка", badge.text())
        self.assertIn("HTTP 200", badge.toolTip())

    def test_navigation_settings_and_search_mode_persist(self):
        self.window.nav_buttons[1].click()
        self.assertEqual(self.window.workspace_tabs.currentIndex(), 1)
        self.window._open_settings(4)
        self.assertEqual(self.window.settings_tabs.currentIndex(), 4)
        self.window.search_only_check.setChecked(False)
        self.window._save_preferences()
        settings = json.loads(desktop.SETTINGS_FILE.read_text())
        self.assertFalse(settings["search_only"])
        self.assertEqual(settings["min_apply"], 66)

    def test_responsive_layout_leaves_room_for_details(self):
        self.window.resize(1380, 900)
        self.window.show()
        self.app.processEvents()
        self.assertEqual(self.window.dashboard_splitter.orientation(), Qt.Horizontal)
        self.window.resize(960, 760)
        self.app.processEvents()
        self.assertEqual(self.window.dashboard_splitter.orientation(), Qt.Vertical)
        self.assertGreaterEqual(self.window.dashboard_detail.viewport().height(), 130)
        self.assertGreaterEqual(self.window.dashboard_table.viewport().height(), 70)
        self.window.hide()

