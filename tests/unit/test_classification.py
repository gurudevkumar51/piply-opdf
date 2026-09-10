"""
Content classification and the residual (graphic) sweep.

The classifier decides what a non-prose region is: printed text, signature,
handwriting, logo, photograph, or — deliberately — nothing it can name.

Samples are generated with variation in size, stroke weight and colour so the
tests assert on *class separation*, not on one hand-picked image. The
thresholds in ``classification.content`` were placed in the gaps between the
per-class ranges these generators produce.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from piply_opdf.classification import classify, measure
from piply_opdf.classification.content import RegionFeatures
from piply_opdf.core.types import ComponentType

SAMPLES_PER_CLASS = 12


def _canvas(width: int, height: int) -> np.ndarray:
    return np.full((height, width, 3), 255, np.uint8)


def make_printed(i: int) -> np.ndarray:
    """Uniform machine text: even stroke width, many small components."""
    width, height = 400 + i * 40, 60 + i * 8
    image = _canvas(width, height)
    scale = 0.6 + 0.12 * (i % 4)
    for row in range(max(1, height // 28)):
        cv2.putText(
            image, "The quick brown fox jumps", (6, 22 + row * 26),
            cv2.FONT_HERSHEY_SIMPLEX, scale, (20, 20, 20), 1, cv2.LINE_AA,
        )
    return image


def make_signature(i: int) -> np.ndarray:
    """A few long, connected, sweeping strokes."""
    rng = np.random.default_rng(100 + i)
    width, height = 300 + i * 30, 90 + i * 6
    image = _canvas(width, height)
    points = [
        (
            int(10 + t * (width - 20) / 120),
            int(height / 2 + (height / 3) * np.sin(t / (6 + i % 5)) + rng.normal(0, 2)),
        )
        for t in range(120)
    ]
    for a, b in zip(points, points[1:]):
        cv2.line(image, a, b, (15, 15, 15), max(1, 1 + (i % 3)), cv2.LINE_AA)
    return image


def make_handwriting(i: int) -> np.ndarray:
    """Many short irregular strokes of varying weight."""
    rng = np.random.default_rng(200 + i)
    width, height = 320 + i * 25, 80 + i * 5
    image = _canvas(width, height)
    for word in range(4 + i % 3):
        x0 = 12 + word * (width // (5 + i % 3))
        for t in range(30):
            x = int(x0 + t * 1.4)
            y = int(height / 2 + 12 * np.sin(t / 3.0 + word) + rng.normal(0, 3))
            cv2.circle(image, (x, y), max(1, 1 + (t % 3)), (20, 20, 20), -1)
    return image


def make_logo(i: int) -> np.ndarray:
    """A designed mark — several colours. Rule 2's positive case."""
    width, height = 160 + i * 12, 120 + i * 10
    image = _canvas(width, height)
    first = [(200, 40, 30), (30, 140, 220), (40, 170, 80), (180, 60, 190)][i % 4]
    second = [(30, 140, 220), (200, 40, 30), (180, 60, 190), (40, 170, 80)][i % 4]
    cv2.rectangle(image, (8, 8), (width // 2, height - 8), first, -1)
    cv2.rectangle(image, (width // 2, 8), (width - 8, height - 8), second, -1)
    cv2.circle(image, (width // 2, height // 2), min(width, height) // 5, (255, 255, 255), -1)
    return image


def make_stamp(i: int) -> np.ndarray:
    """A rubber seal — one ink colour, edges broken by uneven pressure."""
    rng = np.random.default_rng(400 + i)
    width, height = 170 + i * 10, 170 + i * 10
    image = _canvas(width, height)
    ink = [(150, 40, 40), (140, 30, 120), (40, 40, 150)][i % 3]
    centre, radius = (width // 2, height // 2), min(width, height) // 2 - 8

    for angle in range(0, 360, 4):
        if rng.random() < 0.18:          # a real seal prints unevenly
            continue
        a = (int(centre[0] + radius * np.cos(np.radians(angle))),
             int(centre[1] + radius * np.sin(np.radians(angle))))
        b = (int(centre[0] + radius * np.cos(np.radians(angle + 4))),
             int(centre[1] + radius * np.sin(np.radians(angle + 4))))
        cv2.line(image, a, b, ink, 3)

    cv2.putText(image, "APPROVED", (int(width * 0.14), int(height * 0.54)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45 + 0.03 * (i % 3), ink, 2, cv2.LINE_AA)
    return image


def make_photo(i: int) -> np.ndarray:
    """Smooth, colour-rich, fully covered — a photograph of anything."""
    rng = np.random.default_rng(300 + i)
    width, height = 200 + i * 20, 160 + i * 15
    image = (rng.random((height, width, 3)) * 255).astype(np.uint8)
    image = cv2.GaussianBlur(image, (11, 11), 0)
    gradient = np.linspace(0, 120, width)[None, :, None]
    return np.clip(image * 0.6 + gradient, 0, 255).astype(np.uint8)


def make_scanned_printed(i: int) -> np.ndarray:
    """Printed text as an office scanner produces it.

    The clean generator above is not representative: a real scan adds noise,
    blur and threshold ragging, which pushes stroke width variation from 0.09
    up to 0.34-0.40 — indistinguishable from handwriting's 0.43. What survives
    is the baseline: the glyphs still sit on a ruled line.
    """
    rng = np.random.default_rng(500 + i)
    image = make_printed(i).astype(float)
    image = cv2.GaussianBlur(image, (3, 3), 0.8)
    image = np.clip(image + rng.normal(0, 18, image.shape), 0, 255).astype(np.uint8)
    # Scanners clean up after themselves. Without this the noise leaves loose
    # specks that no real scan produces, and the sample stops standing in for
    # the thing it is meant to represent.
    return cv2.medianBlur(image, 3)


def make_coloured_text(i: int) -> np.ndarray:
    """Printed text that happens to be coloured — a hyperlink, a shaded header.

    Real cases from the sample documents: blue hyperlink text on a CV, and
    column headings printed over a yellow highlight band.
    """
    width, height = 420 + i * 30, 64
    ink = [(200, 60, 30), (30, 60, 200), (140, 40, 140)][i % 3]
    background = [(255, 255, 255), (60, 240, 250), (255, 255, 255)][i % 3]
    image = np.full((height, width, 3), background, np.uint8)
    for row in range(2):
        cv2.putText(image, "Closing Balance Credit", (6, 26 + row * 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.62, ink, 1, cv2.LINE_AA)
    return image


GENERATORS = {
    ComponentType.PARAGRAPH: make_printed,
    ComponentType.SIGNATURE: make_signature,
    ComponentType.HANDWRITING: make_handwriting,
    ComponentType.LOGO: make_logo,
    ComponentType.STAMP: make_stamp,
    ComponentType.IMAGE: make_photo,
}


# ── measurement ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("expected", list(GENERATORS))
def test_measure_returns_features(expected):
    features = measure(GENERATORS[expected](0))
    assert features is not None
    assert 0.0 <= features.ink_ratio <= 1.0
    assert 0.0 <= features.saturation <= 1.0
    assert features.aspect_ratio > 0


@pytest.mark.parametrize("crop", [None, np.zeros((0, 0, 3), np.uint8), np.zeros((2, 2, 3), np.uint8)])
def test_measure_rejects_degenerate_input(crop):
    assert measure(crop) is None


def test_classify_handles_unmeasurable_region():
    verdict = classify(None)
    assert verdict.type == ComponentType.UNKNOWN
    assert verdict.confidence == 0.0


# ── classification ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("expected", list(GENERATORS))
def test_each_class_is_recognised(expected):
    generator = GENERATORS[expected]
    hits = [classify(measure(generator(i))).type for i in range(SAMPLES_PER_CLASS)]
    correct = sum(1 for h in hits if h == expected)
    assert correct == SAMPLES_PER_CLASS, f"{expected}: got {set(hits)}"


def test_rule_2_colour_count_separates_stamp_from_logo():
    """Rule 2. A stamp deposits one ink; a logo is normally polychrome."""
    stamps = [measure(make_stamp(i)).colour_clusters for i in range(SAMPLES_PER_CLASS)]
    logos = [measure(make_logo(i)).colour_clusters for i in range(SAMPLES_PER_CLASS)]
    assert set(stamps) == {1}, f"stamps should show one colour, got {set(stamps)}"
    assert min(logos) >= 2, f"logos should show two or more, got {set(logos)}"


def test_rule_3_word_groups_separate_signature_from_handwriting():
    """Rule 3. A signature is a name; handwriting is a sentence."""
    signatures = [measure(make_signature(i)).word_groups for i in range(SAMPLES_PER_CLASS)]
    assert max(signatures) <= 2, f"a signature is 1-2 groups, got {set(signatures)}"


def test_signature_and_handwriting_are_distinguished():
    """Component density backs Rule 3 up.

    Words written close together can merge into one group, so the count alone
    is not enough. A signature is a few long connected strokes; handwriting is
    many short ones, and that gap is wide.
    """
    signatures = [measure(make_signature(i)).component_density for i in range(SAMPLES_PER_CLASS)]
    handwriting = [measure(make_handwriting(i)).component_density for i in range(SAMPLES_PER_CLASS)]
    assert max(signatures) < min(handwriting), (
        f"densities overlap: signature<={max(signatures):.0f} handwriting>={min(handwriting):.0f}"
    )


def test_near_tie_reports_a_choice_rather_than_refusing():
    """R13. A monochrome solid mark could be either.

    Rather than answering UNKNOWN — an open question for the operator — the
    likelier type is reported with the alternative recorded, so the choice is
    one click.
    """
    mark = _canvas(160, 120)
    cv2.rectangle(mark, (10, 10), (150, 110), (150, 40, 40), -1)

    verdict = classify(measure(mark))

    assert verdict.type == ComponentType.LOGO
    assert verdict.confidence < 0.65, "a near-tie must not look confident"
    assert [c["type"] for c in verdict.candidates] == [
        ComponentType.LOGO, ComponentType.STAMP,
    ]


def test_scanned_printed_text_is_not_handwriting():
    """Found on `Sbizhub_C2219080509040.pdf`: a whole bank statement read as
    handwriting.

    Scanning ruins stroke uniformity — the one measurement the printed-text
    rule relied on. Every value on the page came back HANDWRITING, so a fully
    typed document would have gone to a person as if it were hand-filled.
    """
    hits = [classify(measure(make_scanned_printed(i))).type for i in range(SAMPLES_PER_CLASS)]
    assert all(h == ComponentType.PARAGRAPH for h in hits), f"got {set(hits)}"


def test_coloured_text_is_text_not_a_mark():
    """Found on `sample11.pdf` and `Sbizhub_C2219080509040.pdf`.

    Blue hyperlinks came back STAMP and headings on a yellow band came back
    LOGO, because the colour rules ran before anything asked whether the region
    was text. Colour says nothing about whether something is writing.
    """
    for i in range(6):
        verdict = classify(measure(make_coloured_text(i)))
        assert verdict.type == ComponentType.PARAGRAPH, f"variant {i} → {verdict.type}"


def test_baseline_alignment_separates_print_from_handwriting_on_scans():
    """The measurement that replaces stroke width once a scan is involved."""
    printed = [measure(make_scanned_printed(i)).baseline_scatter for i in range(SAMPLES_PER_CLASS)]
    hand = [measure(make_handwriting(i)).baseline_scatter for i in range(SAMPLES_PER_CLASS)]

    printed = [v for v in printed if v >= 0]
    hand = [v for v in hand if v >= 0]
    assert printed and hand
    assert max(printed) < min(hand), (
        f"baselines overlap: print<={max(printed):.3f} hand>={min(hand):.3f}"
    )


def test_the_old_stroke_width_threshold_rejects_scanned_print():
    """Records *why* the baseline measurement had to be added.

    Stroke width is not useless — scanned print reaches 0.396 and handwriting
    starts at 0.43, so a gap does exist. The bug was the *threshold*: 0.20,
    calibrated on clean generated text measuring 0.09. No real scan has ever
    met it, so every scanned page fell through to the handwriting rule.

    The margin between the two classes is thin, which is why the classifier
    requires baseline alignment as well rather than leaning on this alone.
    """
    printed = [measure(make_scanned_printed(i)).stroke_width_cv for i in range(SAMPLES_PER_CLASS)]
    hand = [measure(make_handwriting(i)).stroke_width_cv for i in range(SAMPLES_PER_CLASS)]

    assert min(printed) > 0.20, "scanned print would pass the old threshold"
    assert max(printed) < min(hand), "the classes should still be ordered"
    assert min(hand) - max(printed) < 0.10, (
        "margin is wide enough to drop the baseline check — revisit the design"
    )


def test_marks_are_not_stolen_by_the_text_rule():
    """Why it is safe to ask "is this text?" before asking about colour.

    Density alone does not protect them — a fragmented stamp reaches 519,
    above the 400 text floor. What keeps marks out of the text rule is stroke
    and baseline behaviour: a seal has broken, uneven strokes and no ruled
    line. This asserts the outcome rather than one measurement, because the
    outcome is what matters and the density argument is not sufficient.
    """
    for generator, expected in (
        (make_logo, ComponentType.LOGO),
        (make_stamp, ComponentType.STAMP),
        (make_photo, ComponentType.IMAGE),
        (make_signature, ComponentType.SIGNATURE),
    ):
        hits = [classify(measure(generator(i))).type for i in range(SAMPLES_PER_CLASS)]
        assert all(h == expected for h in hits), f"{generator.__name__}: {set(hits)}"


def make_rule(i: int) -> np.ndarray:
    """A horizontal divider, as drawn on almost every business document."""
    width, height = 1200 + i * 300, 20 + (i % 3) * 8
    image = _canvas(width, height)
    thickness = 2 + (i % 3)
    y = height // 2
    cv2.line(image, (4, y), (width - 4, y), (30, 30, 30), thickness)
    return image


@pytest.mark.parametrize("i", range(6))
def test_a_ruled_line_is_a_separator_not_a_signature(i):
    """Found on `OD330106520353075100.pdf` and `PolicyStatus_885472060_.pdf`.

    A 2386x27 divider satisfied every signature condition — sparse ink, few
    pieces, one word-group — so documents were reporting signatures they did
    not contain. Nothing in the vocabulary described a ruled line, so there was
    nowhere else for it to go.
    """
    verdict = classify(measure(make_rule(i)))
    assert verdict.type == ComponentType.SEPARATOR, f"variant {i} → {verdict.type}"


def test_a_wide_line_of_prose_is_not_mistaken_for_a_rule():
    """A single line of text is also long and thin — it must stay text.

    This is why the separator rule is asked *after* the text rule rather than
    before it.
    """
    image = _canvas(1600, 60)
    cv2.putText(image, "Regd. office: Consulting Rooms Private Limited, New Delhi",
                (8, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20, 20, 20), 2, cv2.LINE_AA)
    assert classify(measure(image)).type == ComponentType.PARAGRAPH


def test_separator_is_in_the_vocabulary():
    assert ComponentType.SEPARATOR in ComponentType.ALL
    assert ComponentType.SEPARATOR in ComponentType.GRAPHIC
    assert ComponentType.SEPARATOR not in ComponentType.TEXTUAL


def test_a_pen_like_single_ink_mark_offers_signature_as_an_alternative():
    """Found on `OD330106520353075100.pdf`: a real signature reported STAMP.

    A signature and a seal are both one ink, both broken, both compact — the
    real signature measured density 133 against a generated stamp's 137. Rather
    than answer confidently, the near-tie carries its alternative so the
    operator settles it in one click (R13).

    Built from the values actually measured on that signature rather than from
    a drawing, because a hand-drawn stand-in would only prove that the drawing
    matched the threshold.
    """
    real_signature = RegionFeatures(
        ink_ratio=0.068, component_density=133.0, component_area_cv=1.38,
        stroke_width_cv=0.463, saturation=0.04, colour_richness=0.070,
        edge_density=0.05, aspect_ratio=329 / 137, row_coverage=0.83,
        colour_clusters=1, word_groups=1, baseline_scatter=-1.0,
    )

    verdict = classify(real_signature)

    assert ComponentType.SIGNATURE in [c["type"] for c in verdict.candidates], (
        f"{verdict.type} at {verdict.confidence} with {verdict.candidates}"
    )
    assert verdict.confidence < 0.65, "a near-tie must not look confident"


def test_a_clean_seal_is_still_reported_confidently():
    """The alternative must not be offered for every stamp, or it means nothing."""
    for i in range(SAMPLES_PER_CLASS):
        verdict = classify(measure(make_stamp(i)))
        assert verdict.type == ComponentType.STAMP
        assert verdict.candidates == [], f"sample {i} hedged: {verdict.candidates}"


def test_confident_results_carry_no_candidates():
    """Candidates mean "we could not choose" — they must not appear otherwise."""
    for generator in (make_printed, make_photo, make_handwriting):
        assert classify(measure(generator(0))).candidates == []


def test_logo_saturation_separates_from_everything_else():
    logo_saturation = min(measure(make_logo(i)).saturation for i in range(SAMPLES_PER_CLASS))
    others = [
        measure(generator(i)).saturation
        for component_type, generator in GENERATORS.items()
        if component_type != ComponentType.LOGO
        for i in range(SAMPLES_PER_CLASS)
    ]
    assert logo_saturation > max(others)


def test_blank_region_is_not_forced_into_a_class():
    """An empty crop must not be confidently labelled anything."""
    blank = _canvas(200, 80)
    verdict = classify(measure(blank))
    assert verdict.type == ComponentType.UNKNOWN
    assert verdict.confidence <= 0.35


def test_unclassifiable_noise_falls_through_to_unknown():
    """Sparse random specks match no rule, so they land in the residual bucket.

    This is the guarantee behind the UNKNOWN type: content that cannot be named
    is still captured rather than dropped.
    """
    rng = np.random.default_rng(999)
    image = _canvas(300, 200)
    for _ in range(12):
        x, y = int(rng.integers(10, 290)), int(rng.integers(10, 190))
        cv2.circle(image, (x, y), 2, (30, 30, 30), -1)
    assert classify(measure(image)).type == ComponentType.UNKNOWN


# ── type vocabulary ──────────────────────────────────────────────────────────

def test_graphic_types_include_unknown():
    assert ComponentType.UNKNOWN in ComponentType.GRAPHIC


def test_textual_and_graphic_are_disjoint():
    assert not set(ComponentType.TEXTUAL) & set(ComponentType.GRAPHIC)


@pytest.mark.parametrize(
    "component_type",
    [ComponentType.SIGNATURE, ComponentType.HANDWRITING, ComponentType.LOGO,
     ComponentType.STAMP, ComponentType.IMAGE, ComponentType.UNKNOWN],
)
def test_new_types_are_registered_in_vocabulary(component_type):
    assert component_type in ComponentType.ALL


# ── the residual sweep's handling of text ────────────────────────────────────

def test_missed_text_is_reported_as_text_not_as_unknown(tmp_path):
    """Found on `Sbizhub_C2219080509040.pdf`: a whole bank statement as UNKNOWN.

    Reaching the residual sweep means the text detectors missed a region, not
    that it stopped being text. The sweep used to rewrite any text verdict to
    UNKNOWN, which put every value on that page into the "nobody knows what
    this is" bin. It should say text, and ask for OCR.
    """
    import cv2 as _cv2

    from piply_opdf.core.types import PageContext
    from piply_opdf.detectors.graphic.cv_strategy import CvGraphicStrategy

    page_image = np.full((1200, 1000, 3), 255, np.uint8)
    for row in range(6):
        _cv2.putText(page_image, "Closing Balance 200000", (80, 200 + row * 90),
                     _cv2.FONT_HERSHEY_SIMPLEX, 1.1, (25, 25, 25), 2, _cv2.LINE_AA)

    path = tmp_path / "page.png"
    _cv2.imwrite(str(path), page_image)
    page = PageContext(page_number=1, source_path=path, image=page_image, dpi=300)

    found = CvGraphicStrategy().detect(page, [])

    assert found, "the sweep should claim the unaccounted text"
    text_units = [c for c in found if c.type == ComponentType.SENTENCE]
    assert text_units, f"got {[c.type for c in found]}"
    assert all(c.metadata.get("needs_ocr") for c in text_units), "text must be sent for reading"
    assert all(c.confidence <= 0.5 for c in text_units), (
        "geometry was never confirmed by a text detector, so confidence stays low"
    )


def test_a_real_graphic_still_reports_as_a_graphic(tmp_path):
    """The change must not turn genuine marks into text."""
    import cv2 as _cv2

    from piply_opdf.core.types import PageContext
    from piply_opdf.detectors.graphic.cv_strategy import CvGraphicStrategy

    page_image = np.full((1200, 1000, 3), 255, np.uint8)
    logo = make_logo(3)
    page_image[120:120 + logo.shape[0], 120:120 + logo.shape[1]] = logo

    path = tmp_path / "page.png"
    _cv2.imwrite(str(path), page_image)
    page = PageContext(page_number=1, source_path=path, image=page_image, dpi=300)

    found = CvGraphicStrategy().detect(page, [])
    assert found
    assert any(c.type in ComponentType.GRAPHIC for c in found), [c.type for c in found]


def test_a_page_sized_region_is_not_a_mark(tmp_path):
    """Found on `sample-img1.png`, `sample.pdf` and `sample6.pdf`.

    A signature, a stamp and a logo are marks — small things placed on a page.
    Nothing enforced that, so a whole revenue chart came back SIGNATURE and a
    whole transaction table came back HANDWRITING. Measured across the corpus,
    genuine marks run 0.5-2.3% of a page against 6-45% for these.

    The classifier cannot apply this rule itself: it only ever sees the crop.
    """
    import cv2 as _cv2

    from piply_opdf.core.types import PageContext
    from piply_opdf.detectors.graphic.cv_strategy import CvGraphicStrategy

    rng = np.random.default_rng(11)
    page_image = np.full((2000, 1600, 3), 255, np.uint8)

    # A sprawling pen-like scrawl over a third of the page — the shape of the
    # chart and the empty column that were being called signatures.
    points = [(int(120 + t * 1300 / 400), int(700 + 380 * np.sin(t / 26.0) + rng.normal(0, 6)))
              for t in range(400)]
    for a, b in zip(points, points[1:]):
        _cv2.line(page_image, a, b, (20, 20, 20), 3, _cv2.LINE_AA)

    path = tmp_path / "page.png"
    _cv2.imwrite(str(path), page_image)
    page = PageContext(page_number=1, source_path=path, image=page_image, dpi=300)

    found = CvGraphicStrategy().detect(page, [])
    assert found

    page_area = 2000 * 1600
    for c in found:
        if c.bbox.area > page_area * 0.05:
            assert c.type not in ("SIGNATURE", "STAMP", "LOGO", "HANDWRITING"), (
                f"{c.type} covering {c.bbox.area / page_area:.0%} of the page"
            )


def test_a_normal_sized_mark_is_still_a_mark(tmp_path):
    """The cap must not stop real marks being found."""
    import cv2 as _cv2

    from piply_opdf.core.types import PageContext
    from piply_opdf.detectors.graphic.cv_strategy import CvGraphicStrategy

    page_image = np.full((2000, 1600, 3), 255, np.uint8)
    logo = make_logo(5)                      # ~1% of this page
    page_image[200:200 + logo.shape[0], 200:200 + logo.shape[1]] = logo

    path = tmp_path / "page.png"
    _cv2.imwrite(str(path), page_image)
    page = PageContext(page_number=1, source_path=path, image=page_image, dpi=300)

    found = CvGraphicStrategy().detect(page, [])
    assert any(c.type in ComponentType.GRAPHIC and c.type != ComponentType.UNKNOWN
               for c in found), [c.type for c in found]
