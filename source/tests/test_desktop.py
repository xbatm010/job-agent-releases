"""Exercise the real Qt widgets offscreen with isolated local history."""
import copy
import csv
import json
from datetime import datetime, timedelta
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel
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
        patch.object(desktop, "RESPONSE_FILE", Path(self.temp.name) / "employer_responses.json").start()
        patch.object(desktop, "SETTINGS_FILE", Path(self.temp.name) / "settings.json").start()
        self.window = desktop.JobAgentWindow()
        self.window.timer.stop()
        self.window.stats_timer.stop()
        self.addCleanup(self.window.deleteLater)

    def filter(self, value):
        combo = self.window.dashboard_decision_filter
        combo.setCurrentIndex(combo.findData(value))

    def test_followup_metrics_deduplicate_confirmed_applications(self):
        now = datetime(2026, 10, 13, 10, 0)
        records = [
            {"job_id": "job:111", "title": "Junior Analyst", "status": "REVIEW_PENDING"},
            {"job_id": "job:111", "title": "Junior Analyst", "status": "REVIEW_PENDING"},
            {"job_id": "job:222", "title": "BI Specialist", "status": "REVIEW_PENDING"},
            {"job_id": "job:333", "title": "Reporting Analyst", "status": "REVIEW_PENDING"},
            {"job_id": "job:444", "title": "Data Specialist", "status": "REVIEW_PENDING"},
        ]
        for record in records:
            record["status"] = "REVIEW_PENDING"
        responses = {
            "job:111": {
                "stage": "INTERVIEW_SCHEDULED",
                "next_date": "2026-10-13 09:30",
            },
            "job:222": {
                "stage": "REJECTED",
                "next_date": "2026-10-12",
            },
            "job:333": {
                "stage": "OFFER",
                "next_date": "2026-10-14",
            },
            "job:444": {
                "stage": "WAITING",
                "next_date": "2026-10-11",
            },
            "job:unsubmitted": {
                "stage": "INTERVIEW_COMPLETED",
                "next_date": "2026-10-01",
            },
        }
        stats, tasks = desktop.application_followup_overview(
            records,
            {"job:111", "job:222", "job:333", "job:444"},
            responses, now,
        )
        self.assertEqual(stats, dict(
            sent=4, replies=3, interviews=1, rejected=1,
            offers=1, due=2, next_week=1,
        ))
        self.assertEqual(
            [(x["job_id"], x["bucket"]) for x in tasks],
            [("job:444", "due"), ("job:111", "due"), ("job:333", "next_week")],
        )
        self.assertNotIn("job:222", [x["job_id"] for x in tasks])
        self.assertNotIn("job:unsubmitted", [x["job_id"] for x in tasks])

    def test_followup_date_validation_and_local_day_semantics(self):
        now = datetime(2026, 10, 13, 10, 0)
        cases = {
            "2026-10-12": "due",
            "2026-10-13": "due",
            "2026-10-13 09:59": "due",
            "2026-10-13 10:01": "next_week",
            "2026-10-20": "next_week",
            "2026-10-21": "later",
            "": "", "tomorrow": "", "2026-13-20": "",
        }
        for when, expected in cases.items():
            with self.subTest(date=when):
                self.assertEqual(desktop.followup_due_bucket(when, now), expected)

    def test_followup_tab_shows_due_tasks_and_opens_dashboard_without_reapplying(self):
        jid = "job:2000000002"
        desktop.save_response_tracking(
            jid, "INTERVIEW_SCHEDULED", "Call recruiter first", "2026-01-10",
        )
        self.window._refresh_dashboard()
        self.assertEqual(self.window.followups_table.rowCount(), 1)
        self.assertIn("Отправлено: 1", self.window.response_metrics.text())
        self.assertIn("Ответы: 1", self.window.response_metrics.text())
        self.assertIn("На этапе интервью: 1", self.window.response_metrics.text())
        self.assertIn("Требуют внимания: 1", self.window.followups_summary.text())
        self.assertEqual(self.window.followups_table.item(0, 3).text(), "Срок наступил")
        self.window.filter("All") if hasattr(self.window, "filter") else self.filter("All")
        self.window.dashboard_table.selectRow(0)
        self.window.followups_table.selectRow(0)
        self.window.open_followup_btn.click()
        self.assertEqual(
            self.window._selected_dashboard_record()["job_id"], jid,
        )
        self.assertFalse(self.window.prepare_now_btn.isEnabled())
        self.assertEqual(self.window.workspace_tabs.currentIndex(), 0)
        self.assertFalse(desktop.HISTORY_FILE.exists())

    def test_response_stage_persistence_is_atomic_and_not_application_submission(self):
        jid = "job:2000000002"
        history_before = desktop.HISTORY_FILE.read_bytes() if desktop.HISTORY_FILE.exists() else b""
        self.assertEqual(desktop.load_response_tracking(), {})
        entry = desktop.save_response_tracking(
            jid, "INTERVIEW_SCHEDULED", "<b>HR call</b>", "2026-10-24 14:30"
        )
        self.assertEqual(entry["stage"], "INTERVIEW_SCHEDULED")
        self.assertEqual(desktop.load_response_tracking()[jid]["next_date"], "2026-10-24 14:30")
        self.assertEqual(desktop.HISTORY_FILE.read_bytes() if desktop.HISTORY_FILE.exists() else b"", history_before)
        with self.assertRaises(ValueError):
            desktop.save_response_tracking(jid, "SUBMITTED_MANUALLY")
        with self.assertRaises(ValueError):
            desktop.save_response_tracking(jid, "OFFER", next_date="tomorrow")
        self.assertEqual(
            desktop.load_response_tracking()[jid]["stage"], "INTERVIEW_SCHEDULED"
        )
        desktop.RESPONSE_FILE.write_text("{ invalid JSON", encoding="utf-8")
        self.assertEqual(desktop.load_response_tracking(), {})

    def test_response_stage_ui_is_explicit_only_for_submitted_jobs(self):
        self.window._refresh_dashboard()
        self.window.dashboard_table.selectRow(0)
        self.assertFalse(self.window.response_action.isEnabled())

        submitted_index = next(
            i for i, record in enumerate(self.window.dashboard_records)
            if record["job_id"] == "job:2000000002"
        )
        self.window.dashboard_table.selectRow(submitted_index)
        self.assertTrue(self.window.response_action.isEnabled())
        self.assertTrue(self.window.response_summary.isVisible() or not self.window.isVisible())
        self.assertIn("Ожидаем ответ", self.window.response_summary.text())

        def set_dialog_fields(dialog):
            combo = dialog.findChild(desktop.QComboBox, "response_stage_combo")
            stage_index = combo.findData("INTERVIEW_SCHEDULED")
            self.assertGreater(stage_index, 0)
            combo.setCurrentIndex(stage_index)
            dialog.findChild(desktop.QLineEdit, "response_next_date").setText("2026-10-24 14:30")
            dialog.findChild(desktop.QTextEdit, "response_notes").setPlainText("<hr> Invitation")
            return desktop.QDialog.Accepted

        with patch.object(desktop.QDialog, "exec", set_dialog_fields):
            self.window.response_action.trigger()
        data = desktop.load_response_tracking()["job:2000000002"]
        self.assertEqual(data["stage"], "INTERVIEW_SCHEDULED")
        self.assertEqual(data["notes"], "<hr> Invitation")
        self.assertEqual(
            self.window.dashboard_decision_filter.findData("RESPONDED") >= 0,
            True,
        )
        self.assertIn("Собеседование назначено", self.window.response_summary.text())
        self.assertIn("<hr> Invitation", self.window.response_summary.text())
        self.assertEqual(self.window.response_summary.textFormat(), Qt.PlainText)

        self.window.extra_filter_actions["RESPONDED"].trigger()
        self.assertEqual(
            [r["job_id"] for r in self.window.dashboard_records],
            ["job:2000000002"],
        )
        self.assertFalse(self.window.prepare_now_btn.isEnabled())
        with patch.object(desktop.QDialog, "exec", return_value=desktop.QDialog.Rejected):
            self.window.response_action.trigger()
        self.assertEqual(desktop.load_response_tracking()["job:2000000002"], data)

        self.window.filter("All") if hasattr(self.window, "filter") else self.filter("All")
        self.window.dashboard_table.selectRow(0)
        with patch.object(desktop.QMessageBox, "information") as info:
            self.window._edit_response_tracking()
        info.assert_called_once()
        self.assertEqual(len(desktop.load_response_tracking()), 1)

    def test_needs_attention_filter_shows_incomplete_forms_and_manual_handoffs(self):
        self.records[0]["status"] = "FORM_PARTIALLY_FILLED"
        self.records[0]["title"] = "Data Governance and Data Quality Specialist"
        self.records[1]["status"] = "FORM_PARTIALLY_FILLED"  # submitted in history
        self.records.append(dict(
            job_id="job:2001443223",
            title="Sanofi PowerBI Intern",
            company="Sanofi", score=79, decision="APPLY",
            status="PRE_APPLY_CONFIRMATION_REQUIRED",
            source="jobs.cz",
            url="https://www.jobs.cz/rpd/2001443223/",
            handoff_url="https://www.jobs.cz/externi-jof/2001443223/",
        ))
        self.records.append(dict(
            job_id="job:2000000005", title="Old archived incomplete",
            company="Old", score=62, decision="REVIEW",
            status="FORM_PARTIALLY_FILLED", source="jobs.cz",
        ))
        self.overrides["job:2000000005"] = {"decision": "INACTIVE"}
        self.window._refresh_dashboard()
        self.assertIn("ATTENTION", self.window.extra_filter_actions)
        self.window.extra_filter_actions["ATTENTION"].trigger()
        self.assertEqual(
            {r["job_id"] for r in self.window.dashboard_records},
            {"job:2000000001", "job:2001443223"},
        )
        partial_index = next(
            i for i, r in enumerate(self.window.dashboard_records)
            if r["job_id"] == "job:2000000001"
        )
        self.window.dashboard_table.selectRow(partial_index)
        self.assertTrue(self.window.prepare_now_btn.isEnabled())
        sanofi_index = next(
            i for i, r in enumerate(self.window.dashboard_records)
            if r["job_id"] == "job:2001443223"
        )
        self.window.dashboard_table.selectRow(sanofi_index)
        self.assertTrue(self.window.detail_actions[10].isEnabled())
        self.records[0]["status"] = "SUBMITTED_MANUALLY"
        self.records[-2]["status"] = "SUBMITTED_MANUALLY"
        self.window._refresh_dashboard()
        self.assertEqual(len(self.window.dashboard_records), 0)

    def test_inactive_vacancy_hidden_and_restorable_in_filter(self):
        self.overrides["job:2000000001"] = {"decision": "INACTIVE"}
        self.window._refresh_dashboard()
        self.assertNotIn("job:2000000001", [r["job_id"] for r in self.window.dashboard_records])
        self.assertIn("INACTIVE", self.window.extra_filter_actions)
        self.window.extra_filter_actions["INACTIVE"].trigger()
        self.assertEqual([r["job_id"] for r in self.window.dashboard_records], ["job:2000000001"])
        self.window.dashboard_table.selectRow(0)
        self.assertFalse(self.window.prepare_now_btn.isEnabled())
        self.assertTrue(self.window.detail_actions[5].isEnabled())
        self.overrides.pop("job:2000000001")
        self.filter("All")
        self.assertIn("job:2000000001", [r["job_id"] for r in self.window.dashboard_records])

    def test_explicit_manual_jobs_handoff_link_is_offered_only_when_pending(self):
        record = self.records[0]
        handoff_url = "https://www.jobs.cz/externi-jof/2000000001/"
        record["status"] = "PRE_APPLY_CONFIRMATION_REQUIRED"
        record["handoff_url"] = handoff_url
        self.window._refresh_dashboard()
        self.window.dashboard_table.selectRow(0)
        manual_action = self.window.detail_actions[10]
        self.assertTrue(manual_action.isEnabled())
        with patch.object(desktop.QDesktopServices, "openUrl", return_value=True) as opened:
            manual_action.trigger()
            opened.assert_called_once()
            self.assertEqual(opened.call_args.args[0].toString(), handoff_url)

        record["status"] = "READY_TO_PREPARE"
        self.window._refresh_dashboard()
        self.assertFalse(manual_action.isEnabled())

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

    def test_filter_tabs_keep_selection_and_counts_in_search_scope(self):
        self.window.filter_buttons["APPLY"].click()
        self.assertEqual(len(self.window.dashboard_records), 1)
        self.window.filter_buttons["APPLY"].click()
        self.assertTrue(self.window.filter_buttons["APPLY"].isChecked())
        self.window.dashboard_search.setText("SQL")
        self.assertEqual(self.window.filter_buttons["All"].text(), "Все (1)")
        self.assertEqual(self.window.filter_buttons["SUBMITTED"].text(), "Отправлены (0)")
        self.window._show_all_vacancies()
        self.assertEqual(len(self.window.dashboard_records), 3)
        self.assertTrue(self.window.filter_buttons["All"].isChecked())

    def test_source_menu_filters_without_losing_extra_status_filters(self):
        self.window.source_filter_actions["startupjobs.cz"].trigger()
        self.assertEqual(len(self.window.dashboard_records), 1)
        self.assertEqual(self.window.dashboard_records[0]["source"], "startupjobs.cz")
        self.assertTrue(self.window.source_filter_actions["startupjobs.cz"].isChecked())
        self.window._show_all_vacancies()
        self.window.extra_filter_actions["INTERESTING"].trigger()
        self.assertEqual(self.window.dashboard_decision_filter.currentData(), "INTERESTING")
        self.assertEqual(len(self.window.dashboard_records), 0)

    def test_native_detail_uses_plain_text_and_explains_unknown_location(self):
        record = dict(self.records[0], title="<b>Literal title</b>",
                      description='<img src="file:///private">',
                      location_gate="location_unknown")
        self.window.dashboard_detail.set_record(record, "REVIEW")
        labels = [label for label in self.window.dashboard_detail.findChildren(QLabel) if not label.isHidden()]
        self.assertTrue(all(label.textFormat() == Qt.PlainText for label in labels if label.text()))
        self.assertIn("Место работы не подтверждено", [label.text() for label in labels])
        self.assertIn("<b>Literal title</b>", [label.text() for label in labels])
        self.window.dashboard_detail.description_toggle.click()
        descriptions = self.window.dashboard_detail.findChildren(QLabel, "Description")
        self.assertTrue(any(not label.isHidden() and '<img src="file:///private">' in label.text() for label in descriptions))

    def test_embedded_journal_opens_full_log(self):
        self.window._append_log("Example run event")
        self.assertEqual(self.window.latest_log.text(), "Example run event")
        self.window.journal_header.click()
        self.assertEqual(self.window.workspace_tabs.currentIndex(), 2)



class VacancyCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.vacancies = root / "vacancies.jsonl"
        self.history = root / "applications.csv"
        self.overrides = root / "job_overrides.json"
        for name, path in [
            ("VACANCIES_FILE", self.vacancies),
            ("HISTORY_FILE", self.history),
            ("OVERRIDES_FILE", self.overrides),
        ]:
            p = patch.object(desktop, name, path)
            p.start()
            self.addCleanup(p.stop)
        self.now = datetime(2026, 10, 8, 12)

    def write_records(self, *rows):
        with self.vacancies.open("w", encoding="utf-8") as out:
            for row in rows:
                out.write(json.dumps(row, ensure_ascii=False) + "\n")

    def row(self, jid, days, **extra):
        item = {
            "job_id": jid, "title": f"Vacancy {jid}", "source": "jobs.cz",
            "saved_at": (self.now - timedelta(days=days)).isoformat(timespec="seconds"),
            "status": "REVIEW_PENDING",
        }
        item.update(extra)
        return item

    def write_history(self, jid, status="SUBMITTED_MANUALLY"):
        with self.history.open("w", encoding="utf-8", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=["job_id", "title", "url", "status"])
            writer.writeheader()
            writer.writerow({"job_id": jid, "title": "Preserved application",
                             "url": "https://www.jobs.cz/rpd/2000000001/", "status": status})

    def test_old_vacancy_selection_protects_recent_submitted_favorite_and_queue(self):
        records = [
            self.row("job:1", 100),
            self.row("job:2", 5),
            self.row("job:3", 100),
            self.row("job:4", 100),
            self.row("job:5", 100),
            {"job_id": "job:6", "title": "undated"},
        ]
        overrides = {"job:3": {"decision": "INTERESTING"},
                     "job:4": {"decision": "MANUAL_APPLY"}}
        ids = desktop.old_vacancy_ids(
            records, 60, self.now, overrides, {"job:5"}
        )
        self.assertEqual(ids, {"job:1"})
        self.assertEqual(desktop.old_vacancy_ids(records, 180, self.now, overrides, {"job:5"}), set())

    def test_purge_removes_all_snapshot_rows_backs_up_and_preserves_history(self):
        stale = self.row("job:2000000001", 100)
        fresh = self.row("job:2000000002", 1)
        self.write_records(stale, stale, fresh)
        self.write_history("job:2000000001", status="REVIEW_PENDING")
        ids = desktop.old_vacancy_ids(
            desktop.load_vacancy_records(), 90, self.now, {}, set()
        )
        self.assertEqual(ids, {"job:2000000001"})
        hidden, removed_rows, backup = desktop.purge_vacancy_records(ids)
        self.assertEqual((hidden, removed_rows), (1, 2))
        self.assertTrue(backup.is_file())
        self.assertEqual(len(backup.read_text(encoding="utf-8").splitlines()), 3)
        self.assertEqual(
            [row["job_id"] for row in desktop.load_vacancy_records()],
            ["job:2000000002"],
        )
        self.assertIn("2000000001", self.history.read_text(encoding="utf-8"))
        self.assertEqual(
            desktop.load_job_overrides()["job:2000000001"]["decision"],
            "INACTIVE",
        )

    def test_submitted_favorite_and_queue_cannot_be_purged_even_directly(self):
        self.write_records(
            self.row("job:1", 100), self.row("job:2", 100),
            self.row("job:3", 100),
        )
        self.overrides.write_text(json.dumps({
            "job:2": {"decision": "INTERESTING"},
            "job:3": {"decision": "MANUAL_APPLY"},
        }))
        self.write_history("job:1")
        original = self.vacancies.read_text(encoding="utf-8")
        for jid in ["job:1", "job:2", "job:3"]:
            with self.subTest(jid=jid):
                with self.assertRaises(ValueError):
                    desktop.purge_vacancy_records({jid})
        self.assertEqual(self.vacancies.read_text(encoding="utf-8"), original)

    def test_unparseable_lines_are_retained(self):
        self.write_records(self.row("job:1", 100))
        with self.vacancies.open("a", encoding="utf-8") as f:
            f.write("bad json line\n")
        hidden, removed, _ = desktop.purge_vacancy_records({"job:1"})
        self.assertEqual((hidden, removed), (1, 1))
        self.assertEqual(self.vacancies.read_text(encoding="utf-8"), "bad json line\n")
