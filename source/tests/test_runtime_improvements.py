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

    async def test_blocked_jobs_handoff_does_not_block_other_vacancies(self):
        jobs = [
            vacancy("Junior Data Analyst", job_id="2001443223"),
            vacancy("Junior Data Analyst", job_id="2001443224"),
        ]
        cv = Path(self.state.name) / "fixture-cv.txt"
        cv.write_text("dummy cv")
        handoff_url = "https://www.jobs.cz/externi-jof/2001443223/"
        prepare = AsyncMock(side_effect=[
            ("PRE_APPLY_CONFIRMATION_REQUIRED", "manual handoff", handoff_url,
             {"stage": "jobs_handoff"}),
            ("SUBMITTED_MANUALLY", "confirmed by user", "https://www.jobs.cz/odpoved-odeslana/2001443224/",
             {}),
        ])
        output = io.StringIO()
        previous = Path.cwd()
        try:
            os.chdir(self.state.name)
            with patch.multiple(main, SEARCH_ONLY=False, CV_PATH=str(cv), MAX_APPLICATIONS_PER_RUN=3), \
                    patch.object(main, "discover_all", AsyncMock(return_value=jobs)), \
                    patch.object(main, "enrich_job", side_effect=lambda j, _: j), \
                    patch.object(main, "browser_recover_weak_evidence", AsyncMock(side_effect=lambda j: j)), \
                    patch.object(main, "prepare_application", prepare), \
                    contextlib.redirect_stdout(output):
                await main.main()
        finally:
            os.chdir(previous)
        self.assertEqual(prepare.await_count, 2)
        records = [json.loads(x) for x in main.VACANCIES_FILE.read_text(encoding="utf-8").splitlines()]
        by_id = {r["job_id"]: r for r in records}
        self.assertEqual(by_id["job:2001443223"]["status"], "PRE_APPLY_CONFIRMATION_REQUIRED")
        self.assertEqual(by_id["job:2001443223"]["handoff_url"], handoff_url)
        self.assertEqual(by_id["job:2001443224"]["status"], "SUBMITTED_MANUALLY")
        self.assertEqual(main.load_processed(), {"job:2001443224"})
        self.assertIn("Pending manual Jobs.cz handoffs: 1", output.getvalue())
        self.assertIn("Confirmed submissions: 1", output.getvalue())

    async def test_handoff_does_not_relax_other_user_intervention_gates(self):
        self.assertTrue(main.should_continue_after_application("PRE_APPLY_CONFIRMATION_REQUIRED"))
        for status in (
            "LOGIN_REQUIRED", "WORKDAY_LOGIN_REQUIRED",
            "PWC_CONSENT_CHOICES_REQUIRED", "READY_FOR_MANUAL_SUBMIT",
        ):
            with self.subTest(status=status):
                self.assertFalse(main.should_continue_after_application(status))
        self.assertTrue(main.should_continue_after_application("SUBMITTED_MANUALLY"))

    async def test_search_card_recovers_cez_employer_from_correlated_logo(self):
        html = """
        <article>
          <h2><a href="/rpd/2001283488/">Specialista/ka datové kvality (Data Quality)</a></h2>
          <img src="/images/preview.svg" alt="Skupina ČEZ">
          <ul><li>Skupina ČEZ</li><li>Praha – Michle</li></ul>
        </article>
        """
        jobs = main.parse_search(html, "data quality")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["job_id"], "2001283488")
        self.assertEqual(jobs[0]["company"], "Skupina ČEZ")
        self.assertEqual(jobs[0]["company_source"], "search_card")

    async def test_navigation_domů_is_not_an_employer_but_real_brands_survive(self):
        for label in [
            "Domů", "Domu", "Home", "Úvod", "Hlavní stránka",
            "Zpět", "Menu", "Přihlásit se", "Volné pozice",
        ]:
            with self.subTest(label=label):
                self.assertFalse(main.valid_company(label, "search_card"))
                self.assertFalse(main.valid_company(label, "meta"))
                self.assertEqual(main.normalized_employer_logo_label(label), "")
        for label in ["Home Credit a.s.", "Skupina ČEZ", "Seznam.cz, a.s."]:
            with self.subTest(company=label):
                self.assertTrue(main.valid_company(label, "search_card"))
                self.assertEqual(main.normalized_employer_logo_label(label), label)

    async def test_navigation_logo_skipped_even_when_named_company(self):
        soup = main.BeautifulSoup("""
        <article>
          <h2><a href="/rpd/2001457607/">Master Data Specialist</a></h2>
          <header><a class="company-logo" href="/">
            <img src="/assets/company-logo.svg" alt="Domů"></a></header>
          <nav><img src="/logos/header.svg" alt="Navigation"></nav>
          <div class="company-logo">
            <img src="/assets/cez-logo.svg" alt="Skupina ČEZ"></div>
        </article>
        """, "html.parser")
        self.assertEqual(
            main.extract_company_from_search_card(
                soup.article, "Master Data Specialist",
            ),
            "Skupina ČEZ",
        )
        only_nav = main.BeautifulSoup("""
        <article>
          <h2><a href="/rpd/2001457607/">Master Data Specialist</a></h2>
          <div class="company-logo">
            <img src="/assets/site-logo.svg" alt="Domů"></div>
        </article>
        """, "html.parser")
        self.assertEqual(main.extract_company_from_search_card(
            only_nav.article, "Master Data Specialist",
        ), "")
        detail = main.BeautifulSoup(
            '<div class="company-logo"><img src="/site/logo.svg" alt="Domů"></div>',
            "html.parser",
        )
        self.assertEqual(main.extract_company(detail), "")

    async def test_browser_navigation_logo_cannot_be_employer(self):
        class Locator:
            first = None

            def __init__(self, selector):
                self.selector = selector
                self.first = self

            async def count(self):
                return 1 if "img[alt]," in self.selector else 0

            def nth(self, index):
                return self

            async def is_visible(self):
                return True

            async def get_attribute(self, name):
                return "Domů" if name == "alt" else None

            async def inner_text(self):
                return ""

        page = SimpleNamespace(
            url="https://www.jobs.cz/rpd/2001457607/",
            evaluate=AsyncMock(return_value=""),
            locator=lambda selector: Locator(selector),
            title=AsyncMock(return_value=""),
        )
        with patch.object(main, "page_contexts", AsyncMock(return_value=[page])):
            company, source = await main.extract_company_from_page(page)
        self.assertEqual((company, source), ("", "not_detected"))

    async def test_employer_logo_rejects_unrelated_images_and_vacancy_title(self):
        bs = main.BeautifulSoup
        title = "Specialista/ka datové kvality (Data Quality)"
        decorative = bs(f"""
            <article><img src="/images/office.jpg" alt="Home Office">
            <img src="/assets/logo.png" alt="{title}"></article>
        """, "html.parser").article
        self.assertEqual(main.employer_from_logo(decorative, title), "")
        explicit = bs(
            '<article><img src="/logos/cez.svg" alt="Logo společnosti Skupina ČEZ">'
            '</article>', "html.parser",
        ).article
        self.assertEqual(main.employer_from_logo(explicit, title), "Skupina ČEZ")
        self.assertEqual(main.normalized_employer_logo_label("logo firmy"), "")
        self.assertEqual(main.normalized_employer_logo_label(title, title), "")

    async def test_employer_from_details_company_logo_but_not_generic_alt(self):
        bs = main.BeautifulSoup
        page = bs(
            '<div class="company-logo">'
            '<img src="/graphics/cez.svg" alt="Skupina ČEZ"></div>',
            "html.parser",
        )
        self.assertEqual(main.extract_company(page), "Skupina ČEZ")
        empty = bs(
            '<div class="company-logo"><img src="/icons/generic.svg" alt="Logo firmy">'
            '</div>', "html.parser",
        )
        self.assertEqual(main.extract_company(empty), "")

    async def test_browser_logo_fallback_is_read_only_and_employer_scoped(self):
        class Locator:
            def __init__(self, selector):
                self.selector = selector
                self.first = self

            async def count(self):
                return 1 if 'img[alt],' in self.selector else 0

            def nth(self, index):
                self._nth = index
                return self

            async def is_visible(self):
                return True

            async def get_attribute(self, name):
                return "Logo společnosti Skupina ČEZ" if name == "alt" else None

            async def inner_text(self):
                return ""

        page = SimpleNamespace(
            url="https://www.jobs.cz/rpd/2001283488/",
            evaluate=AsyncMock(return_value=""),
            locator=lambda sel: Locator(sel),
            title=AsyncMock(return_value=""),
        )
        with patch.object(main, "page_contexts", AsyncMock(return_value=[page])):
            company, source = await main.extract_company_from_page(page)
        self.assertEqual(company, "Skupina ČEZ")
        self.assertEqual(source, "browser_employer_logo")

    async def test_employer_link_company_prefix_is_removed_only_for_legal_names(self):
        self.assertEqual(
            main.clean_browser_employer_label("Company EP Commodities, a.s."),
            "EP Commodities, a.s.",
        )
        self.assertEqual(
            main.clean_browser_employer_label("Company Example s.r.o."),
            "Example s.r.o.",
        )
        self.assertEqual(
            main.clean_browser_employer_label("Company of Heroes"),
            "Company of Heroes",
        )
        self.assertEqual(
            main.clean_browser_employer_label("Company Software"),
            "Company Software",
        )

    async def test_role_title_fragment_is_not_company(self):
        self.assertFalse(main.valid_company("analytička", "meta"))
        self.assertFalse(main.valid_company("Business Analyst", "meta"))
        self.assertTrue(main.valid_company("Komerční banka", "meta"))
        self.assertTrue(main.valid_company("Prague Finance s.r.o.", "meta"))

    async def test_pending_handoff_is_excluded_from_future_auto_discovery(self):
        pending = vacancy("Analytics and PowerBI Development Intern", job_id="2001443223")
        fresh = vacancy("Junior Data Analyst", job_id="2001443999")
        pending["source"] = "jobs.cz"
        main.save_status(
            pending, "PRE_APPLY_CONFIRMATION_REQUIRED", 79,
            "Manual continuation is required",
        )
        self.assertEqual(main.load_pending_manual_handoffs(), {"job:2001443223"})
        called = []
        def enrich(job, _):
            called.append(job["job_id"])
            return job
        cwd = Path.cwd()
        try:
            os.chdir(self.state.name)
            with patch.object(main, "SEARCH_ONLY", True), \
                    patch.object(main, "discover_all", AsyncMock(return_value=[pending, fresh])), \
                    patch.object(main, "enrich_job", side_effect=enrich), \
                    patch.object(main, "browser_recover_weak_evidence",
                                 AsyncMock(side_effect=lambda jobs: jobs)), \
                    contextlib.redirect_stdout(io.StringIO()):
                await main.main()
        finally:
            os.chdir(cwd)
        self.assertEqual(called, ["2001443999"])
        records = [json.loads(line) for line in main.VACANCIES_FILE.read_text().splitlines()]
        statuses = [r["status"] for r in records if r["job_id"] == "job:2001443223"]
        self.assertEqual(statuses, ["PRE_APPLY_CONFIRMATION_REQUIRED"])
        self.assertEqual(main.load_pending_manual_handoffs(), {"job:2001443223"})

    async def test_pending_manual_handoff_cleared_only_by_later_status(self):
        job = vacancy("Junior Data Analyst", job_id="2001443223")
        main.save_status(job, "PRE_APPLY_CONFIRMATION_REQUIRED", 79, "human follow-up")
        self.assertIn("job:2001443223", main.load_pending_manual_handoffs())
        main.save_status(job, "SUBMITTED_MANUALLY", 79, "confirmed")
        self.assertNotIn("job:2001443223", main.load_pending_manual_handoffs())
        self.assertIn("job:2001443223", main.load_processed())

    async def test_no_apply_suggestions_only_include_safe_manual_review_options(self):
        def review(jid, score, **fields):
            return {
                "job_id": jid, "title": f"Analyst {jid}",
                "source": "jobs.cz", "role_class": "target",
                "score": score, "decision": "REVIEW", "candidate_fit": 6,
                "evidence_quality": "strong", "location_gate": "prague_area",
                "target_apply_blockers": ["candidate_fit=6 < 10"],
                "url": f"https://www.jobs.cz/rpd/{jid}/",
                **fields,
            }
        candidates = [
            review("s1", 90, source="startupjobs.cz"),
            review("unsafe", 85, location_gate="location_unknown"),
            review("weak", 82, evidence_quality="weak"),
            review("hard", 81, hard_experience=True),
            review("a", 74, role_class="expanded", expanded_apply_blockers=["candidate_fit=8 < 12"]),
            review("b", 70),
            review("c", 69),
            review("d", 67),
            review("submitted", 100, decision="SKIP"),
        ]
        suggested = main.safe_manual_review_candidates(candidates)
        self.assertEqual([j["job_id"] for j in suggested], ["a", "b", "c"])
        self.assertEqual(main.safe_manual_review_candidates(candidates, 0), [])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main.print_manual_review_suggestions(candidates)
        self.assertIn("REVIEW candidates: 8", output.getvalue())
        self.assertIn("candidate_fit=8 < 12", output.getvalue())
        self.assertIn("Dashboard", output.getvalue())
        self.assertNotIn("Analyst unsafe", output.getvalue())

    async def test_no_apply_run_saves_review_and_never_opens_application_form(self):
        job = vacancy("Data Analyst", job_id="2001475720")
        job["description"] = "SQL Excel and reporting. " * 50
        cv = Path(self.state.name) / "fixture-cv.txt"
        cv.write_text("CV")
        attempted = AsyncMock()
        output = io.StringIO()
        previous = Path.cwd()
        try:
            os.chdir(self.state.name)
            with patch.multiple(main, SEARCH_ONLY=False, CV_PATH=str(cv)), \
                    patch.object(main, "discover_all", AsyncMock(return_value=[job])), \
                    patch.object(main, "enrich_job", side_effect=lambda j, _: j), \
                    patch.object(main, "browser_recover_weak_evidence",
                                 AsyncMock(side_effect=lambda x: x)), \
                    patch.object(main, "score_job", return_value={
                        "score": 74, "decision": "REVIEW", "role_class": "target",
                        "candidate_fit": 6, "evidence_quality": "strong",
                        "target_apply_blockers": ["candidate_fit=6 < 10"],
                        "reasons": ["insufficient skill readiness"],
                    }), \
                    patch.object(main, "location_gate",
                                 return_value=(True, "prague_area", "Praha")), \
                    patch.object(main, "prepare_application", attempted), \
                    contextlib.redirect_stdout(output):
                await main.main()
        finally:
            os.chdir(previous)
        attempted.assert_not_awaited()
        self.assertIn("No new vacancy qualifies for automatic APPLY", output.getvalue())
        self.assertIn("safe manual-review suggestions: 1", output.getvalue())
        self.assertIn("Data Analyst", output.getvalue())
        records = [
            json.loads(line)
            for line in main.VACANCIES_FILE.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(records[-1]["decision"], "REVIEW")
        self.assertEqual(records[-1]["status"], "REVIEW_PENDING")

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

    async def test_first_name_selector_does_not_match_czech_surname(self):
        from bs4 import BeautifulSoup
        page = BeautifulSoup(
            '<input name="prijmeno" value="Surname">'
            '<input name="jmeno" value="">'
            '<input name="příjmení" value="Surname">'
            '<input name="jméno" value="">',
            "html.parser",
        )
        matches = [
            inp for selector in main.FIRST_NAME_SELECTORS
            for inp in page.select(selector)
        ]
        self.assertEqual({x["name"] for x in matches}, {"jmeno", "jméno"})
        self.assertNotIn("prijmeno", {x["name"] for x in matches})
        self.assertNotIn("příjmení", {x["name"] for x in matches})

    async def test_manual_name_read_only_validation_requires_unique_correct_field(self):
        class Input:
            def __init__(self, value, metadata):
                self.value = value
                self.metadata = metadata

            async def is_visible(self):
                return True

            async def is_disabled(self):
                return False

            async def get_attribute(self, key):
                return "text" if key == "type" else None

            async def input_value(self):
                return self.value

        inputs = [
            Input("TestFirst", "surname"),
            Input("", "unknown field"),
            Input("TestFirst", "opaque text field"),
        ]
        loc = SimpleNamespace(count=AsyncMock(return_value=3),
                              nth=lambda i: inputs[i])
        frame = SimpleNamespace(locator=lambda _: loc)
        with patch.dict(main.CANDIDATE, {"first_name": "TestFirst"}), \
                patch.object(main, "page_contexts", AsyncMock(return_value=[frame])), \
                patch.object(main, "input_metadata",
                             AsyncMock(side_effect=lambda el: el.metadata)):
            self.assertTrue(await main.manually_verified_first_name(object()))
            inputs[1].value = "TestFirst"
            self.assertFalse(await main.manually_verified_first_name(object()))
            inputs[1].value = ""
            inputs[2].value = ""
            self.assertFalse(await main.manually_verified_first_name(object()))

    async def test_manual_first_name_completion_is_bounded_and_never_submits(self):
        page = SimpleNamespace(wait_for_timeout=AsyncMock())
        form = {"first_name": False, "submit": True, "cv": True}
        with patch.multiple(main, MANUAL_SUBMIT_HOLD=True, MANUAL_NAME_WAIT_SECONDS=2), \
                patch.object(main, "manually_verified_first_name",
                             AsyncMock(side_effect=[False, True])) as verified, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(await main.manual_first_name_fallback(page, form))
        self.assertEqual(verified.await_count, 2)
        page.wait_for_timeout.assert_awaited_once_with(1000)
        self.assertTrue(form["first_name"])
        self.assertEqual(form["first_name_source"], "manual_unique_visible_input")
        self.assertFalse(hasattr(page, "click"))

    async def test_manual_name_fallback_times_out_and_respects_disabled_hold(self):
        page = SimpleNamespace(wait_for_timeout=AsyncMock())
        with patch.multiple(main, MANUAL_SUBMIT_HOLD=False, MANUAL_NAME_WAIT_SECONDS=2), \
                patch.object(main, "manually_verified_first_name", AsyncMock()) as verify:
            self.assertFalse(await main.manual_first_name_fallback(page, {}))
            verify.assert_not_awaited()
        with patch.multiple(main, MANUAL_SUBMIT_HOLD=True, MANUAL_NAME_WAIT_SECONDS=2), \
                patch.object(main, "manually_verified_first_name",
                             AsyncMock(return_value=False)) as verify, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(await main.manual_first_name_fallback(page, {}))
            self.assertEqual(verify.await_count, 2)

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

