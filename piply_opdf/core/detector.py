"""
Detection contracts: strategies, detectors, and the detector registry.

Design
------
A **strategy** knows one way to find one kind of component — e.g. "read headers
from the PDF text layer" or "find headers by running OCR over the top zone of
the rendered page".

A **detector** owns an ordered list of strategies and delegates to the first one
that reports itself applicable for the page at hand. That is what lets a single
``HeaderDetector`` serve both digital and scanned PDFs: the text strategy
declines when :attr:`PageContext.has_text_layer` is False, and the CV strategy
picks it up.

Adding a new approach means adding a strategy — detectors, the pipeline and the
persistence layer are untouched (open/closed).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Callable, Iterable

from piply_opdf.core.exceptions import DetectionError
from piply_opdf.core.types import BBox, DetectedComponent, PageContext

logger = logging.getLogger(__name__)

__all__ = [
    "DetectionStrategy",
    "Detector",
    "CompositeDetector",
    "DetectorRegistry",
    "registry",
]


class DetectionStrategy(ABC):
    """One concrete way of locating components of a single type."""

    #: Human-readable name, used in logs and manifests.
    name: str = "unnamed"

    #: Higher wins when several strategies are applicable to the same page.
    priority: int = 0

    @abstractmethod
    def is_applicable(self, page: PageContext) -> bool:
        """Whether this strategy can run against *page*.

        Must be cheap — it is called for every page. The canonical test is
        ``page.has_text_layer``.
        """

    @abstractmethod
    def detect(
        self,
        page: PageContext,
        exclusions: list[BBox] | None = None,
    ) -> list[DetectedComponent]:
        """Locate components on *page*, skipping regions covered by
        *exclusions* (already-claimed areas such as tables)."""


class Detector(ABC):
    """Finds one component type on a page, via one or more strategies.

    Subclasses declare :attr:`component_type` and supply strategies. Ordering is
    by :attr:`DetectionStrategy.priority`, highest first.
    """

    component_type: str = "UNKNOWN"

    def __init__(self, strategies: Iterable[DetectionStrategy] | None = None) -> None:
        provided = list(strategies) if strategies is not None else self.default_strategies()
        self._strategies = sorted(provided, key=lambda s: s.priority, reverse=True)
        if not self._strategies:
            raise DetectionError(f"{type(self).__name__} was constructed with no strategies")

    def default_strategies(self) -> list[DetectionStrategy]:
        """Strategies used when none are injected. Override in subclasses."""
        return []

    @property
    def strategies(self) -> list[DetectionStrategy]:
        return list(self._strategies)

    def select_strategy(self, page: PageContext) -> DetectionStrategy | None:
        """The highest-priority applicable strategy for *page*, if any."""
        for strategy in self._strategies:
            if strategy.is_applicable(page):
                return strategy
        return None

    def detect(
        self,
        page: PageContext,
        exclusions: list[BBox] | None = None,
    ) -> list[DetectedComponent]:
        """Run the first applicable strategy.

        A strategy that raises is logged and treated as producing nothing, so a
        single failing detector cannot abort the whole page.
        """
        strategy = self.select_strategy(page)
        if strategy is None:
            logger.debug(
                "%s: no applicable strategy for page %d (text_layer=%s)",
                type(self).__name__, page.page_number, page.has_text_layer,
            )
            return []

        try:
            found = strategy.detect(page, exclusions or [])
        except Exception:
            logger.exception(
                "%s: strategy %r failed on page %d",
                type(self).__name__, strategy.name, page.page_number,
            )
            return []

        logger.debug(
            "%s: strategy %r found %d component(s) on page %d",
            type(self).__name__, strategy.name, len(found), page.page_number,
        )
        return found


class CompositeDetector(Detector):
    """A detector assembled from strategies without a dedicated subclass."""

    def __init__(self, component_type: str, strategies: Iterable[DetectionStrategy]) -> None:
        self.component_type = component_type
        super().__init__(strategies)


class DetectorRegistry:
    """Factory + registry for detectors, keyed by component type.

    Keeps the pipeline free of hard-coded detector imports: it asks the registry
    for what is registered and runs it in the configured order.
    """

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], Detector]] = {}

    def register(self, component_type: str) -> Callable[[type[Detector]], type[Detector]]:
        """Class decorator registering a detector for *component_type*."""
        def decorator(cls: type[Detector]) -> type[Detector]:
            self.register_factory(component_type, cls)
            return cls
        return decorator

    def register_factory(self, component_type: str, factory: Callable[[], Detector]) -> None:
        if component_type in self._factories:
            logger.debug("Replacing registered detector for %s", component_type)
        self._factories[component_type] = factory

    def create(self, component_type: str) -> Detector:
        try:
            return self._factories[component_type]()
        except KeyError:
            raise DetectionError(
                f"No detector registered for component type {component_type!r}. "
                f"Registered: {sorted(self._factories)}"
            ) from None

    def create_all(self, component_types: Iterable[str]) -> dict[str, Detector]:
        return {ct: self.create(ct) for ct in component_types}

    def is_registered(self, component_type: str) -> bool:
        return component_type in self._factories

    @property
    def registered_types(self) -> list[str]:
        return sorted(self._factories)


#: Process-wide registry. Detector modules register themselves on import.
registry = DetectorRegistry()
