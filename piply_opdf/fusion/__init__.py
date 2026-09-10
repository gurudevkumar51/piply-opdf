"""
Combining the baseline model's regions with Piply's own detections.

Measured across the sample corpus, the two are genuinely complementary —
neither is a superset of the other:

===============================  ===============================
Baseline finds, Piply does not   Piply finds, baseline does not
===============================  ===============================
HEADING      9 pages             KEY_VALUE     11 pages
SENTENCE     6                   HANDWRITING   10
PARAGRAPH    5                   FOOTER         6
HEADER       2                   LIST_ITEM      6
TITLE        1                   PANEL          5
TABLE        1  (borderless)     LOGO / STAMP   4
===============================  ===============================

So fusion is not "pick the better detector". It is "keep what each is good at,
and notice when they disagree".

The three outcomes
------------------

**Agreement** raises confidence. Two independent detectors reaching the same
answer is real evidence, and it is the cheapest evidence available.

**One found it, the other did not** keeps the finding, at the finder's own
confidence. A baseline table on a borderless statement is worth having even
though the rules missed it; a key-value pair is worth having even though the
model has no such concept.

**Disagreement is not resolved silently.** Where both claim the same region and
name it differently, the more specific type wins *and the component is flagged
for review*, carrying both opinions. Per the governing principle: a wrong type
held confidently, with nobody looking, is the failure this system exists to
avoid.
"""

from __future__ import annotations

from piply_opdf.fusion.combine import (
    FusionOutcome,
    fuse,
    specificity,
)

__all__ = ["fuse", "FusionOutcome", "specificity"]
