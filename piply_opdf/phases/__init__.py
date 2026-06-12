"""Phases package init."""

from piply_opdf.phases.phase1_assess import DocumentAssessor
from piply_opdf.phases.phase2_enhance import DocumentEnhancer

__all__ = [
    "DocumentAssessor",
    "DocumentEnhancer",
]
