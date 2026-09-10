"""Component counts per document, as a before/after comparison point.

    python tools/corpus_snapshot.py [folder] [out.json]

Counts are the most sensitive signal that a pipeline change altered detection:
coverage barely moves when types change, but counts do.
"""

from __future__ import annotations

import json
import logging
import sys
import warnings
from collections import Counter
from pathlib import Path

warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

from piply_opdf import Document                       # noqa: E402


def counts_for(doc: Document) -> dict:
    tally: Counter[str] = Counter()
    for name in ("panels", "headers", "footers", "titles", "key_values",
                 "paragraphs", "sentences", "list_items", "graphics"):
        for item in getattr(doc, name, []) or []:
            tally[item.get("type", name.upper())] += 1
    for table in list(doc.tables) + list(doc.borderless_tables):
        tally["TABLE"] += 1
        tally["CELL"] += len(getattr(table, "cells", []) or [])
        tally["ROW"] += len(getattr(table, "rows", []) or [])
        tally["COLUMN"] += len(getattr(table, "columns", []) or [])
    return dict(sorted(tally.items()))


def main() -> int:
    src = Path(sys.argv[1] if len(sys.argv) > 1
               else r"C:\Users\Gurudev\Desktop\Git_test\Sample PDFs")
    dest = Path(sys.argv[2] if len(sys.argv) > 2 else "_snapshot.json")

    files = [f for f in sorted(src.iterdir())
             if f.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg")]

    snapshot: dict[str, dict] = {}
    for f in files:
        try:
            doc = Document(f, work_dir=Path("_snapshot_out") / f.stem)
            doc.process_layout()
            snapshot[f.name] = counts_for(doc)
            print(f"{f.name[:42]:42} {sum(snapshot[f.name].values()):5} components")
        except Exception as exc:
            snapshot[f.name] = {"ERROR": f"{type(exc).__name__}: {exc}"}
            print(f"{f.name[:42]:42} ERROR {type(exc).__name__}")

    dest.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
