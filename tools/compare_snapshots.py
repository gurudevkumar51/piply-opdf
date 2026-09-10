"""Diff two corpus snapshots. Silence is the good outcome for a refactor."""

from __future__ import annotations

import json
import sys
from pathlib import Path

before = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
after = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

changed = same = 0
lines: list[str] = []
for name in sorted(set(before) | set(after)):
    b, a = before.get(name, {}), after.get(name, {})
    if b == a:
        same += 1
        continue
    changed += 1
    lines.append(f"\n{name}")
    for kind in sorted(set(b) | set(a)):
        bv, av = b.get(kind, 0), a.get(kind, 0)
        if bv != av:
            lines.append(f"    {kind:20} {bv!s:>8} -> {av!s:>8}")

print(f"unchanged: {same}   changed: {changed}")
print("\n".join(lines) if lines else "\nno differences")
