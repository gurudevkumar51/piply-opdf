"""
Where a piece of knowledge came from, and what produced it.

Every knowledge record carries this block. Without it a record written by last
month's detector looks exactly like one written today, and the store keeps
answering with numbers that no longer mean what they meant when they were
saved. That is not a stale cache — it is silent poisoning, because nothing
about the answer looks wrong.

So the rule here is absolute and mechanical:

    **Knowledge is only comparable within a feature version.**

Matching filters on it. It does not try anyway and hope. When the extractor
changes, either the old records are re-derived or they are ignored — there is
no third option that is honest.

The same applies to template fingerprints later (Phase T): a fingerprint built
by extractor v1 cannot be compared with one built by v2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

__all__ = ["FEATURE_VERSION", "Provenance", "utc_now"]

#: The version of the feature extractor that produces layout features.
#:
#: **Bump this whenever a stored number would come out different for the same
#: region.** That includes changing a measurement in
#: :mod:`piply_opdf.classification.content`, changing how geometry is
#: normalised, and changing how neighbours are chosen. It does *not* include
#: adding a brand-new nullable column, because every old record still means
#: what it said.
#:
#: History:
#:   ``1`` — geometry, relationships, and the appearance signals from
#:           ``classification.measure``.
FEATURE_VERSION = "1"


def utc_now() -> datetime:
    """Timezone-aware now. Naive timestamps sort wrongly across machines."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class Provenance:
    """The versioning block required on every knowledge record.

    ``detector_name`` and ``detector_version`` say who proposed the region;
    ``model_version`` is set only when the baseline model was involved, so a
    later question like "did the model help?" is answerable from the store
    rather than from memory.
    """

    source_document: str
    source_page: int
    detector_name: str = "unknown"
    detector_version: str = "0"
    model_version: str | None = None
    feature_version: str = FEATURE_VERSION
    created_at: datetime = field(default_factory=utc_now)

    def as_row(self) -> dict[str, object]:
        """Flatten to the column names used by the knowledge stores."""
        return {
            "source_document": self.source_document,
            "source_page": self.source_page,
            "detector_name": self.detector_name,
            "detector_version": self.detector_version,
            "model_version": self.model_version,
            "feature_version": self.feature_version,
            "created_at": self.created_at.isoformat(),
        }

    @property
    def is_current(self) -> bool:
        """Whether this record can be compared against freshly built features."""
        return self.feature_version == FEATURE_VERSION
