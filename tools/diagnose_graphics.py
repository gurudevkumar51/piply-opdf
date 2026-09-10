"""Print the measured features behind every graphic verdict on a page.

    python tools/diagnose_graphics.py <file> [page]

Used to work out why printed text was coming back as LOGO or HANDWRITING.
Prints one row per graphic component so the numbers can be compared against the
calibration table in classification/content.py.
"""

from __future__ import annotations

import logging
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

from piply_opdf import Document                        # noqa: E402
from piply_opdf.classification import classify, measure  # noqa: E402
from piply_opdf.utils.pdf import iter_pages            # noqa: E402


def main() -> int:
    path = Path(sys.argv[1])
    want_page = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    document = Document(path, work_dir=Path("_diag_out") / path.stem)
    document.process_layout()

    images = {i + 1: im for i, im in iter_pages(path, dpi=300)}
    image = images[want_page]

    print(f"{'type':13} {'ink':>6} {'dens':>7} {'areaCV':>7} {'strokeCV':>9} "
          f"{'sat':>6} {'rich':>7} {'col':>4} {'grp':>4} {'rows':>6}  bbox")
    print("-" * 110)

    for raw in document.graphics:
        if raw.get("page", 1) != want_page:
            continue
        x, y, w, h = raw["bbox"]
        crop = image[y:y + h, x:x + w]
        f = measure(crop)
        if f is None:
            print(f"{raw['type']:13}  (unmeasurable)  {raw['bbox']}")
            continue
        verdict = classify(f)
        print(f"{verdict.type:13} {f.ink_ratio:6.3f} {f.component_density:7.0f} "
              f"{f.component_area_cv:7.2f} {f.stroke_width_cv:9.3f} {f.saturation:6.2f} "
              f"{f.colour_richness:7.3f} {f.colour_clusters:4} {f.word_groups:4} "
              f"{f.row_coverage:6.2f}  {raw['bbox']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
