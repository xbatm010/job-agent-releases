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
    async def test_pre_enrichment_prioritizes_entry_roles_and_excludes_senior(self):
        def item(title, jid, source="jobs.cz"):
            return {
                "title": title, "job_id": str(jid), "source": source,
                "url": f"https://www.jobs.cz/rpd/{jid}/",
                "location": "Praha",
            }

        jobs = [item("Java Engineer", i, "startupjobs.cz") for i in range(30)]
        jobs += [item("Senior Data Analyst", 301), item("Business Analyst", 302)]
        jobs += [item("AI & Automation Student Support (Part-time)", 303, "prace.cz")]
        jobs += [item("Junior Data Analyst", 304)]
        result = main.select_discovery_candidates(jobs, set(), set(), 3)
        self.assertEqual(
            [j["job_id"] for j in result],
            ["304", "303", "302"],
        )
        self.assertNotIn("301", [j["job_id"] for j in result])
        self.assertEqual(
            [j["job_id"] for j in main.select_discovery_candidates(
                jobs, {"job:304"}, {"job:303"}, 2
            )],
            ["302", "0"],
        )

    async def test_priority_balances_sources_within_same_relevance_tier(self):
        jobs = [
            {"title": "Junior Data Analyst", "job_id": str(i),
             "source": "jobs.cz", "location": "Praha"}
            for i in range(10)
        ]
        jobs += [
            {"title": "Junior Data Analyst", "job_id": str(100 + i),
             "source": "prace.cz", "location": "Praha"}
            for i in range(2)
        ]
        result = main.select_discovery_candidates(jobs, set(), set(), 4)
        self.assertEqual([j["source"] for j in result], [
            "jobs.cz", "prace.cz", "jobs.cz", "prace.cz",
        ])

    async def test_full_detail_scores_determine_shortlist_not_discovery_order(self):
        initial_order = [
            {"job_id": str(i), "decision": "SKIP", "score": 90 - i}
            for i in range(4)
        ]
        initial_order += [
            {"job_id": "review", "decision": "REVIEW", "score": 65},
            {"job_id": "apply", "decision": "APPLY", "score": 74},
        ]
        selected = main.select_review_shortlist(initial_order, 2)
        self.assertEqual([j["job_id"] for j in selected], ["apply", "review"])
        self.assertEqual(len(initial_order), 6)
        self.assertEqual(main.select_review_shortlist(initial_order, 0), [])

    async def test_run_can_select_high_scoring_job_after_old_review_cutoff(self):
        jobs = [vacancy("Data Analyst", job_id=str(1001 + i)) for i in range(3)]
        for job in jobs:
            job["card_text"] = ""
            job["location"] = "Praha"

        def scored(job):
            best = job["job_id"] == "1003"
            return {
                "score": 89 if best else 15,
                "decision": "APPLY" if best else "SKIP",
                "role_class": "target",
                "reasons": [],
                "evidence_verified": True,
            }

        prev = Path.cwd()
        try:
            os.chdir(self.state.name)
            with patch.multiple(main, SEARCH_ONLY=True, MAX_JOBS_TO_REVIEW=1), \
                    patch.object(main, "discover_all", AsyncMock(return_value=jobs)), \
                    patch.object(main, "enrich_job", side_effect=lambda j, _: j), \
                    patch.object(main, "browser_recover_weak_evidence",
                                 AsyncMock(side_effect=lambda x: x)), \
                    patch.object(main, "score_job", side_effect=scored), \
                    patch.object(main, "location_gate",
                                 return_value=(True, "prague_area", "Praha")), \
                    contextlib.redirect_stdout(io.StringIO()):
                await main.main()
            ranked = json.loads(Path("jobs.json").read_text(encoding="utf-8"))
        finally:
            os.chdir(prev)

        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["job_id"], "1003")
        self.assertEqual(ranked[0]["decision"], "APPLY")

    async def test_analytics_powerbi_internship_is_not_discarded_as_other(self):
        title = "Analytics and PowerBI Development Intern"
        self.assertEqual(main.role_class(title), "expanded")
        job = vacancy(title)
        self.assertGreater(main.pre_enrichment_relevance_tier(job), 1)
        result = main.score_job(job)
        self.assertEqual(result["role_class"] if "role_class" in result else main.role_class(title), "expanded")
        self.assertGreater(result["score"], 42)
        self.assertNotEqual(result["decision"], "SKIP")
        self.assertEqual(main.role_class("Junior Esims Trader"), "other")
        self.assertEqual(main.role_class("Senior PowerBI Development Intern"), "excluded")

    async def test_version_banner_uses_packaged_metadata(self):
        root = Path(self.state.name)
        path = root / "version.json"
        path.write_text(json.dumps({"version": "2.9.6", "channel": "beta"}))
        with patch.object(main, "__file__", str(root / "main.py")):
            self.assertEqual(main.current_agent_version(), "2.9.6")
            path.write_text('bad json')
            with patch.dict(os.environ, {"JOB_AGENT_VERSION": "fallback-version"}):
                self.assertEqual(main.current_agent_version(), "fallback-version")

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
        encoded = fake_page("https://www.jobs.cz/odpov%C4%9B%C4%8F-odesl%C3%A1na/2001468066/")
        self.assertEqual(
            await main.manual_submit_success_signal(encoded, original),
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

