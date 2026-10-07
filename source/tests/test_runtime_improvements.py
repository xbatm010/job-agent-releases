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

