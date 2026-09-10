"""
Stage 2 of the pipeline: split detected layout regions into review units.

Importing this package registers every segmenter, so the registry is populated
before :func:`~piply_opdf.core.segmenter.segment_tree` is called.

    from piply_opdf.core.segmenter import segment_tree
    import piply_opdf.segmentation  # noqa: F401  (registers segmenters)

    segment_tree(component, page)

Unit hierarchy
--------------

===================  ==========================================
Layout               Units
===================  ==========================================
TABLE                ROW / COLUMN -> CELL
PARAGRAPH            SENTENCE -> WORD
SENTENCE             WORD
HEADER / FOOTER      WORD
TITLE                WORD
LIST_ITEM            WORD
KEY_VALUE            KEY / SEPARATOR / VALUE
PANEL                whatever the detectors find inside it
===================  ==========================================

CELL and WORD are terminal — no segmenter is registered for them, so
``segment_tree`` stops there.
"""

from piply_opdf.segmentation.container import ContainerSegmenter
from piply_opdf.segmentation.key_value import KeyValueSegmenter
from piply_opdf.segmentation.prose import SentenceSegmenter, WordSegmenter

__all__ = ["SentenceSegmenter", "WordSegmenter", "KeyValueSegmenter", "ContainerSegmenter"]
