import contextlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from test_scoring import ScoringDefaults, main, vacancy


class RuntimeImprovements(ScoringDefaults, unittest.IsolatedAsyncioTestCase):
    async def test_search_only_saves_apply_without_cv_or_form_preparation(self):
        job = vacancy()
        prepare = AsyncMock()
        previous = Path.cwd()
        try:
            os.chdir(self.state.name)
            with patch.object(main, "SEARCH_ONLY", True), \
                    patch.object(main, "CV_PATH", "/missing/cv.pdf"), \
                    patch.object(main, "discover_all", AsyncMock(return_value=[job])), \
                    patch.object(main, "enrich_job", side_effect=lambda j, _: j), \
                    patch.object(main, "browser_recover_weak_evidence", AsyncMock(side_effect=lambda jobs: jobs)), \
                    patch.object(main, "prepare_application", prepare), \
                    contextlib.redirect_stdout(io.StringIO()):
                await main.main()
        finally:
            os.chdir(previous)
        prepare.assert_not_awaited()
        snapshot = json.loads(main.VACANCIES_FILE.read_text().splitlines()[-1])
        self.assertEqual(snapshot["decision"], "APPLY")
        self.assertEqual(snapshot["status"], "READY_TO_PREPARE")
        self.assertEqual(main.load_processed(), set())

    async def test_empty_startup_search_records_diagnostics_and_uses_fallback(self):
        response = SimpleNamespace(status_code=200, text="<html><body>No cards</body></html>", url="https://www.startupjobs.cz/nabidky", raise_for_status=lambda: None)
        session = SimpleNamespace(get=lambda *args, **kwargs: response)
        fallback = AsyncMock(return_value=[])
        log = io.StringIO()
        with patch.multiple(main, SOURCE_JOBS_CZ=False, SOURCE_PRACE_CZ=False, SOURCE_STARTUPJOBS_CZ=True), \
                patch.object(main, "browser_discovery_fallback", fallback), \
                contextlib.redirect_stdout(log):
            result = await main.discover_all(session)
        self.assertEqual(result, [])
        fallback.assert_awaited_once()
        status = json.loads((main.STATE_DIR / "discovery_status.json").read_text())
        self.assertEqual(status["sources"]["startupjobs.cz"]["status"], "empty")
        self.assertEqual(status["sources"]["jobs.cz"]["status"], "disabled")
        self.assertIn("HTTP 200; parsed=0", status["sources"]["startupjobs.cz"]["details"][0])
        self.assertIn("no parsed vacancies", log.getvalue())

    async def test_startupjobs_failed_listing_is_not_reported_as_empty(self):
        html = "<html><body><h1>Data analytik</h1><p>ss... něco se pokazilo.</p><button>Načíst znovu</button></body></html>"
        response = SimpleNamespace(status_code=200, text=html, url="https://www.startupjobs.cz/nabidky/data-analytik", raise_for_status=lambda: None)
        session = SimpleNamespace(get=lambda *args, **kwargs: response)
        with patch.multiple(main, SOURCE_JOBS_CZ=False, SOURCE_PRACE_CZ=False, SOURCE_STARTUPJOBS_CZ=True), \
                patch.object(main, "browser_discovery_fallback", AsyncMock(return_value=[])), \
                contextlib.redirect_stdout(io.StringIO()):
            await main.discover_all(session)
        status = json.loads((main.STATE_DIR / "discovery_status.json").read_text())
        self.assertEqual(status["sources"]["startupjobs.cz"]["status"], "error")
        self.assertTrue(any("incomplete" in d for d in status["sources"]["startupjobs.cz"]["details"]))

    async def test_submission_confirmation_requires_success_evidence(self):
        def fake_page(url, message="Application details"):
            return SimpleNamespace(
                url=url,
                locator=lambda selector: SimpleNamespace(
                    inner_text=AsyncMock(return_value=message)
                ),
            )

        original = "https://www.jobs.cz/odpoved/2001468066/"
        redirect = fake_page("https://www.jobs.cz/prace/praha/")
        self.assertEqual(
            await main.manual_submit_success_signal(redirect, original), (False, "")
        )
        success = fake_page("https://www.jobs.cz/odpoved-odeslana/2001468066/")
        self.assertEqual(
            await main.manual_submit_success_signal(success, original),
            (True, "post_submit_redirect"),
        )
        confirmed_text = fake_page(original, "Děkujeme za odpověď")
        self.assertEqual(
            await main.manual_submit_success_signal(confirmed_text, original),
            (True, "confirmation_text"),
        )

    async def test_missing_cover_letter_warns_before_manual_submit(self):
        page = SimpleNamespace(
            url="https://www.jobs.cz/odpoved/2001468066/",
            wait_for_timeout=AsyncMock(),
        )
        details = {"cover_letter": False, "cover_letter_source": "field_not_found"}
        output = io.StringIO()
        with patch.multiple(
            main, MANUAL_SUBMIT_HOLD=True, MANUAL_SUBMIT_WAIT_SECONDS=1,
            AUTO_CZECH_COVER_LETTER=True,
        ), patch.object(
            main, "manual_submit_success_signal",
            AsyncMock(return_value=(True, "post_submit_redirect")),
        ), contextlib.redirect_stdout(output):
            status, reason, url, form = await main.hold_for_manual_final_submit(
                page, ("READY_FOR_MANUAL_SUBMIT", "prepared", page.url, details)
            )
        self.assertEqual(status, "SUBMITTED_MANUALLY")
        self.assertIn("No cover-letter field detected", output.getvalue())
        self.assertIn("manual copy", output.getvalue())

    async def test_source_failure_is_not_reported_as_successful_empty_search(self):
        with patch.multiple(main, DISCOVERY_NOTES={}, DISCOVERY_FAILURES={}, SOURCE_JOBS_CZ=True):
            main.discovery_failure("jobs.cz", "Timeout")
            main.write_discovery_status({"jobs.cz": []})
            status = json.loads((main.STATE_DIR / "discovery_status.json").read_text())
            self.assertEqual(status["sources"]["jobs.cz"]["status"], "error")
            main.write_discovery_status({"jobs.cz": [vacancy()]})
            status = json.loads((main.STATE_DIR / "discovery_status.json").read_text())
            self.assertEqual(status["sources"]["jobs.cz"]["status"], "partial")

    async def test_city_cannot_become_employer_but_city_in_company_name_is_allowed(self):
        for city in ("Prague", "Praha", "Brno", "Remote", "Czech Republic"):
            with self.subTest(city=city):
                self.assertFalse(main.valid_company(city, "meta"))
        self.assertTrue(main.valid_company("Prague Finance s.r.o.", "meta"))
        self.assertTrue(main.valid_company("Provident Financial s.r.o.", "meta"))

    async def test_entry_expanded_role_gets_browser_slot_before_generic_target(self):
        entry = vacancy("AI & Automation Student Support")
        entry["source"] = "prace.cz"
        regular = vacancy("Business Analyst")
        self.assertGreater(main.browser_evidence_priority(entry), main.browser_evidence_priority(regular))

