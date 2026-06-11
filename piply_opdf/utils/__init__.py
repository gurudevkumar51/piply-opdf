"""Utilities package init."""

from piply_opdf.utils.hash import (
    ahash,
    compute_all_hashes,
    dhash,
    hash_distance,
    is_similar,
    phash,
)
from piply_opdf.utils.image import (
    crop_region,
    cv_to_pil,
    draw_regions,
    estimate_noise,
    estimate_skew_angle,
    laplacian_variance,
    load_image,
    pil_to_cv,
    rms_contrast,
    rotate_image,
    save_image,
    to_bgr,
    to_gray,
)
from piply_opdf.utils.pdf import (
    get_page_metadata,
    iter_pages,
    open_pdf,
    page_count,
    pdf_page_to_image,
    pdf_page_to_pil,
    save_images_as_pdf,
)

__all__ = [
    # image
    "crop_region",
    "cv_to_pil",
    "draw_regions",
    "estimate_noise",
    "estimate_skew_angle",
    "laplacian_variance",
    "load_image",
    "pil_to_cv",
    "rms_contrast",
    "rotate_image",
    "save_image",
    "to_bgr",
    "to_gray",
    # pdf
    "get_page_metadata",
    "iter_pages",
    "open_pdf",
    "page_count",
    "pdf_page_to_image",
    "pdf_page_to_pil",
    "save_images_as_pdf",
    # hash
    "ahash",
    "compute_all_hashes",
    "dhash",
    "hash_distance",
    "is_similar",
    "phash",
]
