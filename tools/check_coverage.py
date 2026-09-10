"""Report ink coverage per page over a folder of documents.

    python tools/check_coverage.py [folder]

Coverage is the share of a page's ink that ended up inside some component. It
is the one detection quality signal that needs no labelled ground truth: a low
score means content was lost, whatever the document is.
"""

from __future__ import annotations

import logging
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

from piply_opdf import Document                                    # noqa: E402
from piply_opdf.core import PageContext                            # noqa: E402
from piply_opdf.quality import TARGET_COVERAGE, measure_coverage   # noqa: E402
from piply_opdf.utils.pdf import iter_pages                        # noqa: E402


def components_of(document: Document) -> list:
    """Every component the pipeline produced, as DetectedComponent-like objects."""
    from piply_opdf.core.types import BBox, DetectedComponent

    out: list[DetectedComponent] = []

    def add(raw: dict) -> DetectedComponent | None:
        box = BBox.from_any(raw.get("bbox"))
        if box is None:
            return None
        node = DetectedComponent(
            id=raw.get("id", ""), type=raw.get("type", "UNKNOWN"),
            page=raw.get("page", 1), bbox=box,
        )
        node.children = [c for c in (add(k) for k in raw.get("children", [])) if c]
        return node

    for group in (document.panels, document.headers, document.footers,
                  document.titles, document.key_values, document.paragraphs,
                  document.sentences, document.list_items, document.graphics):
        out.extend(c for c in (add(r) for r in group) if c)

    # Tables are model objects, not dicts. Their bbox is a pydantic model, so
    # tuple() over it yields (field, value) pairs rather than coordinates —
    # read the fields explicitly.
    def box_of(obj):
        raw = getattr(obj, "bbox", None)
        if raw is None:
            return None
        if hasattr(raw, "x") and hasattr(raw, "width"):
            return BBox(int(raw.x), int(raw.y), int(raw.width), int(raw.height))
        return BBox.from_any(raw)

    for table in list(document.tables) + list(document.borderless_tables):
        box = box_of(table)
        if box is None:
            continue
        node = DetectedComponent(id=str(getattr(table, "table_id", "")),
                                 type="TABLE", page=getattr(table, "page", 1), bbox=box)
        # Cells cover the text; the table box alone leaves gaps between rules.
        node.children = [
            DetectedComponent(id=str(getattr(c, "cell_id", "")), type="CELL",
                              page=node.page, bbox=cb)
            for c in getattr(table, "cells", []) or []
            if (cb := box_of(c)) is not None
        ]
        out.append(node)
    return out


def main() -> int:
    src = Path(sys.argv[1] if len(sys.argv) > 1
               else r"C:\Users\Gurudev\Desktop\Git_test\Sample PDFs")
    work = Path("_coverage_out")

    files = [f for f in sorted(src.iterdir())
             if f.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg")]

    print(f"{'file':38} {'page':>5} {'coverage':>9} {'missed':>9}  worst gap")
    print("-" * 86)

    scores = []
    for f in files:
        try:
            document = Document(f, work_dir=work / f.stem)
            document.process_layout()
            components = components_of(document)
        except Exception as exc:
            print(f"{f.name[:38]:38}  ERROR {type(exc).__name__}: {exc}")
            continue

        for index, image in iter_pages(f, dpi=300):
            page_no = index + 1
            page = PageContext(page_number=page_no, source_path=f.resolve(),
                               image=image, dpi=300)
            on_page = [c for c in components if c.page == page_no]
            report = measure_coverage(page, on_page)
            scores.append((f.name, page_no, report.accounted))

            flag = "" if report.meets_target else "  <-- below target"
            worst = report.gaps[0].to_tuple() if report.gaps else "-"
            print(f"{f.name[:38]:38} {page_no:5} {report.accounted:9.4f} "
                  f"{report.missed_ink:9}  {worst}{flag}")

    if scores:
        values = [s for _, _, s in scores]
        below = [s for s in scores if s[2] < TARGET_COVERAGE]
        print(f"\npages: {len(values)}   mean {sum(values)/len(values):.4f}   "
              f"min {min(values):.4f}   target {TARGET_COVERAGE}")
        print(f"below target: {len(below)}/{len(values)}")
        for name, page_no, score in sorted(below, key=lambda s: s[2])[:10]:
            print(f"   {score:.4f}  {name} page {page_no}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
