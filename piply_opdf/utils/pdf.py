"""PDF utility helpers — thin wrappers around PyMuPDF (fitz)."""

from __future__ import annotations

import logging
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def open_pdf(path: str | Path) -> fitz.Document:
    """Open a PDF and return the fitz Document handle."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    doc = fitz.open(str(path))
    logger.debug("Opened PDF %s — %d page(s)", path.name, doc.page_count)
    return doc


def page_count(path: str | Path) -> int:
    """Return the number of pages in a PDF without keeping the handle open."""
    with fitz.open(str(path)) as doc:
        return doc.page_count


def pdf_page_to_image(
    pdf_path: str | Path,
    page_index: int,
    dpi: int = 300,
) -> np.ndarray:
    """
    Render a PDF page to a NumPy (OpenCV-compatible) BGR array.

    Parameters
    ----------
    pdf_path:
        Path to the PDF file.
    page_index:
        0-based page index.
    dpi:
        Render resolution in dots per inch.
    """
    with fitz.open(str(pdf_path)) as doc:
        page = doc[page_index]
        mat = fitz.Matrix(dpi / 72, dpi / 72)  # 72 dpi is the PDF default
        pix = page.get_pixmap(matrix=mat, alpha=False)
        # pix.samples → bytes in RGB order
        img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )
    # Convert RGB → BGR for OpenCV
    import cv2
    if pix.n == 3:
        return cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    elif pix.n == 4:
        return cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)
    return img_array


def pdf_page_to_pil(
    pdf_path: str | Path,
    page_index: int,
    dpi: int = 300,
) -> Image.Image:
    """Render a PDF page to a PIL Image (RGB)."""
    with fitz.open(str(pdf_path)) as doc:
        page = doc[page_index]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def get_page_metadata(pdf_path: str | Path, page_index: int) -> dict:
    """Return basic metadata for a page (dimensions, rotation, dpi hint)."""
    with fitz.open(str(pdf_path)) as doc:
        page = doc[page_index]
        rect = page.rect
        return {
            "page_index": page_index,
            "page_number": page_index + 1,
            "width_pt": rect.width,
            "height_pt": rect.height,
            "rotation": page.rotation,
        }


def get_page_classification(pdf_path: str | Path, page_index: int, dpi: int = 300) -> dict:
    """Classify page as DIGITAL, SCANNED, or HYBRID and get image bounding boxes."""
    with fitz.open(str(pdf_path)) as doc:
        page = doc[page_index]
        text_len = len(page.get_text("text").strip())
        image_info = page.get_image_info()
        scale = dpi / 72.0
        
        image_bboxes = []
        for img in image_info:
            x0, y0, x1, y1 = img["bbox"]
            image_bboxes.append((int(x0 * scale), int(y0 * scale), int(x1 * scale), int(y1 * scale)))
            
        doc_type = "SCANNED"
        if text_len > 0:
            doc_type = "HYBRID" if len(image_bboxes) > 0 else "DIGITAL"
            
        return {
            "doc_type": doc_type,
            "image_bboxes": image_bboxes
        }


def iter_pages(
    pdf_path: str | Path,
    dpi: int = 300,
) -> "Generator[tuple[int, np.ndarray], None, None]":
    """
    Yield (page_index, image_array) pairs for each page in a PDF.

    Example
    -------
    >>> for idx, img in iter_pages("doc.pdf"):
    ...     process(img)
    """
    import cv2
    with fitz.open(str(pdf_path)) as doc:
        for page_index, page in enumerate(doc):
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            if pix.n == 3:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            elif pix.n == 4:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)
            yield page_index, img_array


def images_to_pdf(images: list[Image.Image], output_path: str | Path, dpi: int = 300) -> Path:
    """
    Create a PDF from a list of PIL Images.

    The first image is saved as the main page; subsequent images are appended.
    Returns the output path.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not images:
        raise ValueError("images list is empty")

    doc = fitz.open()
    for pil_img in images:
        img_bytes = pil_img.tobytes("raw", "RGB")
        w, h = pil_img.size
        page_w = w * 72 / dpi
        page_h = h * 72 / dpi
        # Insert image as a page
        page = doc.new_page(width=page_w, height=page_h)
        rect = fitz.Rect(0, 0, page_w, page_h)
        page.insert_image(rect, stream=pil_img._repr_png_() if hasattr(pil_img, "_repr_png_") else _pil_to_bytes(pil_img))

    doc.save(str(output_path))
    doc.close()
    return output_path


def _pil_to_bytes(img: Image.Image) -> bytes:
    """Serialise a PIL image to PNG bytes."""
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def save_images_as_pdf(
    images: list[np.ndarray],
    output_path: str | Path,
    dpi: int = 300,
) -> Path:
    """
    Save a list of OpenCV BGR images as a multi-page PDF.
    """
    import io
    import cv2

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()

    for bgr in images:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        h, w = bgr.shape[:2]
        page_w = w * 72 / dpi
        page_h = h * 72 / dpi
        page = doc.new_page(width=page_w, height=page_h)
        rect = fitz.Rect(0, 0, page_w, page_h)
        page.insert_image(rect, stream=png_bytes)

    doc.save(str(output_path))
    doc.close()
    return output_path
