"""
Containers: find what is inside a box by running the ordinary detectors on it.

A panel holding a signature, a stamp, two key-value pairs and a caption needs
no parser of its own. It is searched with exactly the detectors that search a
page — they are handed a cropped view and cannot tell the difference.

Two things make that work:

* :meth:`PageContext.sub_context` produces a crop whose coordinates, including
  text-layer coordinates, are relative to the crop itself;
* results are translated back to full-page coordinates afterwards.

So no detector needs to know that containers exist.
"""

from __future__ import annotations

import logging

from piply_opdf.core.segmenter import SegmentationStrategy, Segmenter, segmenter_registry
from piply_opdf.core.types import BBox, ComponentType, DetectedComponent, PageContext

logger = logging.getLogger(__name__)

__all__ = ["ContainerSegmenter", "InteriorDetectionStrategy", "INTERIOR_ORDER"]


#: Which detectors run inside a container, in order. Each passes its results to
#: the next as exclusions, so a region is claimed once.
#:
#: Deliberately *not* the full page order:
#:
#: * ``PANEL`` is excluded — a panel searching itself would find its own frame
#:   again, forever. Nested boxes are a real thing but need their own guard, so
#:   they are left for later.
#: * ``HEADER`` and ``FOOTER`` are excluded — they mean "the top and bottom
#:   bands of a *page*". Inside a box those bands are meaningless.
#: * ``TITLE`` is excluded for the same reason: prominence is judged against the
#:   page's body text, not against a caption in a box.
INTERIOR_ORDER = (
    ComponentType.TABLE,
    ComponentType.KEY_VALUE,
    ComponentType.LIST_ITEM,
    ComponentType.PARAGRAPH,
    ComponentType.UNKNOWN,      # residual sweep — claims whatever is left
)

#: Trim from the frame before searching, as a fraction of the shorter side.
#: Without it the frame's own rules sit inside the crop and are detected as
#: content — a border would come back as a line, or worse, as a table.
BORDER_INSET_RATIO = 0.02
MIN_BORDER_INSET = 4


class InteriorDetectionStrategy(SegmentationStrategy):
    """Runs the page detectors over the inside of a container."""

    name = "interior-detection"
    priority = 100

    def is_applicable(self, component: DetectedComponent, page: PageContext) -> bool:
        return (
            component.type in ComponentType.CONTAINER
            and page.image is not None
            and page.image.size > 0
        )

    def segment(
        self,
        component: DetectedComponent,
        page: PageContext,
    ) -> list[DetectedComponent]:
        # The component's bbox is in full-page coordinates; the context may
        # itself already be a crop, so convert before cropping again.
        ox, oy = page.origin
        local = BBox(
            component.bbox.x - ox, component.bbox.y - oy,
            component.bbox.width, component.bbox.height,
        )

        inset = max(
            MIN_BORDER_INSET,
            int(min(local.width, local.height) * BORDER_INSET_RATIO),
        )
        interior = page.sub_context(local, inset=inset)
        if interior is None:
            return []

        found: list[DetectedComponent] = []
        claimed: list = []

        for component_type in INTERIOR_ORDER:
            detector = self._detector_for(component_type)
            if detector is None:
                continue

            try:
                results = detector.detect(interior, list(claimed))
            except Exception:
                logger.exception(
                    "interior detection failed for %s inside %s",
                    component_type, component.id,
                )
                continue

            for child in results:
                # Back into full-page coordinates before anything else sees it.
                self._to_page(child, interior)
                child.id = f"{component.id}_{child.id}"
                child.metadata["inside"] = component.id
                found.append(child)
                # Exclusions are passed to the next detector, which works in
                # crop coordinates, so convert back.
                ox_i, oy_i = interior.origin
                claimed.append(
                    BBox(
                        child.bbox.x - ox_i, child.bbox.y - oy_i,
                        child.bbox.width, child.bbox.height,
                    )
                )

        found = self._drop_residual_overlaps(found)
        found.sort(key=lambda c: (c.bbox.y, c.bbox.x))
        return found

    @staticmethod
    def _drop_residual_overlaps(
        components: list[DetectedComponent],
        threshold: float = 0.45,
    ) -> list[DetectedComponent]:
        """Remove residual regions that sit on top of a recognised one.

        The residual sweep exists so nothing is lost, not to compete for space
        already claimed. It masks out exclusions before looking, but a detected
        region's box can be tighter than the ink it covers — a key-value line
        box is thinner than the glyphs' full height — so a few stray marks
        survive and come back as handwriting or unknown, overlapping the very
        component they belong to.

        Dropping those keeps one region per piece of content. Anything genuinely
        unclaimed is still kept.
        """
        # A text line's box is tighter than the ink it covers — ascenders and
        # descenders fall outside it — so compare against a slightly grown
        # version, otherwise a stray mark from the same word looks unclaimed.
        recognised = [
            c.bbox.padded(max(4, int(c.bbox.height * 0.6)))
            for c in components
            if c.type not in ComponentType.GRAPHIC
        ]
        if not recognised:
            return components

        return [
            c for c in components
            if c.type not in ComponentType.GRAPHIC
            or c.bbox.covered_fraction(recognised) <= threshold
        ]

    @staticmethod
    def _to_page(component: DetectedComponent, context: PageContext) -> None:
        """Move a component and everything it carries into page coordinates.

        Three places hold geometry, and all three must move together:

        * ``bbox``;
        * any children a detector already attached;
        * **geometry recorded in metadata** — the key-value detectors store
          ``key_bbox`` / ``value_bbox`` / ``separator_bbox`` there for the
          segmenter to use later. Missing these leaves a component whose own
          box is correct while its parts point somewhere else entirely.
        """
        component.bbox = context.to_page(component.bbox)

        for key, value in list(component.metadata.items()):
            if not key.endswith("_bbox"):
                continue
            box = BBox.from_any(value)
            if box is not None:
                component.metadata[key] = list(context.to_page(box).to_tuple())

        for child in component.children:
            InteriorDetectionStrategy._to_page(child, context)

    @staticmethod
    def _detector_for(component_type: str):
        from piply_opdf.core.detector import registry

        if not registry.is_registered(component_type):
            return None
        try:
            return registry.create(component_type)
        except Exception:
            logger.exception("could not build detector for %s", component_type)
            return None


@segmenter_registry.register(ComponentType.PANEL)
class ContainerSegmenter(Segmenter):
    """A container's children are whatever the detectors find inside it."""

    component_type = ComponentType.PANEL
    produces = "ANY"

    def default_strategies(self) -> list[SegmentationStrategy]:
        return [InteriorDetectionStrategy()]
