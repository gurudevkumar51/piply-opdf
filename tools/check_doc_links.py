"""Every internal link in the docs must resolve. Broken links rot silently."""

from __future__ import annotations

import re
import sys
from pathlib import Path

LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
ROOT = Path(".")


def anchor_of(heading: str) -> str:
    """GitHub's heading-to-anchor rule.

    Each space becomes a hyphen — runs are **not** collapsed. That is why a
    heading containing an em-dash ("Rule 0 — is it text?") yields a double
    hyphen: the dash is stripped and the two spaces around it each become one.
    Collapsing them was this checker's own bug, and it reported nine perfectly
    good links as broken. Trailing hyphens are kept for the same reason: a
    heading ending in an emoji leaves one behind.
    """
    slug = heading.strip().lower()
    slug = re.sub(r"[`*_]", "", slug)
    slug = re.sub(r"[^\w\s-]", "", slug)
    return slug.replace(" ", "-")


def anchors_in(path: Path) -> set[str]:
    found = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            found.add(anchor_of(line.lstrip("#")))
    return found


def main() -> int:
    files = [ROOT / "README.md"] + sorted((ROOT / "docs").glob("*.md"))
    anchors = {f: anchors_in(f) for f in files if f.exists()}
    broken: list[str] = []

    for source in files:
        if not source.exists():
            continue
        for label, target in LINK.findall(source.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path_part, _, anchor = target.partition("#")

            if path_part:
                resolved = (source.parent / path_part).resolve()
                if not resolved.exists():
                    broken.append(f"{source}: [{label}] -> missing file {path_part}")
                    continue
                target_file = next((f for f in anchors if f.resolve() == resolved), None)
            else:
                target_file = source

            if anchor and target_file is not None and anchor not in anchors[target_file]:
                broken.append(f"{source}: [{label}] -> no anchor #{anchor}")

    if broken:
        print(f"{len(broken)} broken link(s):")
        for item in broken:
            print("  " + item)
        return 1
    print(f"all internal links resolve ({len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
