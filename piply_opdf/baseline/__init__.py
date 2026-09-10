"""
The baseline layout detector.

A trained document-layout model does the generic work — title, text, table,
figure, header, footer — better than hand-written rules, and Piply's rules then
specialise where the model is not enough: borderless table assembly, key-value
pairs, nested regions, template knowledge and everything driven by human
feedback.

.. code-block:: python

    from piply_opdf.baseline import baseline_detector, is_available

    if is_available():
        regions = baseline_detector().detect(page)

**Always an adapter.** ``is_available()`` answers honestly and every entry point
degrades to "no regions" rather than raising, so the package still runs — and
the tests still pass — on a machine with no model installed.
"""

from __future__ import annotations

from piply_opdf.baseline.labels import LABEL_MAP, PRECISE_LABELS, to_component_type
from piply_opdf.baseline.paddle_layout import (
    DEFAULT_MIN_SCORE,
    PaddleLayoutBaseline,
    is_available,
)

__all__ = [
    "PaddleLayoutBaseline",
    "baseline_detector",
    "is_available",
    "LABEL_MAP",
    "PRECISE_LABELS",
    "to_component_type",
    "DEFAULT_MIN_SCORE",
]


def baseline_detector(**kwargs) -> PaddleLayoutBaseline:
    """The configured baseline detector."""
    return PaddleLayoutBaseline(**kwargs)
