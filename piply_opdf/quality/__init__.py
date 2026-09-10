"""Measurable quality signals.

    from piply_opdf.quality import measure_coverage

    report = measure_coverage(page, components)
    print(report.accounted, report.gaps)
"""

from piply_opdf.quality.accuracy import (
    DEFAULT_MIN_IOU,
    AccuracyReport,
    LabelledRegion,
    PageLabels,
    TypeScore,
    load_labels,
    score_page,
)
from piply_opdf.quality.coverage import (
    TARGET_COVERAGE,
    CoverageReport,
    measure_coverage,
)

from piply_opdf.quality.images import (
    PageImages,
    build_page_images,
    structure_evidence,
)
from piply_opdf.quality.orientation import (
    SIDEWAYS,
    UNDECIDED,
    UPRIGHT,
    OrientationEstimate,
    correct_orientation,
    estimate_orientation,
)

__all__ = [
    "CoverageReport", "measure_coverage", "TARGET_COVERAGE",
    "AccuracyReport", "TypeScore", "LabelledRegion", "PageLabels",
    "load_labels", "score_page", "DEFAULT_MIN_IOU",
    # The three-image pipeline and page orientation.
    "PageImages", "build_page_images", "structure_evidence",
    "OrientationEstimate", "estimate_orientation", "correct_orientation",
    "UPRIGHT", "SIDEWAYS", "UNDECIDED",
]
