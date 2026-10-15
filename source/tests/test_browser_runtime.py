"""Regression tests for outdated Playwright browsers in the packaged Mac app."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import browser_runtime
from browser_runtime import BrowserUnavailable, launch_chromium

with tempfile.TemporaryDirectory() as folder:
    with patch.dict(os.environ, {"STATE_DIR": folder}):
        import main


class BrowserAvailabilityTests(unittest.TestCase):
    def test_stale_revision_folder_does_not_count_as_available(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "chromium_headless_shell-1200").mkdir()
            (root / "chromium-1200").mkdir()
            with patch.object(browser_runtime, "browser_cache_dir", return_value=root), \
                 patch.object(browser_runtime, "expected_chromium_revisions",
                              return_value={"chromium-headless-shell": "1248", "chromium": "1248"}), \
                 patch.object(browser_runtime, "installed_chrome_paths", return_value=[]):
                self.assertFalse(browser_runtime.managed_chromium_available())
                self.assertFalse(browser_runtime.browser_available())

    def test_matching_revision_needs_real_executable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shell = root / "chromium_headless_shell-1248" / "chrome-headless-shell-mac-arm64"
            shell.mkdir(parents=True)
            with patch.object(browser_runtime, "browser_cache_dir", return_value=root), \
                 patch.object(browser_runtime, "expected_chromium_revisions",
                              return_value={"chromium-headless-shell": "1248", "chromium": "1248"}):
                self.assertFalse(browser_runtime.managed_chromium_available())
                (shell / "chrome-headless-shell").write_text("binary")
                self.assertTrue(browser_runtime.managed_chromium_available())

    def test_system_chrome_counts_as_available(self):
        with patch.object(browser_runtime, "managed_chromium_available", return_value=False), \
             patch.object(browser_runtime, "installed_chrome_paths",
                          return_value=[Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]):
            self.assertTrue(browser_runtime.browser_available())

    def test_manifest_uses_matching_playwright_revision(self):
        revisions = browser_runtime.expected_chromium_revisions()
        self.assertIn("chromium", revisions)
        self.assertIn("chromium-headless-shell", revisions)
        self.assertTrue(revisions["chromium"].isdigit())


class BrowserLaunchTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_managed_chromium_still_preferred(self):
        browser = object()
        chrom = MagicMock()
        chrom.launch = AsyncMock(return_value=browser)
        with patch.object(browser_runtime, "installed_chrome_paths", return_value=[]):
            self.assertIs(await launch_chromium(chrom), browser)
        chrom.launch.assert_awaited_once_with(headless=True)

    async def test_missing_headless_shell_uses_full_chromium(self):
        browser = object()
        chrom = MagicMock()
        chrom.launch = AsyncMock(side_effect=[
            RuntimeError("Executable doesn't exist at /missing/chrome-headless-shell"),
            browser,
        ])
        with patch.object(browser_runtime, "installed_chrome_paths", return_value=[]):
            self.assertIs(await launch_chromium(chrom), browser)
        self.assertEqual(chrom.launch.await_args_list[1].kwargs["channel"], "chromium")

    async def test_missing_managed_chromium_uses_installed_chrome(self):
        browser = object()
        chrom = MagicMock()
        chrom.launch = AsyncMock(side_effect=[
            RuntimeError("Executable doesn't exist"),
            RuntimeError("Executable doesn't exist"),
            browser,
        ])
        path = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        with patch.object(browser_runtime, "installed_chrome_paths", return_value=[path]):
            self.assertIs(await launch_chromium(chrom), browser)
        self.assertEqual(chrom.launch.await_args_list[2].kwargs["executable_path"], str(path))

    async def test_missing_all_browsers_raises_friendly_error(self):
        chrom = MagicMock()
        chrom.launch = AsyncMock(side_effect=RuntimeError("Executable doesn't exist"))
        with patch.object(browser_runtime, "installed_chrome_paths", return_value=[]):
            with self.assertRaises(BrowserUnavailable) as cm:
                await launch_chromium(chrom)
        self.assertIn("Search-only can continue via HTTP", str(cm.exception))
        self.assertEqual(chrom.launch.await_count, 2)

    async def test_non_missing_browser_failure_is_never_hidden(self):
        chrom = MagicMock()
        chrom.launch = AsyncMock(side_effect=RuntimeError("Browser crashed unexpectedly"))
        with patch.object(browser_runtime, "installed_chrome_paths", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "crashed"):
                await launch_chromium(chrom)
        self.assertEqual(chrom.launch.await_count, 1)

    async def test_persistent_application_profile_preserved_with_fallback(self):
        context = object()
        chrom = MagicMock()
        chrom.launch_persistent_context = AsyncMock(side_effect=[
            RuntimeError("Executable doesn't exist"), context,
        ])
        with patch.object(browser_runtime, "installed_chrome_paths", return_value=[]):
            actual = await launch_chromium(
                chrom, headless=False, profile_dir="/tmp/test-job-agent-profile",
                viewport={"width": 1440, "height": 1000},
            )
        self.assertIs(actual, context)
        second = chrom.launch_persistent_context.await_args_list[1]
        self.assertEqual(second.args, ("/tmp/test-job-agent-profile",))
        self.assertFalse(second.kwargs["headless"])
        self.assertEqual(second.kwargs["channel"], "chromium")

    async def test_http_scoring_continues_when_browser_missing(self):
        job = {
            "source": "jobs.cz", "title": "Junior Data Analyst",
            "actual_title": "Junior Data Analyst", "job_id": "2000999888",
            "description": "Limited listing", "evidence_quality": "weak",
            "url": "https://example.invalid/job",
        }
        chrom = MagicMock()
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=MagicMock(chromium=chrom))
        manager.__aexit__ = AsyncMock(return_value=False)
        with patch.object(main, "should_browser_recover_evidence", return_value=True), \
             patch.object(main, "async_playwright", return_value=manager), \
             patch.object(main, "launch_chromium", AsyncMock(
                 side_effect=BrowserUnavailable("browser missing")
             )):
            result = await main.browser_recover_weak_evidence([job])
        self.assertEqual(result, [job])
        self.assertEqual(job["evidence_quality"], "weak")
        self.assertEqual(job["browser_evidence_error"], "browser_unavailable")
        self.assertNotEqual(main.score_job(job)["decision"], "APPLY")


if __name__ == "__main__":
    unittest.main()
