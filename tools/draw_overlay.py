"""Draw detected components onto page images so a person can check them.

    python tools/draw_overlay.py [file-or-folder] [--page N] [--out DIR]

Counts and coverage say *how much* was found. They cannot say whether a
paragraph was really a paragraph. This renders every detected box, labelled and
colour-coded by type, so the answer is visible rather than inferred.

Written for eyeballing, not for tests — no thresholds, no pass/fail.
"""

from __future__ import annotations

import logging
import sys
import warnings
from pathlib import Path

import cv2
import numpy as np

warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

from piply_opdf import Document                          # noqa: E402
from piply_opdf.utils.pdf import iter_pages              # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from check_coverage import components_of                 # noqa: E402

# BGR. Containers cool, text warm, graphics vivid — so a mislabelled region is
# obvious at a glance without reading the label.
COLOURS = {
    "TABLE":            (180, 90, 20),
    "BORDERLESS_TABLE": (200, 140, 40),
    "PANEL":            (150, 110, 60),
    "CELL":             (220, 200, 170),
    "TITLE":            (40, 40, 200),
    "HEADER":           (60, 130, 210),
    "FOOTER":           (90, 160, 220),
    "PARAGRAPH":        (40, 150, 40),
    "SENTENCE":         (110, 190, 110),
    "KEY_VALUE":        (30, 110, 190),
    "LIST_ITEM":        (60, 180, 160),
    "SIGNATURE":        (200, 40, 160),
    "HANDWRITING":      (170, 60, 200),
    "STAMP":            (40, 60, 200),
    "LOGO":             (140, 40, 140),
    "IMAGE":            (100, 100, 100),
    "UNKNOWN":          (0, 0, 255),
}
DEFAULT = (128, 128, 128)


def draw(image: np.ndarray, components: list, *, show_cells: bool = False) -> np.ndarray:
    """Return a copy of *image* with every component outlined and labelled."""
    canvas = image.copy()
    scale = max(image.shape[1] / 2550, 0.6)          # keep labels legible at any DPI
    thickness = max(2, int(3 * scale))

    def one(component, depth: int = 0) -> None:
        kind = str(component.type)
        if kind == "CELL" and not show_cells:
            return
        box = component.bbox
        colour = COLOURS.get(kind, DEFAULT)
        cv2.rectangle(canvas, (box.x, box.y), (box.x1, box.y1), colour,
                      max(1, thickness - depth))

        label = kind if depth == 0 else f"{kind}"
        font_scale = 0.55 * scale
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        ty = max(box.y, th + 4)
        cv2.rectangle(canvas, (box.x, ty - th - 4), (box.x + tw + 6, ty + 2), colour, -1)
        cv2.putText(canvas, label, (box.x + 3, ty - 2), cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale, (255, 255, 255), 1, cv2.LINE_AA)

        for child in getattr(component, "children", []) or []:
            one(child, depth + 1)

    # Draw containers first so smaller components land on top of them.
    order = {"TABLE": 0, "BORDERLESS_TABLE": 0, "PANEL": 1}
    for component in sorted(components, key=lambda c: order.get(str(c.type), 2)):
        one(component)
    return canvas


def render(path: Path, out_dir: Path, only_page: int | None = None) -> list[tuple[int, int]]:
    """Write one annotated PNG per page. Returns (page, component count) pairs."""
    document = Document(path, work_dir=out_dir / "_work" / path.stem)
    document.process_layout()
    components = components_of(document)

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for index, image in iter_pages(path, dpi=300):
        page_no = index + 1
        if only_page and page_no != only_page:
            continue
        on_page = [c for c in components if c.page == page_no]
        dest = out_dir / f"{path.stem}_p{page_no:02d}.png"
        cv2.imwrite(str(dest), draw(image, on_page))
        written.append((page_no, len(on_page)))
    return written


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    target = Path(args[0]) if args else Path(r"C:\Users\Gurudev\Desktop\Git_test\Sample PDFs")
    only_page = next((int(f.split("=")[1]) for f in flags if f.startswith("--page=")), None)
    out_dir = next((Path(f.split("=")[1]) for f in flags if f.startswith("--out=")),
                   Path("_overlay_out"))

    files = ([target] if target.is_file()
             else [f for f in sorted(target.iterdir())
                   if f.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg")])

    for f in files:
        try:
            for page_no, count in render(f, out_dir, only_page):
                print(f"{f.name[:40]:40} page {page_no:3}  {count:4} components")
        except Exception as exc:
            print(f"{f.name[:40]:40} ERROR {type(exc).__name__}: {exc}")
    print(f"\nwrote to {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
