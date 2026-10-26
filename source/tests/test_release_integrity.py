"""The macOS publisher must not delete newly imported source modules.

The v3.1.0 release silently removed fit_intelligence.py from main after
building a healthy app. Validate this safety invariant offline, before
the next release can trigger.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = ROOT / ".github" / "release-source-allowlist.txt"
PUBLISH = ROOT / ".github" / "workflows" / "publish-release.yml"


class ReleaseSourceIntegrityTests(unittest.TestCase):
    def test_every_top_level_python_module_is_reviewed_for_persistence(self):
        modules = {p.name for p in (ROOT / "source").glob("*.py")}
        allowed = {
            line.strip() for line in ALLOWLIST.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertIn("fit_intelligence.py", modules)
        self.assertIn("fit_intelligence.py", allowed)
        self.assertEqual(modules - allowed, set(), "Release would delete modules")

    def test_release_fails_before_packaging_if_modules_are_missing(self):
        workflow = PUBLISH.read_text(encoding="utf-8")
        self.assertIn("Validate release source module inventory", workflow)
        self.assertIn("actual - allowlist", workflow)
        self.assertIn("raise SystemExit(", workflow)
        self.assertLess(
            workflow.index("Validate release source module inventory"),
            workflow.index("Build arm64 macOS app"),
        )
        self.assertLess(
            workflow.index("Validate release source module inventory"),
            workflow.index("gh release create"),
        )
        self.assertIn('done < .github/release-source-allowlist.txt', workflow)
        self.assertIn("test -s source/fit_intelligence.py", workflow)


if __name__ == "__main__":
    unittest.main()
