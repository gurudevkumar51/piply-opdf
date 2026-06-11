"""
Phase 4 — Layout Extraction Engine
=====================================

Converts detected layout regions into independent cropped image assets.
Each region is saved as a separate image file with full metadata.

Output structure
----------------
    layouts/
        header_001.png
        paragraph_001.png
        table_001.png
        cell_001.png
        ...

Output file
-----------
    layout_manifest.json

Public API
----------
>>> from piply_opdf.phases.phase4_extract import LayoutExtractor
>>> extractor = LayoutExtractor()
>>> manifest = extractor.extract("invoice.pdf", layout_result, output_dir="layouts/")

CLI
---
    piply-opdf extract-layouts invoice.pdf
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import cv2
import numpy as np

from piply_opdf.config import Config, get_default_config
from piply_opdf.models.layout import LayoutManifest, LayoutRegion, LayoutResult
from piply_opdf.utils.image import crop_region, save_image
from piply_opdf.utils.pdf import iter_pages

logger = logging.getLogger(__name__)


class LayoutExtractor:
    """
    Extracts cropped region images from a document based on detected layout.

    Parameters
    ----------
    config:
        Optional Config object; defaults to the package default config.
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or get_default_config()
        cfg = self.config.section("layout_extraction")

        self.region_padding: int = cfg.get("region_padding", 4)
        self.output_dir_name: str = cfg.get("output_dir", "layouts")
        self.manifest_file: str = cfg.get("manifest_file", "layout_manifest.json")
        self.render_dpi: int = self.config.get("assessment.render_dpi", 300)

    # ── Main entry point ──────────────────────────────────────────────────────

    def extract(
        self,
        source_path: str | Path,
        layout_result: LayoutResult,
        output_dir: str | Path | None = None,
    ) -> LayoutManifest:
        """
        Crop and save all layout regions from the source document.

        Parameters
        ----------
        source_path:
            Path to the PDF or image file.
        layout_result:
            Output from Phase 3 (LayoutDetector.detect).
        output_dir:
            Directory to write cropped images and manifest into.
            Defaults to ``<source_stem>_layouts/`` next to the source file.

        Returns
        -------
        LayoutManifest
            Manifest with per-region image paths and metadata.
        """
        source_path = Path(source_path)
        if output_dir is None:
            output_dir = source_path.parent / f"{source_path.stem}_{self.output_dir_name}"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Extracting %d regions to %s", len(layout_result.regions), output_dir)

        # Load all page images into a dict indexed by page_number
        page_images: dict[int, np.ndarray] = {}
        if source_path.suffix.lower() == ".pdf":
            for page_idx, img in iter_pages(source_path, dpi=self.render_dpi):
                page_images[page_idx + 1] = img
        else:
            img = cv2.imread(str(source_path))
            if img is None:
                raise ValueError(f"Cannot read image: {source_path}")
            page_images[1] = img

        # Extract each region (including children)
        extracted_regions: list[LayoutRegion] = []
        for region in layout_result.regions:
            updated = self._extract_region(region, page_images, output_dir)
            extracted_regions.append(updated)

        manifest = LayoutManifest(
            source_path=str(source_path),
            output_dir=str(output_dir),
            regions=extracted_regions,
        )

        # Save manifest
        manifest_path = output_dir / self.manifest_file
        with manifest_path.open("w", encoding="utf-8") as fh:
            fh.write(manifest.model_dump_json(indent=2))

        logger.info(
            "Extraction complete — %d regions saved, manifest at %s",
            len(extracted_regions),
            manifest_path,
        )
        return manifest

    def extract_from_image(
        self,
        image: np.ndarray,
        regions: list[LayoutRegion],
        output_dir: str | Path,
        page_number: int = 1,
    ) -> list[LayoutRegion]:
        """
        Extract regions from a single in-memory image.

        Returns updated LayoutRegion list with image_path populated.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        page_images = {page_number: image}
        return [self._extract_region(r, page_images, output_dir) for r in regions]

    # ── Region cropping ───────────────────────────────────────────────────────

    def _extract_region(
        self,
        region: LayoutRegion,
        page_images: dict[int, np.ndarray],
        output_dir: Path,
    ) -> LayoutRegion:
        """Crop one region from the appropriate page image and save it."""
        page_img = page_images.get(region.page_number)
        if page_img is None:
            logger.warning(
                "No image for page %d — skipping region %s",
                region.page_number,
                region.region_id,
            )
            return region

        bbox = region.bbox
        cropped = crop_region(
            page_img,
            x=bbox.x,
            y=bbox.y,
            width=bbox.width,
            height=bbox.height,
            padding=self.region_padding,
        )

        if cropped.size == 0:
            logger.warning("Empty crop for region %s — skipping", region.region_id)
            return region

        # Save the cropped image
        img_filename = f"{region.region_id}.png"
        img_path = output_dir / img_filename
        save_image(cropped, img_path)

        # Return a copy with image_path populated
        updated = region.model_copy(update={"image_path": str(img_path)})

        # Recursively extract child regions (e.g., cells within a table)
        if region.children:
            updated_children: list[LayoutRegion] = []
            for child in region.children:
                updated_child = self._extract_region(child, page_images, output_dir)
                updated_children.append(updated_child)
            updated = updated.model_copy(update={"children": updated_children})

        return updated

    # ── Persistence ───────────────────────────────────────────────────────────

    @staticmethod
    def load_manifest(path: str | Path) -> LayoutManifest:
        """Load a previously saved layout_manifest.json."""
        path = Path(path)
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return LayoutManifest.model_validate(data)
