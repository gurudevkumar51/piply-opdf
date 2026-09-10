"""Keep the test counts in the documentation true.

    python tools/sync_docs.py            # check only, non-zero exit if stale
    python tools/sync_docs.py --write    # update them

The count lives in six files. It has gone stale repeatedly — a change adds
tests, one or two documents get updated, and the rest quietly claim a number
that has not been right for weeks. A reader cannot tell which is current, which
makes every number in the docs slightly less believable.

So it is derived rather than typed: this collects the real figures from pytest
and rewrites the places that carry them.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Every place a count appears, as (path, pattern, replacement template).
#: ``{cases}`` and ``{functions}`` are substituted.
TARGETS: list[tuple[str, str, str]] = [
    ("README.md",
     r"\d+ tests\. Corpora",
     "{cases} tests. Corpora"),
    ("docs/installation.md",
     r"\d+ tests\. See",
     "{cases} tests. See"),
    ("docs/quality.md",
     r"Detection is verified by \*\*\d+ tests\*\*",
     "Detection is verified by **{cases} tests**"),
    ("docs/testing.md",
     r"\*\*\d+ test functions · \d+ cases · \d+ passing, 0 failing\.\*\*",
     "**{functions} test functions · {cases} cases · {cases} passing, 0 failing.**"),
    ("docs/testing.md",
     r"\| \*\*Total\*\* \| \*\*\d+\*\* \| \*\*\d+\*\* \| \|",
     "| **Total** | **{functions}** | **{cases}** | |"),
    ("docs/testing.md",
     r"All \d+ pass\.",
     "All {cases} pass."),
    ("docs/backlog.md",
     r"\d+ tests passing, 0 failing",
     "{cases} tests passing, 0 failing"),
    ("tools/make_flowchart.py",
     r"\d+ automated tests passing",
     "{cases} automated tests passing"),
]


def collect() -> tuple[int, int]:
    """(cases, functions) as pytest actually reports them."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/unit", "--collect-only", "-q", "--no-header"],
        cwd=ROOT, capture_output=True, text=True,
        env={**__import__("os").environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
    )
    text = result.stdout

    match = re.search(r"(\d+) tests? collected", text)
    if not match:
        raise SystemExit(f"could not read a test count from pytest:\n{text[-800:]}")
    cases = int(match.group(1))

    # A parametrised test is one function and many cases. `-q --collect-only`
    # prints a tree of `<Function name[param]>`, so the function name is the
    # part before the bracket.
    functions = len({
        m.group(1) for m in re.finditer(r"<Function ([^\[>]+)", text)
    })
    return cases, functions or cases


def main() -> int:
    write = "--write" in sys.argv
    cases, functions = collect()
    print(f"pytest reports {cases} cases across {functions} functions")

    stale: list[str] = []
    for name, pattern, template in TARGETS:
        path = ROOT / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        wanted = template.format(cases=cases, functions=functions)

        updated, count = re.subn(pattern, wanted.replace("\\", "\\\\"), text)
        if count == 0:
            stale.append(f"{name}: pattern not found — {pattern}")
            continue
        if updated == text:
            continue

        stale.append(f"{name}: out of date")
        if write:
            path.write_text(updated, encoding="utf-8")

    if not stale:
        print("all documented counts are current")
        return 0

    print(("updated:" if write else "STALE (run with --write):"))
    for item in stale:
        print("   " + item)
    return 0 if write else 1


if __name__ == "__main__":
    raise SystemExit(main())
