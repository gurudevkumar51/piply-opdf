"""
Precision and recall against labelled ground truth.

Coverage (see :mod:`piply_opdf.quality.coverage`) says whether content was
lost. It says nothing about whether components were given the *right type* —
that needs someone to have written down what the right answer is.

This module compares detected components against a hand-labelled page and
reports, per component type, how often detection was right.

Matching
--------
A detection matches a label when they are the same type and their boxes overlap
by at least ``min_iou``. Each label matches at most one detection, best first,
so two detections covering one label count as one hit and one false positive
rather than two hits.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from piply_opdf.core.types import BBox, DetectedComponent

__all__ = [
    "LabelledRegion",
    "PageLabels",
    "TypeScore",
    "AccuracyReport",
    "load_labels",
    "score_page",
    "DEFAULT_MIN_IOU",
]

#: Overlap required to call a detection and a label the same region. 0.5 is the
#: usual convention and is forgiving enough that a slightly loose or tight box
#: still counts, while a box covering the wrong thing does not.
DEFAULT_MIN_IOU = 0.5


@dataclass(frozen=True, slots=True)
class LabelledRegion:
    """One region a person marked up."""

    type: str
    bbox: BBox
    #: Set when the labeller was unsure. Excluded from scoring rather than
    #: counted against the system — a case a human could not decide is not
    #: evidence about the detector.
    uncertain: bool = False


@dataclass(frozen=True, slots=True)
class PageLabels:
    """Ground truth for one page."""

    source: str
    page: int
    regions: tuple[LabelledRegion, ...]


@dataclass
class TypeScore:
    """Counts for one component type."""

    matched: int = 0
    detected: int = 0
    labelled: int = 0

    @property
    def precision(self) -> float:
        """Of what was detected, how much was right. 1.0 when nothing detected."""
        return self.matched / self.detected if self.detected else 1.0

    @property
    def recall(self) -> float:
        """Of what was there, how much was found. 1.0 when nothing labelled."""
        return self.matched / self.labelled if self.labelled else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass
class AccuracyReport:
    """Per-type scores for a page or a whole corpus."""

    by_type: dict[str, TypeScore] = field(default_factory=dict)

    def score(self, component_type: str) -> TypeScore:
        return self.by_type.setdefault(component_type, TypeScore())

    def merge(self, other: AccuracyReport) -> None:
        for name, score in other.by_type.items():
            mine = self.score(name)
            mine.matched += score.matched
            mine.detected += score.detected
            mine.labelled += score.labelled

    def as_table(self) -> str:
        lines = [f"{'type':20} {'precision':>10} {'recall':>8} {'F1':>7} "
                 f"{'found':>7} {'truth':>7}"]
        lines.append("-" * 64)
        for name in sorted(self.by_type):
            s = self.by_type[name]
            lines.append(f"{name:20} {s.precision:10.3f} {s.recall:8.3f} "
                         f"{s.f1:7.3f} {s.detected:7} {s.labelled:7}")
        return "\n".join(lines)


def _iou(a: BBox, b: BBox) -> float:
    overlap = a.intersection_area(b)
    if not overlap:
        return 0.0
    union = a.area + b.area - overlap
    return overlap / union if union else 0.0


def load_labels(path: str | Path) -> PageLabels:
    """Read one page's ground truth.

    Expected shape::

        {
          "source": "invoice.pdf",
          "page": 1,
          "regions": [
            {"type": "TABLE", "bbox": [120, 340, 2100, 900]},
            {"type": "SIGNATURE", "bbox": [1500, 2800, 400, 160], "uncertain": true}
          ]
        }
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    regions = []
    for raw in data.get("regions", []):
        box = BBox.from_any(raw.get("bbox"))
        if box is None:
            continue
        regions.append(
            LabelledRegion(
                type=str(raw["type"]).upper(),
                bbox=box,
                uncertain=bool(raw.get("uncertain", False)),
            )
        )
    return PageLabels(
        source=str(data.get("source", "")),
        page=int(data.get("page", 1)),
        regions=tuple(regions),
    )


def score_page(
    detected: list[DetectedComponent],
    labels: PageLabels,
    *,
    min_iou: float = DEFAULT_MIN_IOU,
    types: tuple[str, ...] | None = None,
) -> AccuracyReport:
    """Compare one page's detections against its labels.

    Regions marked *uncertain* are dropped from both sides — a case a person
    could not decide should not count for or against the system.
    """
    truth = [r for r in labels.regions if not r.uncertain]
    if types is not None:
        truth = [r for r in truth if r.type in types]
        detected = [d for d in detected if d.type in types]

    report = AccuracyReport()
    for region in truth:
        report.score(region.type).labelled += 1
    for component in detected:
        report.score(component.type).detected += 1

    # Best overlap first, so a clear match is not stolen by a marginal one.
    pairs = sorted(
        (
            (_iou(d.bbox, t.bbox), di, ti)
            for di, d in enumerate(detected)
            for ti, t in enumerate(truth)
            if d.type == t.type
        ),
        key=lambda p: p[0],
        reverse=True,
    )

    used_detections: set[int] = set()
    used_truth: set[int] = set()
    for overlap, di, ti in pairs:
        if overlap < min_iou or di in used_detections or ti in used_truth:
            continue
        used_detections.add(di)
        used_truth.add(ti)
        report.score(truth[ti].type).matched += 1

    return report
