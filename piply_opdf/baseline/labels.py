"""
Translating the layout model's vocabulary into this system's.

PP-DocLayout names regions in its own terms. Most map straight across; a few
need a decision, and those are the interesting ones — recorded here rather than
buried in a dictionary literal.

Observed on the sample corpus (10 documents, first page each):

===================  =====  =========================================
Model label          Seen   Maps to
===================  =====  =========================================
text                   60   PARAGRAPH
paragraph_title        18   HEADING
header                 13   HEADER
table                   9   TABLE
footer                  7   FOOTER
image                   7   IMAGE
number                  4   SENTENCE — a page number is a short text run
figure_title            4   SENTENCE — a caption is a sentence
doc_title               1   TITLE
seal                    1   STAMP
===================  =====  =========================================

Two of these are worth stating plainly.

**The model already separates `doc_title` from `paragraph_title`.** That is the
Title / Heading distinction of Rule 4, made by a trained model rather than by a
threshold on relative font size. It does not distinguish a heading from a
subheading, so ``SUBHEADING`` is never produced here — that level is left to the
rules and, where they cannot decide, to a person.

**`table` means "a tabular region", not "a table with cells".** The model finds
the region — including on borderless documents where this system's own rules
find nothing at all — but does not build rows or cells. Assembling those stays
Piply's job.
"""

from __future__ import annotations

from piply_opdf.core.types import ComponentType

__all__ = ["LABEL_MAP", "to_component_type", "PRECISE_LABELS"]

#: Model label to component type. Anything absent becomes ``UNKNOWN`` rather
#: than being guessed at — a region the model named and we cannot interpret is
#: still a region, and losing it would be worse than not typing it.
LABEL_MAP: dict[str, str] = {
    # Text
    "text": ComponentType.PARAGRAPH,
    "paragraph": ComponentType.PARAGRAPH,
    "abstract": ComponentType.PARAGRAPH,
    "content": ComponentType.PARAGRAPH,
    "reference": ComponentType.PARAGRAPH,
    # Headings — the model's own distinction, see the module docstring
    "doc_title": ComponentType.TITLE,
    "title": ComponentType.TITLE,
    "paragraph_title": ComponentType.HEADING,
    # Page furniture
    "header": ComponentType.HEADER,
    "footer": ComponentType.FOOTER,
    "header_image": ComponentType.HEADER,
    "footer_image": ComponentType.FOOTER,
    # A page number is a short run of text, not a category of its own here.
    "number": ComponentType.SENTENCE,
    # A caption sits under a figure or table and reads as a sentence.
    "figure_title": ComponentType.SENTENCE,
    "table_title": ComponentType.SENTENCE,
    "chart_title": ComponentType.SENTENCE,
    # Structure
    "table": ComponentType.TABLE,
    "list": ComponentType.LIST_ITEM,
    # Marks and pictures
    "image": ComponentType.IMAGE,
    "figure": ComponentType.IMAGE,
    "chart": ComponentType.IMAGE,
    "seal": ComponentType.STAMP,
    "stamp": ComponentType.STAMP,
    "formula": ComponentType.UNKNOWN,
    "algorithm": ComponentType.UNKNOWN,
    "aside_text": ComponentType.SENTENCE,
}

#: Labels the model is trusted on more than this system's own rules, because
#: they are what it was trained to find and where the rules are weakest.
#: Used by fusion to break a tie — see ``piply_opdf/fusion``.
PRECISE_LABELS = frozenset({
    "doc_title", "paragraph_title", "header", "footer", "image", "figure", "seal",
})


def to_component_type(label: str) -> str:
    """The component type for a model label, or ``UNKNOWN`` if unrecognised."""
    return LABEL_MAP.get((label or "").strip().lower(), ComponentType.UNKNOWN)
