#!/usr/bin/env python3
"""Structural checks for the perf-sentinel plugin. Usage: check_plugin.py [root]"""
import re
import sys
from collections import namedtuple
from pathlib import Path

Violation = namedtuple("Violation", "path rule detail")

PORTABLE_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
STATUS_LINES = {"Status: tried end-to-end", "Status: written from official docs, not yet tried"}
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
DOC_SOURCE = re.compile(r"github\.com/Institut-du-Numerique-Responsable/perf-sentinel/(blob|tree)/")


def frontmatter(lines):
    """Lines between the first two '---' lines, or [] when there is no frontmatter."""
    if not lines or lines[0].strip() != "---":
        return []
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i]
    return []


def description(fm):
    """The description value: rest of its line plus following indented lines (handles '|' and '>')."""
    for i, line in enumerate(fm):
        m = re.match(r"description:(.*)", line)
        if m:
            parts = [m.group(1).strip()]
            for nxt in fm[i + 1:]:
                if not nxt.startswith((" ", "\t")):
                    break
                parts.append(nxt.strip())
            parts = [p for p in parts if p]
            if parts and re.fullmatch(r"[|>][-+]?", parts[0]):
                parts = parts[1:]
            return " ".join(parts)
    return None


def check_skill(skill_md, rel, out):
    lines = skill_md.read_text().splitlines()
    if len(lines) >= 500:
        out.append(Violation(rel, "skill-size", f"{len(lines)} lines, limit is under 500"))
    fm = frontmatter(lines)
    keys = [m.group(1) for line in fm if (m := re.match(r"([a-z][a-z-]*):", line))]
    extra = sorted(set(keys) - PORTABLE_KEYS)
    if extra:
        out.append(Violation(rel, "frontmatter-keys", f"non-portable keys: {', '.join(extra)}"))
    desc = description(fm)
    if not desc:
        out.append(Violation(rel, "description-missing", "no description in the frontmatter"))
    elif len(desc) > 1024:
        out.append(Violation(rel, "description-length", f"{len(desc)} characters, limit is 1024"))
    name = next((m.group(1).strip() for line in fm if (m := re.match(r"name:(.*)", line))), None)
    if name != skill_md.parent.name:
        out.append(Violation(rel, "name-matches-dir", f"name {name!r} differs from {skill_md.parent.name!r}"))


def check_reference(md, rel, headings, rule, out):
    lines = md.read_text().splitlines()
    first = next((line.strip() for line in lines if line.strip() and not line.startswith("#")), "")
    if first not in STATUS_LINES:
        out.append(Violation(rel, "status-line", f"first non-heading line is {first!r}"))
    present = {line[3:].strip() for line in lines if line.startswith("## ")}
    missing = [h for h in headings if h not in present]
    if missing:
        out.append(Violation(rel, rule, f"missing sections: {', '.join(missing)}"))


def check(root: Path) -> list:
    root = Path(root)
    skills = root / "skills"
    out = []
    for skill_md in sorted(skills.glob("*/SKILL.md")):
        check_skill(skill_md, str(skill_md.relative_to(root)), out)
    for f in sorted(skills.rglob("*.md")):
        if DOC_SOURCE.search(f.read_text()):
            out.append(Violation(str(f.relative_to(root)), "doc-source", "github blob or tree link, use a release link"))
    for md in sorted(skills.glob("*/references/stacks/*.md")):
        check_reference(md, str(md.relative_to(root)), STACK_HEADINGS, "stack-sections", out)
    for md in sorted(skills.glob("*/references/ci/*.md")):
        check_reference(md, str(md.relative_to(root)), CI_HEADINGS, "ci-sections", out)
    return out


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    violations = check(root)
    for v in violations:
        print(f"{v.path}: {v.rule}: {v.detail}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
