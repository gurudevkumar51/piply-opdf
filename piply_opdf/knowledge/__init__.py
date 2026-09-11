"""
What the system has been taught, kept apart by the question it answers.

Three stores, three questions:

===================  =====================================================
Text knowledge       "What does this say?"        — ``KnowledgeRegistry``
Layout knowledge     "What kind of region is this?" — ``LayoutKnowledgeStore``
Template knowledge   "What does a page of this family look like?" — Phase T
===================  =====================================================

They are separate files on purpose, so another application can take one without
the others. What they share is the feature extractor: layout appearance comes
from :func:`piply_opdf.classification.measure`, the same function the
classifier uses, so a stored record and a live region are always measured the
same way.

Every record carries a version block (:mod:`piply_opdf.knowledge.provenance`),
and nothing enters the store on a detector's say-so — only what a person
confirmed.
"""

from .actions import DetectorScore, LayoutAction, LayoutFeedback, counts_by_action, tally
from .backup import BackupResult, backup_all, backup_database, restore
from .layout import LayoutFeatures, describe, describe_page, page_band
from .provenance import FEATURE_VERSION, Provenance
from .registry import KnowledgeRegistry
from .store import TRUSTED_SOURCES, LayoutKnowledgeStore, StoredLayout

__all__ = [
    "KnowledgeRegistry",
    # layout knowledge
    "LayoutKnowledgeStore",
    "StoredLayout",
    "LayoutFeatures",
    "describe",
    "describe_page",
    "page_band",
    # provenance
    "FEATURE_VERSION",
    "Provenance",
    # human actions
    "LayoutAction",
    "LayoutFeedback",
    "DetectorScore",
    "tally",
    "counts_by_action",
    "TRUSTED_SOURCES",
    # keeping it
    "backup_all",
    "backup_database",
    "restore",
    "BackupResult",
]
