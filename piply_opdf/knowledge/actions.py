"""
What a person did, recorded by kind.

The tempting shape is one boolean — the human agreed, or they did not. It is
also the shape that throws away the answer. These five actions mean genuinely
different things about the detector that produced the region:

===============  ==========================================================
``CONFIRMED``    Detector said table, human said table
``CORRECTED``    Detector said paragraph, human said heading
``ADDED``        Human drew a region the system missed entirely
``DELETED``      Human removed a region the system invented
``REJECTED``     Human rejected an applied template outright
===============  ==========================================================

Collapsed into "agreed / disagreed", a detector that finds everything and names
half of it wrong scores the same as one that names everything it finds
correctly but misses half the page. Those need opposite fixes.

Kept apart, the counts answer the two questions separately:

* *Did we find a region there at all?* — ``DELETED`` is a false positive,
  ``ADDED`` is a false negative.
* *Having found it, did we name it right?* — ``CORRECTED`` against
  ``CONFIRMED``.

**What these numbers are not.** They come from whatever a person happened to
review, which is normally the doubtful end of the pile. That makes them a fair
account of the queue and a poor estimate of the page. A real accuracy figure
needs the gold corpus (Phase E), where the sample is chosen rather than
self-selected. These are for watching a detector change over time, not for
claiming a score.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from piply_opdf.core.types import BBox
from piply_opdf.knowledge.provenance import Provenance, utc_now

__all__ = [
    "LayoutAction", "LayoutFeedback", "DetectorScore", "tally", "counts_by_action",
]


class LayoutAction:
    """The five things a person can do to a detected region."""

    CONFIRMED = "confirmed"
    CORRECTED = "corrected"
    ADDED = "added"
    DELETED = "deleted"
    REJECTED = "rejected"

    ALL: tuple[str, ...] = (CONFIRMED, CORRECTED, ADDED, DELETED, REJECTED)

    #: Actions that say something about a detector's own output. ``REJECTED``
    #: is about an applied template, not about the detector that found the
    #: region, so counting it here would blame the wrong component.
    ABOUT_DETECTORS: tuple[str, ...] = (CONFIRMED, CORRECTED, ADDED, DELETED)


@dataclass(frozen=True, slots=True)
class LayoutFeedback:
    """One human action on one region."""

    action: str
    document_id: str
    page_no: int
    provenance: Provenance
    layout_knowledge_id: int | None = None
    detected_type: str | None = None
    human_type: str | None = None
    bbox_before: BBox | None = None
    bbox_after: BBox | None = None
    user_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.action not in LayoutAction.ALL:
            raise ValueError(
                f"unknown action {self.action!r}; expected one of "
                f"{', '.join(LayoutAction.ALL)}"
            )


@dataclass
class DetectorScore:
    """Review-derived counts for one detector. See the module docstring."""

    detector_name: str
    confirmed: int = 0
    corrected: int = 0
    added: int = 0
    deleted: int = 0

    @property
    def reviewed(self) -> int:
        """Regions the detector proposed and a person judged."""
        return self.confirmed + self.corrected + self.deleted

    @property
    def detection_precision(self) -> float | None:
        """Of what it proposed, how much was really there.

        ``None`` when nothing has been reviewed — an unmeasured detector must
        not read as a detector that scored zero.
        """
        kept = self.confirmed + self.corrected
        return _ratio(kept, kept + self.deleted)

    @property
    def detection_recall(self) -> float | None:
        """Of what was really there, how much it found."""
        kept = self.confirmed + self.corrected
        return _ratio(kept, kept + self.added)

    @property
    def type_accuracy(self) -> float | None:
        """Having found a region, how often it named it correctly."""
        return _ratio(self.confirmed, self.confirmed + self.corrected)

    def summary(self) -> str:
        return (
            f"{self.detector_name}: {self.confirmed} confirmed, "
            f"{self.corrected} corrected, {self.added} added, "
            f"{self.deleted} deleted"
        )


def tally(feedback: Iterable[LayoutFeedback]) -> dict[str, DetectorScore]:
    """Group feedback by the detector that proposed each region.

    ``ADDED`` regions were nobody's proposal — the system missed them — so they
    are charged to the detector that *should* have found them, which is
    recorded on the feedback's provenance by whoever wrote it. Where that is
    unknown the row lands under ``"unknown"`` rather than being dropped, so a
    gap in recording shows up as a gap instead of quietly improving the score.
    """
    scores: dict[str, DetectorScore] = {}

    for row in feedback:
        if row.action not in LayoutAction.ABOUT_DETECTORS:
            continue
        name = row.provenance.detector_name or "unknown"
        score = scores.setdefault(name, DetectorScore(detector_name=name))
        setattr(score, row.action, getattr(score, row.action) + 1)

    return scores


def counts_by_action(feedback: Iterable[LayoutFeedback]) -> dict[str, int]:
    """Every action counted, including ``REJECTED``."""
    counts: dict[str, int] = defaultdict(int)
    for row in feedback:
        counts[row.action] += 1
    return {action: counts[action] for action in LayoutAction.ALL}


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator
