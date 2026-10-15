"""Safe Playwright browser selection for the packaged macOS Job Agent.

The PyInstaller app contains the Playwright Python driver, not browser binaries.
An old Chromium cache directory is not evidence that the *current revision* is
installed. Prefer Playwright's managed browser; if it is missing, use an already
installed full Chromium or Google Chrome. Never download executables implicitly.
"""
import json
import os
from pathlib import Path

try:
    import playwright
except ImportError:  # Helps diagnostics in intentionally reduced environments.
    playwright = None


class BrowserUnavailable(RuntimeError):
    """None of the supported local Chrome/Chromium executables are present."""


def browser_cache_dir():
    return Path(os.getenv("PLAYWRIGHT_BROWSERS_PATH") or
                Path.home() / "Library" / "Caches" / "ms-playwright")


def expected_chromium_revisions():
    """Read exact revisions required by the *packaged* Playwright driver."""
    if playwright is None or not getattr(playwright, "__file__", None):
        return {}
    manifest = Path(playwright.__file__).parent / "driver" / "package" / "browsers.json"
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        return {
            entry["name"]: str(entry["revision"])
            for entry in payload.get("browsers", [])
            if entry.get("name") in {"chromium", "chromium-headless-shell"}
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def managed_chromium_available():
    root = browser_cache_dir()
    versions = expected_chromium_revisions()
    paths = []
    chromium = versions.get("chromium")
    shell = versions.get("chromium-headless-shell")
    if chromium:
        base = root / f"chromium-{chromium}"
        paths.extend(base.glob("*/Chromium.app/Contents/MacOS/Chromium"))
        paths.extend(base.glob("*/chrome"))
        paths.extend(base.glob("*/chrome.exe"))
    if shell:
        base = root / f"chromium_headless_shell-{shell}"
        paths.extend(base.glob("*/chrome-headless-shell"))
        paths.extend(base.glob("*/chrome-headless-shell.exe"))
    return any(path.is_file() for path in paths)


def installed_chrome_paths():
    if os.name != "posix":
        return []
    return [
        path for path in (
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ) if path.is_file()
    ]


def browser_available():
    """GUI preflight: ignore stale cache folders from previous Playwright."""
    return managed_chromium_available() or bool(installed_chrome_paths())


def missing_browser_executable(error):
    message = str(error).lower()
    return any(marker in message for marker in (
        "executable doesn't exist",
        "browser executable does not exist",
        "browser has not been found",
        "failed to find browser",
        "browser is not installed",
        "chromium distribution",  # Playwright chrome-channel install hint.
        "enoent",
    ))


async def launch_chromium(chromium, *, headless=True, profile_dir=None, **options):
    """Use managed shell, managed full Chromium, then local Google Chrome.

    A launch error unrelated to a missing executable is propagated, not hidden.
    Persistent profile handling and final Submit checks stay with main.py.
    """
    if profile_dir is None:
        launch = chromium.launch
        args = ()
    else:
        launch = chromium.launch_persistent_context
        args = (str(profile_dir),)

    failures = []
    attempts = [
        ("Playwright Chromium", {}),
        ("full Chromium", {"channel": "chromium"}),
    ]
    attempts.extend(
        ("Google Chrome", {"executable_path": str(path)})
        for path in installed_chrome_paths()
    )
    for name, extra in attempts:
        try:
            result = await launch(*args, headless=headless, **options, **extra)
            if failures:
                print(f"🌐 Browser fallback: using {name} (missing managed Chromium revision)")
            return result
        except Exception as error:
            if not missing_browser_executable(error):
                raise
            failures.append(name)

    raise BrowserUnavailable(
        "No compatible Playwright Chromium or installed Google Chrome executable. "
        "Search-only can continue via HTTP, but browser-dependent checks and "
        "application preparation need a compatible local browser."
    )
