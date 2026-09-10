"""Compare generated samples against the real measurements they stand in for."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from piply_opdf.classification import classify, measure           # noqa: E402
from tests.unit.test_classification import (                      # noqa: E402
    make_coloured_text, make_handwriting, make_logo, make_photo,
    make_printed, make_scanned_printed, make_signature, make_stamp,
)

GENS = {
    "printed": make_printed,
    "scanned_printed": make_scanned_printed,
    "coloured_text": make_coloured_text,
    "handwriting": make_handwriting,
    "signature": make_signature,
    "logo": make_logo,
    "stamp": make_stamp,
    "photo": make_photo,
}


def main() -> int:
    print(f"{'class':18} {'dens':>16} {'strokeCV':>16} {'baseline':>16}  verdicts")
    print("-" * 100)
    for name, gen in GENS.items():
        feats = [measure(gen(i)) for i in range(12)]
        dens = [f.component_density for f in feats]
        stroke = [f.stroke_width_cv for f in feats]
        base = [f.baseline_scatter for f in feats]
        verdicts = {classify(f).type for f in feats}
        rng = lambda v: f"{min(v):.2f}-{max(v):.2f}"                      # noqa: E731
        print(f"{name:18} {rng(dens):>16} {rng(stroke):>16} {rng(base):>16}  {sorted(verdicts)}")

    print("\nreal scanned print, measured earlier on Sbizhub page 1:")
    print("  density 585-910   strokeCV 0.344-0.396   baseline 0.019-0.131")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
