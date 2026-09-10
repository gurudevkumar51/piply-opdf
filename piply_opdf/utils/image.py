"""Image utility helpers — thin, reusable wrappers around OpenCV + NumPy."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Type alias for OpenCV images (numpy arrays)
CVImage = np.ndarray


# ── Loading / Saving ──────────────────────────────────────────────────────────


def load_image(path: str | Path, flags: int = cv2.IMREAD_COLOR) -> CVImage:
    """Load an image from disk; raises FileNotFoundError if missing."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    img = cv2.imread(str(path), flags)
    if img is None:
        raise ValueError(f"cv2.imread failed to decode: {path}")
    return img


def save_image(image: CVImage, path: str | Path, quality: int = 95) -> Path:
    """Save a CV image to disk; creates parent directories as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix.lower()
    params: list[int] = []
    if ext in (".jpg", ".jpeg"):
        params = [cv2.IMWRITE_JPEG_QUALITY, quality]
    elif ext == ".png":
        # PNG compression 0-9 (mapped from 0–100 quality scale)
        compress = max(0, min(9, 9 - int(quality * 9 / 100)))
        params = [cv2.IMWRITE_PNG_COMPRESSION, compress]
    cv2.imwrite(str(path), image, params)
    return path


def pil_to_cv(pil_image: Image.Image) -> CVImage:
    """Convert a PIL Image to an OpenCV BGR array."""
    rgb = np.array(pil_image.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def cv_to_pil(image: CVImage) -> Image.Image:
    """Convert an OpenCV BGR array to a PIL Image."""
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


# ── Colour Space Helpers ──────────────────────────────────────────────────────


def to_gray(image: CVImage) -> CVImage:
    """Convert BGR or BGRA image to single-channel grayscale."""
    if len(image.shape) == 2:
        return image  # already gray
    if image.shape[2] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def to_bgr(image: CVImage) -> CVImage:
    """Ensure image is 3-channel BGR."""
    if len(image.shape) == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return image


# ── Quality Metrics ───────────────────────────────────────────────────────────


def laplacian_variance(gray: CVImage) -> float:
    """
    Sharpness estimate via Laplacian variance.

    Higher → sharper.  Values < 100 typically indicate blur.
    """
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def rms_contrast(gray: CVImage) -> float:
    """
    Root-mean-square contrast (0–255 scale).

    Lower values indicate a low-contrast image.
    """
    mean, std = cv2.meanStdDev(gray)
    return float(std[0][0])


def estimate_noise(gray: CVImage) -> float:
    """
    Estimate image noise level (0–1 scale).

    Uses the difference between the image and a Gaussian-blurred version.
    """
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    diff = cv2.absdiff(gray, blurred).astype(np.float32)
    noise = float(np.mean(diff)) / 255.0
    return noise


def estimate_skew_angle(gray: CVImage) -> float:
    """
    Estimate document skew angle in degrees using HoughLinesP and Projection Optimization.
    Returns a value in [-45, 45].
    """
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # Use HoughLinesP for better line segment detection on tables
    lines = cv2.HoughLinesP(thresh, 1, np.pi / 180, threshold=100, minLineLength=50, maxLineGap=10)
    
    if lines is None:
        return 0.0
        
    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        # Keep near horizontal lines
        if abs(angle) < 45:
            angles.append(angle)
            
    if not angles:
        return 0.0
        
    median_angle = float(np.median(angles))
    
    # Fine-tune via Projection Optimization
    # Search around the median_angle +/- 2 degrees in 0.1 steps
    best_angle = median_angle
    max_var = 0.0
    
    for a in np.arange(median_angle - 2.0, median_angle + 2.1, 0.2):
        # Rotate thresholded image
        h, w = thresh.shape
        M = cv2.getRotationMatrix2D((w // 2, h // 2), a, 1.0)
        rotated = cv2.warpAffine(thresh, M, (w, h), flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        # Calculate horizontal projection variance
        proj = np.sum(rotated, axis=1)
        var = np.var(proj)
        if var > max_var:
            max_var = var
            best_angle = a
            
    return float(best_angle)


def compute_histogram(gray: CVImage, bins: int = 256) -> np.ndarray:
    """Return a normalised intensity histogram as a 1-D float array."""
    hist = cv2.calcHist([gray], [0], None, [bins], [0, 256])
    hist = hist.flatten().astype(np.float32)
    total = hist.sum()
    if total > 0:
        hist /= total
    return hist


# ── Geometric Helpers ─────────────────────────────────────────────────────────


def crop_region(
    image: CVImage,
    x: int,
    y: int,
    width: int,
    height: int,
    padding: int = 0,
) -> CVImage:
    """
    Crop a rectangular region from an image.

    An optional *padding* (pixels) is added on each side, clamped to image
    boundaries.
    """
    h, w = image.shape[:2]
    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(w, x + width + padding)
    y2 = min(h, y + height + padding)
    return image[y1:y2, x1:x2].copy()


def rotate_image(image: CVImage, angle: float, *, expand: bool = True) -> CVImage:
    """
    Rotate an image by *angle* degrees around its centre.

    This is the single rotation primitive for the package; deskewing builds on
    it rather than reimplementing the warp.

    Parameters
    ----------
    expand:
        When True the canvas grows so corners are not clipped. When False the
        original dimensions are kept and corners are cropped.

        Deskewing passes ``expand=False``: every zone downstream is a *ratio of
        page height* — the header band is the top 12%, the footer the bottom
        12% — so growing the canvas adds blank margin that shifts those bands
        off the content they are meant to cover. Preserving the page frame
        matters more than preserving corners, which on a document scan are
        margin.

    Background is filled with white so new area reads as page background to
    every downstream threshold.
    """
    h, w = image.shape[:2]
    centre = (w // 2, h // 2)
    mat = cv2.getRotationMatrix2D(centre, angle, 1.0)

    new_w, new_h = w, h

    if expand:
        # Calculate new bounding dimensions to prevent clipping
        cos_a = np.abs(mat[0, 0])
        sin_a = np.abs(mat[0, 1])

        new_w = int((h * sin_a) + (w * cos_a))
        new_h = int((h * cos_a) + (w * sin_a))

        # Adjust the rotation matrix translation to centre the image in the new canvas
        mat[0, 2] += (new_w / 2) - centre[0]
        mat[1, 2] += (new_h / 2) - centre[1]

    rotated = cv2.warpAffine(
        image,
        mat,
        (new_w, new_h),
        # Cubic rather than linear: resampling a document raster softens glyph
        # edges, and thin marks — a key-value separator colon, a list bullet —
        # are exactly what the CV strategies key on. Linear interpolation was
        # measurably losing them at larger correction angles.
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255) if len(image.shape) == 3 else 255,
    )
    return rotated


# ── Drawing / Annotation ──────────────────────────────────────────────────────

_REGION_COLOURS: dict[str, tuple[int, int, int]] = {
    "header": (0, 200, 0),
    "footer": (0, 150, 255),
    "paragraph": (255, 100, 0),
    "table": (0, 0, 255),
    "cell": (200, 0, 200),
    "image": (0, 255, 255),
    "signature": (255, 0, 100),
    "key_value": (128, 128, 0),
    "default": (128, 128, 128),
}


def draw_regions(
    image: CVImage,
    regions: list[dict[str, Any]],
    thickness: int = 2,
) -> CVImage:
    """
    Draw bounding boxes for layout regions onto a copy of *image*.

    Each entry in *regions* must have: ``type``, ``bbox`` (x, y, width, height).
    """
    vis = to_bgr(image).copy()
    for region in regions:
        rtype = str(region.get("type", "default"))
        colour = _REGION_COLOURS.get(rtype, _REGION_COLOURS["default"])
        bbox = region.get("bbox", {})
        x, y, w, h = bbox.get("x", 0), bbox.get("y", 0), bbox.get("width", 0), bbox.get("height", 0)
        cv2.rectangle(vis, (x, y), (x + w, y + h), colour, thickness)
        cv2.putText(
            vis,
            rtype,
            (x, max(0, y - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            colour,
            1,
            cv2.LINE_AA,
        )
    return vis
