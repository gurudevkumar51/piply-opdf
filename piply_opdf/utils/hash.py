"""Image hashing utilities — wrappers around the imagehash library."""

from __future__ import annotations

import logging
from pathlib import Path

import imagehash
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def _load_pil(image: "np.ndarray | Image.Image | str | Path") -> Image.Image:
    """Accept multiple image types and return a PIL Image."""
    if isinstance(image, Image.Image):
        return image
    if isinstance(image, (str, Path)):
        return Image.open(str(image)).convert("L")
    # Assume OpenCV BGR array
    import cv2
    if len(image.shape) == 2:
        # Already grayscale
        return Image.fromarray(image)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def phash(image: "np.ndarray | Image.Image", hash_size: int = 16) -> str:
    """
    Perceptual hash — robust to scaling, minor colour changes.

    Returns a hex string.
    """
    pil = _load_pil(image)
    h = imagehash.phash(pil, hash_size=hash_size)
    return str(h)


def dhash(image: "np.ndarray | Image.Image", hash_size: int = 16) -> str:
    """
    Difference hash — sensitive to structural differences.

    Returns a hex string.
    """
    pil = _load_pil(image)
    h = imagehash.dhash(pil, hash_size=hash_size)
    return str(h)


def ahash(image: "np.ndarray | Image.Image", hash_size: int = 16) -> str:
    """Average hash — fastest, least robust."""
    pil = _load_pil(image)
    h = imagehash.average_hash(pil, hash_size=hash_size)
    return str(h)


def hash_distance(hash_a: str, hash_b: str) -> int:
    """
    Hamming distance between two hex hash strings.

    Lower → more similar.  0 = identical.
    """
    ha = imagehash.hex_to_hash(hash_a)
    hb = imagehash.hex_to_hash(hash_b)
    return int(ha - hb)


def is_similar(
    hash_a: str,
    hash_b: str,
    max_distance: int = 10,
) -> bool:
    """Return True when two hashes are within *max_distance* of each other."""
    return hash_distance(hash_a, hash_b) <= max_distance


def compute_all_hashes(
    image: "np.ndarray | Image.Image",
) -> dict[str, str]:
    """Compute phash, dhash, and ahash in one call."""
    pil = _load_pil(image)
    return {
        "phash": str(imagehash.phash(pil)),
        "dhash": str(imagehash.dhash(pil)),
        "ahash": str(imagehash.average_hash(pil)),
    }
