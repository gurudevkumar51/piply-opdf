"""Baseline layout model against Piply's own rules, page by page.

    python tools/compare_baseline.py [folder]

Not precision and recall — that needs the labelled corpus (Phase E). This shows
*where each finds things the other does not*, which is what fusion has to
reconcile.
"""

from __future__ import annotations

import logging
import sys
import warnings
from collections import Counter
from pathlib import Path

warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

from piply_opdf import Document                          # noqa: E402
from piply_opdf.baseline import baseline_detector, is_available  # noqa: E402
from piply_opdf.core import PageContext                  # noqa: E402
from piply_opdf.utils.pdf import iter_pages              # noqa: E402


def piply_counts(doc: Document, page_no: int) -> Counter:
    tally: Counter[str] = Counter()
    for name in ("panels", "headers", "footers", "titles", "key_values",
                 "paragraphs", "sentences", "list_items", "graphics"):
        for item in getattr(doc, name, []) or []:
            if item.get("page", 1) == page_no:
                tally[item.get("type", name.upper())] += 1
    for table in list(doc.tables) + list(doc.borderless_tables):
        if getattr(table, "page", 1) == page_no:
            tally["TABLE"] += 1
    return tally


def main() -> int:
    if not is_available():
        print("baseline model unavailable")
        return 1

    src = Path(sys.argv[1] if len(sys.argv) > 1
               else r"C:\Users\Gurudev\Desktop\Git_test\Sample PDFs")
    files = [f for f in sorted(src.iterdir())
             if f.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg")]

    detector = baseline_detector()
    only_baseline: Counter[str] = Counter()
    only_piply: Counter[str] = Counter()

    print(f"{'file':34} {'baseline':>34}   {'piply':>34}")
    for f in files:
        try:
            doc = Document(f, work_dir=Path("_cmp_out") / f.stem)
            doc.process_layout()
        except Exception as exc:
            print(f"{f.name[:34]:34}  ERROR {type(exc).__name__}")
            continue

        image = next((im for i, im in iter_pages(f, dpi=300) if i == 0), None)
        if image is None:
            continue
        page = PageContext(page_number=1, source_path=f.resolve(), image=image, dpi=300)

        base = Counter(c.type for c in detector.detect(page))
        mine = piply_counts(doc, 1)

        for kind in set(base) | set(mine):
            if base.get(kind, 0) and not mine.get(kind, 0):
                only_baseline[kind] += 1
            if mine.get(kind, 0) and not base.get(kind, 0):
                only_piply[kind] += 1

        print(f"{f.name[:34]:34} {str(dict(base.most_common(4)))[:34]:>34}   "
              f"{str(dict(mine.most_common(4)))[:34]:>34}")

    print("\nfound by the BASELINE where Piply found none (pages):")
    for kind, n in only_baseline.most_common():
        print(f"   {kind:16} {n}")
    print("\nfound by PIPLY where the baseline found none (pages):")
    for kind, n in only_piply.most_common():
        print(f"   {kind:16} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
