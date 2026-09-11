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


#: Side of the reduced image the DCT is taken over, and of the low-frequency
#: corner kept from it. 32 and 8 are what every perceptual-hash implementation
#: uses, and 8x8 bits is 16 hex characters — short enough to index, long enough
#: that two unrelated regions do not collide.
_PHASH_IMAGE = 32
_PHASH_BITS = 8


def phash_array(image: "np.ndarray", size: int = _PHASH_BITS) -> str:
    """Perceptual hash of an array, in NumPy — no PIL, no imagehash.

    The same algorithm the library uses, which is four steps and no magic:
    shrink to 32x32, take a 2-D DCT, keep the top-left low-frequency corner,
    and set one bit per coefficient according to whether it is above the
    median. Low frequencies are the broad light-and-dark structure of the
    image, so the result survives rescaling and mild noise while still
    differing between genuinely different content.

    Written out rather than imported because it is a DCT and a comparison —
    about twenty lines — and pulling PIL into the middle of an OpenCV pipeline
    to get them costs a conversion on every call. Also part of backlog E3.

    **Not bit-identical to `imagehash.phash`.** The algorithm is the same but
    the resampling filter is not (OpenCV's area averaging against PIL's), so a
    borderline coefficient can land either side of the median and flip a bit.
    Fine for similarity, which is what layout knowledge wants; do not mix these
    values with stored `imagehash` ones and expect exact lookups to hit.

    **It measures structure, not content.** Measured on rendered text: a 2x
    rescale moves the hash 2-4 bits of 64 and noise moves it 2, but two text
    blocks with entirely different words and the same three-line arrangement
    sit only 6 bits apart, while a blank region sits 26 away. On a large crop
    the letters are high-frequency detail that the 8x8 corner throws away. Read
    a small distance as "laid out alike", never as "the same thing".
    """
    import cv2

    grey = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(grey, (_PHASH_IMAGE, _PHASH_IMAGE), interpolation=cv2.INTER_AREA)

    coefficients = _dct_2d(small.astype(np.float64))[:size, :size]
    median = np.median(coefficients)
    bits = (coefficients > median).flatten()

    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:0{size * size // 4}x}"


def _dct_2d(values: "np.ndarray") -> "np.ndarray":
    """Two-dimensional DCT-II, as two matrix multiplications.

    Unnormalised: every coefficient is off by the same constant factor, and the
    hash compares coefficients against their own median, so a shared scale
    cancels out. Skipping the normalisation keeps this to one matrix.
    """
    n = values.shape[0]
    k = np.arange(n).reshape(-1, 1)
    basis = np.cos(np.pi * (2 * np.arange(n) + 1) * k / (2 * n))
    return basis @ values @ basis.T


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
