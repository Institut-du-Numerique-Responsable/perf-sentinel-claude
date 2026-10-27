import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from check_plugin import check  # noqa: E402

STATUS = "Status: tried end-to-end"
STACK_HEADINGS = [
    "Recommended instrumentation",
    "What must reach the spans",
    "Turning export on in tests",
    "Test-time traps",
    "Running the tests under capture",
    "Links",
]
CI_HEADINGS = [
    "Detecting it",
    "Wrapping the test step",
    "Analyze and archive",
    "Showing results in the PR",
    "Optional gate",
    "Links",
]
SKILL = """---
name: perf-tests
description: Writes performance integration tests.
license: AGPL-3.0-only
---

Body.
"""


def rule_ids(violations):
    return sorted(v.rule for v in violations)


def ref_doc(headings, status=STATUS):
    lines = ["# Title", ""]
    if status:
        lines += [status, ""]
    for h in headings:
        lines += [f"## {h}", "", "text", ""]
    return "\n".join(lines)


class CheckPluginTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.write("skills/perf-tests/SKILL.md", SKILL)
        self.write("skills/perf-tests/references/stacks/go.md", ref_doc(STACK_HEADINGS))
        self.write("skills/perf-tests/references/ci/github.md", ref_doc(CI_HEADINGS))

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def test_clean_tree_passes(self):
        self.assertEqual(check(self.root), [])

    def test_skill_over_500_lines(self):
        self.write("skills/perf-tests/SKILL.md", SKILL + "line\n" * 500)
        self.assertEqual(rule_ids(check(self.root)), ["skill-size"])

    def test_non_portable_key(self):
        self.write("skills/perf-tests/SKILL.md", SKILL.replace("---\n\nBody", "argument-hint: x\n---\n\nBody"))
        self.assertEqual(rule_ids(check(self.root)), ["frontmatter-keys"])

    def test_description_too_long(self):
        text = SKILL.replace("Writes performance integration tests.", "x" * 1025)
        self.write("skills/perf-tests/SKILL.md", text)
        self.assertEqual(rule_ids(check(self.root)), ["description-length"])

    def test_name_differs_from_dir(self):
        self.write("skills/perf-tests/SKILL.md", SKILL.replace("name: perf-tests", "name: perf-test"))
        self.assertEqual(rule_ids(check(self.root)), ["name-matches-dir"])

    def test_github_blob_link(self):
        url = "https://github.com/Institut-du-Numerique-Responsable/perf-sentinel/blob/main/docs/CI.md"
        self.write("skills/perf-tests/references/notes.md", url)
        self.assertEqual(rule_ids(check(self.root)), ["doc-source"])

    def test_release_link_allowed(self):
        url = "https://github.com/Institut-du-Numerique-Responsable/perf-sentinel/releases/latest"
        self.write("skills/perf-tests/references/notes.md", url)
        self.assertEqual(check(self.root), [])

    def test_missing_status_line(self):
        self.write("skills/perf-tests/references/stacks/go.md", ref_doc(STACK_HEADINGS, status=None))
        self.assertEqual(rule_ids(check(self.root)), ["status-line"])

    def test_missing_stack_section(self):
        self.write("skills/perf-tests/references/stacks/go.md", ref_doc(STACK_HEADINGS[:3] + STACK_HEADINGS[4:]))
        self.assertEqual(rule_ids(check(self.root)), ["stack-sections"])

    def test_missing_ci_section(self):
        self.write("skills/perf-tests/references/ci/github.md", ref_doc(CI_HEADINGS[:4] + CI_HEADINGS[5:]))
        self.assertEqual(rule_ids(check(self.root)), ["ci-sections"])


if __name__ == "__main__":
    unittest.main()
