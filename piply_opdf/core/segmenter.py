"""
Segmentation contracts: stage 2 of the pipeline.

Where a :class:`~piply_opdf.core.detector.Detector` answers *"where is the
table?"*, a :class:`Segmenter` answers *"what are its smallest reviewable
units?"*. Detection finds regions; segmentation splits each region down to the
unit that OCR and the knowledge base actually operate on.

    TABLE      -> ROW / COLUMN -> CELL
    PARAGRAPH  -> SENTENCE     -> WORD
    HEADER     -> SENTENCE     -> WORD
    KEY_VALUE  -> KEY / SEPARATOR / VALUE
    TITLE      -> WORD

Segmenting to the smallest meaningful unit is what makes knowledge reusable:
the same word, verified once, is recognised anywhere it reappears.

Segmenters mirror detectors deliberately — same strategy selection, same
registry, same open/closed extension point — so there is one pattern to learn.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Callable, Iterable

from piply_opdf.core.types import DetectedComponent, PageContext

logger = logging.getLogger(__name__)

__all__ = [
    "SegmentationStrategy",
    "Segmenter",
    "SegmenterRegistry",
    "segmenter_registry",
    "segment_tree",
]


class SegmentationStrategy(ABC):
    """One concrete way of splitting a component into child units."""

    name: str = "unnamed"
    priority: int = 0

    @abstractmethod
    def is_applicable(self, component: DetectedComponent, page: PageContext) -> bool:
        """Whether this strategy can split *component*. Must be cheap."""

    @abstractmethod
    def segment(
        self,
        component: DetectedComponent,
        page: PageContext,
    ) -> list[DetectedComponent]:
        """Return the child units of *component*, or [] if it cannot be split."""


class Segmenter(ABC):
    """Splits one component type into its units, via one or more strategies."""

    #: The component type this segmenter consumes.
    component_type: str = "UNKNOWN"

    #: The component type it produces. Informational; used in logs and docs.
    produces: str = "UNKNOWN"

    def __init__(self, strategies: Iterable[SegmentationStrategy] | None = None) -> None:
        provided = list(strategies) if strategies is not None else self.default_strategies()
        self._strategies = sorted(provided, key=lambda s: s.priority, reverse=True)

    def default_strategies(self) -> list[SegmentationStrategy]:
        return []

    @property
    def strategies(self) -> list[SegmentationStrategy]:
        return list(self._strategies)

    def select_strategy(
        self,
        component: DetectedComponent,
        page: PageContext,
    ) -> SegmentationStrategy | None:
        for strategy in self._strategies:
            if strategy.is_applicable(component, page):
                return strategy
        return None

    def segment(
        self,
        component: DetectedComponent,
        page: PageContext,
    ) -> list[DetectedComponent]:
        """Run the first applicable strategy.

        A failing strategy yields no children rather than aborting the page —
        a component that cannot be split is still usable as its own OCR unit.
        """
        strategy = self.select_strategy(component, page)
        if strategy is None:
            return []
        try:
            return strategy.segment(component, page)
        except Exception:
            logger.exception(
                "%s: strategy %r failed on %s",
                type(self).__name__, strategy.name, component.id,
            )
            return []


class SegmenterRegistry:
    """Factory + registry for segmenters, keyed by the type they consume."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], Segmenter]] = {}

    def register(self, component_type: str) -> Callable[[type[Segmenter]], type[Segmenter]]:
        def decorator(cls: type[Segmenter]) -> type[Segmenter]:
            self.register_factory(component_type, cls)
            return cls
        return decorator

    def register_factory(self, component_type: str, factory: Callable[[], Segmenter]) -> None:
        self._factories[component_type] = factory

    def create(self, component_type: str) -> Segmenter | None:
        """Return a segmenter for *component_type*, or None if it is already a
        terminal unit (CELL, WORD, …) with nothing further to split."""
        factory = self._factories.get(component_type)
        return factory() if factory else None

    def is_registered(self, component_type: str) -> bool:
        return component_type in self._factories

    @property
    def registered_types(self) -> list[str]:
        return sorted(self._factories)


#: Process-wide registry. Segmenter modules register themselves on import.
segmenter_registry = SegmenterRegistry()


def segment_tree(
    component: DetectedComponent,
    page: PageContext,
    *,
    max_depth: int = 4,
    _depth: int = 0,
) -> DetectedComponent:
    """Recursively segment *component* in place, returning it for convenience.

    Descends until no segmenter is registered for a type (a terminal unit),
    a component yields no children, or *max_depth* is reached. The depth cap
    is a safety net against a misbehaving segmenter that returns a child of the
    same type as its parent.

    Components that already carry children (the text-layer detectors attach
    words during detection) are left alone and only their children recursed.
    """
    if _depth >= max_depth:
        return component

    # A shape found by the residual sweep is a guess at where ink sits, not a
    # run of known text — often a fragment of a word, because the rest of the
    # word was already claimed by someone else. Splitting one produced children
    # larger than their own parent. Left whole, it goes to OCR and comes back
    # splittable.
    #
    # Scoped to that sweep on purpose: ``needs_ocr`` alone marks the entire
    # scanned path, and guarding on it stops every scanned page segmenting.
    if component.metadata.get("residual_fragment"):
        return component

    if not component.children:
        segmenter = segmenter_registry.create(component.type)
        if segmenter is not None:
            children = segmenter.segment(component, page)
            # Guard against a segmenter echoing its parent back.
            component.children = [c for c in children if c.type != component.type]

    for child in component.children:
        segment_tree(child, page, max_depth=max_depth, _depth=_depth + 1)

    return component
