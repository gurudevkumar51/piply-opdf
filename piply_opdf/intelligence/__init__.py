"""
Template and layout intelligence — recognising a page, and what should be on it.

The subsystem the plan calls Phase T. Four parts were designed; one is built:

``LayoutPredictor``  ✅
    Compares one region against what people have confirmed before, and reports
    what they called regions like it. Feeds the `knowledge_agreement`
    confidence signal — evidence, never a decision.

``FingerprintMatcher``  ⬜
    Six layered signals describing a whole page, so one page can be recognised
    as the same *family* as another.

``TemplateMatcher``  ⬜ *and deliberately not built yet*
    Deciding which family a page belongs to, and applying that family's layout.
    The plan keeps this switched off until Phase E can report a **false match
    rate**, and the reason is worth restating: a system that says `unknown` is
    safe, while one that says *95% match* and is wrong applies the wrong layout
    to a real document and nobody looks again.

``GeometryVerifier``  ⬜
    Checking an applied expectation against the actual ink. The rule it exists
    to enforce — *a template match can never override geometry verification* —
    is why the matcher waits for it.

The ordering is not caution for its own sake. It is the agreed sequence:
layout knowledge first, then human corrections accumulating examples, then
matching tuned against real data. The examples arrive from ordinary review;
nothing has to be collected specially.
"""

from .predictor import GROUP_WEIGHTS, LayoutPredictor, Match, similarity

__all__ = ["LayoutPredictor", "Match", "similarity", "GROUP_WEIGHTS"]
