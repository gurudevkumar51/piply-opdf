# Test Catalogue

Every test in the suite, what it protects, and what is **not** covered.

*From `pytest --collect-only`, 2026-08-17.*
**352 test functions · 567 cases · 567 passing, 0 failing.**

Targets and measurement plan: [quality.md](quality.md).

---

## Principles

**Corpora are generated in-process, not committed as fixtures.** Each suite
builds its own PDFs at several page sizes and resolutions. A test passing
against one committed file proves the code works on that file; generating
across A4/A5/Letter/Legal/landscape and 150–600 DPI proves the *logic* holds —
and catches any threshold written in fixed pixels rather than as a ratio (R5).

**Digital/scanned parity is the core assertion.** A document and its rasterised
twin are visually identical but exercise entirely different code paths — text
layer versus computer vision. Asserting they agree is the strongest single
check available, and is what exposed the original header/footer gap.

**Every bug becomes a permanent test.** Failures found on real documents are
encoded so they cannot recur.

---

## Coverage

| Suite | Functions | Cases | Area |
|-------|-----------|-------|------|
| `test_header_footer_detectors.py` | 11 | 69 | Header/footer across sizes, DPIs, variants |
| `test_layout_knowledge.py` | 61 | 61 | Describing regions, the store's refusals, the learning loop, and backups |
| `test_predictor.py` | 13 | 13 | Matching a region against what people confirmed |
| `test_confidence.py` | 55 | 55 | Evidence signals, weighting, and the review queue |
| `test_classification.py` | 31 | 51 | Rules 0–3, residual sweep, size sanity |
| `test_detector_parity.py` | 10 | 49 | Digital/scanned parity |
| `test_panel_detector.py` | 15 | 35 | Rule 1 — frames, cell counting |
| `test_container_segmentation.py` | 17 | 32 | Detection inside containers |
| `test_deskew.py` | 12 | 31 | Skew estimation and correction |
| `test_segmentation.py` | 9 | 27 | Unit hierarchy and recursion |
| `test_quality.py` | 19 | 19 | Coverage invariant and accuracy scoring |
| `test_orientation.py` | 12 | 17 | Sideways pages, and the refusals |
| `test_ocr.py` | 11 | 15 | Engine registry, availability, edge penalty |
| `test_fusion.py` | 19 | 19 | Baseline and rules combined |
| `test_baseline.py` | 15 | 15 | Layout model adapter and label mapping |
| `test_page_images.py` | 14 | 14 | Original / structural / working, and the pipeline |
| `test_phase2_enhance.py` | 13 | 15 | Enhancement operations |
| `test_form_layouts.py` | 9 | 14 | Multi-column forms, table false positives |
| `test_phase1_assess.py` | 12 | 12 | Quality assessment |
| **Total** | **352** | **567** | |

All 567 pass. Run time is about 3 minutes — most of it rendering PDFs to
images, which the tests do on purpose rather than committing fixtures.

---

## `test_header_footer_detectors.py` — 69

5 page geometries × 3 DPIs × digital/scanned, plus no-header, no-footer,
neither.

| Test | Protects |
|------|----------|
| `test_digital_pdf_uses_text_strategy` | Text layer preferred when present |
| `test_scanned_pdf_falls_back_to_cv_strategy` | **The original regression** — no text layer must not mean no detection |
| `test_header_and_footer_found_at_any_size_and_dpi` | Scale independence |
| `test_absent_header_is_not_invented` | No fabrication |
| `test_absent_footer_is_not_invented` | No fabrication |
| `test_body_only_page_yields_neither` | Pure prose yields neither |
| `test_regions_land_in_their_zone_and_inside_the_page` | Geometry sanity |
| `test_scanned_regions_are_marked_for_ocr` | CV yields geometry only |
| `test_digital_regions_carry_text_without_ocr` | Text-layer needs no OCR |
| `test_exclusions_suppress_regions` | Claimed regions not re-reported |
| `test_ordinals_are_serial_and_gap_free` | IDs contiguous |

## `test_detector_parity.py` — 49

3 page sizes × 3 DPIs, digital and rasterised twins.

| Test | Protects |
|------|----------|
| `test_strategy_selection_differs_by_input` | Correct strategy per input |
| `test_key_values_found_in_both_variants` | Key-values both paths |
| `test_list_items_found_in_both_variants` | List items both paths |
| `test_prose_found_in_both_variants` | Prose both paths |
| `test_scanned_components_are_flagged_for_ocr` | `needs_ocr` set, text empty |
| `test_digital_components_carry_text` | Text present without OCR |
| `test_key_value_records_split_geometry_without_creating_units` | **Stage boundary** — detection locates, segmentation creates |
| `test_ordinals_are_serial_and_gap_free` | Per-type ordinals |
| `test_prose_starting_with_short_words_is_not_a_list` | **False-positive guard** — "A…", "I…", "We…" at shared indent are not bullets |
| `test_exclusions_suppress_all_detectors` | Exclusions honoured uniformly |

## `test_deskew.py` — 31

| Test | Protects |
|------|----------|
| `test_estimator_recovers_known_angle` | 0.00° error across ±8° |
| `test_correction_leaves_no_residual_skew` | Correction actually straightens |
| `test_upright_page_is_left_alone` | No needless resampling |
| `test_blank_page_reports_no_angle` | No angle invented |
| `test_degenerate_input_is_safe` | None / empty handled |
| `test_estimate_is_resolution_independent` | Angle is layout, not DPI |
| `test_deskew_preserves_page_dimensions` | **Regression guard** — expanding the canvas shifts ratio-based zones off content |
| `test_rotate_image_expands_when_asked` | `expand=True` path intact |
| `test_rotate_image_fills_with_page_background` | New area reads as background |
| `test_detection_is_unaffected_by_skew` | **The requirement** — identical detection at 1.5/3/5/8/−4° |
| `test_scanned_page_records_its_correction` | Angle recorded for coordinate recovery |
| `test_pages_with_a_text_layer_are_not_deskewed` | Rotating would desynchronise raster and text layer |

## `test_segmentation.py` — 27

| Test | Protects |
|------|----------|
| `test_segmenter_registered_for_splittable_types` | Registry populated on import |
| `test_terminal_units_have_no_segmenter` | Recursion stops at CELL and WORD |
| `test_header_and_footer_split_into_words` | **Reported issue** — headers/footers reach reviewable units |
| `test_word_counts_match_between_digital_and_scanned` | Same document, same units |
| `test_paragraph_splits_to_sentences_then_words` | Full depth |
| `test_key_value_splits_into_three_roles` | KEY/SEPARATOR/VALUE ordered |
| `test_digital_key_value_units_carry_text` | Roles carry real text |
| `test_segment_tree_respects_max_depth` | Depth cap |
| `test_segment_tree_is_safe_on_unsplittable_component` | Terminal unit is a no-op |

## `test_classification.py` — 32

12 generated samples per class, varying size, stroke weight, colour. Asserts
**class separation**, not agreement with one image.

| Test | Protects |
|------|----------|
| `test_measure_returns_features` | Extraction on every class |
| `test_measure_rejects_degenerate_input` | None / empty / 2×2 |
| `test_classify_handles_unmeasurable_region` | Unmeasurable → UNKNOWN |
| `test_each_class_is_recognised` | 12/12 per class (72/72, six classes) |
| `test_rule_2_colour_count_separates_stamp_from_logo` | **Rule 2** — one ink vs many |
| `test_rule_3_word_groups_separate_signature_from_handwriting` | **Rule 3** — a name vs a sentence |
| `test_signature_and_handwriting_are_distinguished` | Component density backs Rule 3 up when words merge into one group |
| `test_near_tie_reports_a_choice_rather_than_refusing` | **R13** — a solid monochrome mark returns LOGO at low confidence with STAMP recorded, not UNKNOWN |
| `test_confident_results_carry_no_candidates` | Candidates mean "could not choose" — they must not appear otherwise |
| `test_logo_saturation_separates_from_everything_else` | Saturation isolates logos |
| `test_blank_region_is_not_forced_into_a_class` | **Caught a real bug** — blank space satisfied "sparse ink, few components" and read as SIGNATURE |
| `test_unclassifiable_noise_falls_through_to_unknown` | The residual guarantee |
| `test_graphic_types_include_unknown` | Vocabulary consistency |
| `test_textual_and_graphic_are_disjoint` | No type in both groups |
| `test_new_types_are_registered_in_vocabulary` | All types declared |

## `test_form_layouts.py` — 14

Built from real failures on `sample10.pdf`.

| Test | Protects |
|------|----------|
| `test_every_pair_in_a_two_column_form_is_found` | 8/8 pairs in a 2-column lab header |
| `test_form_block_is_not_swallowed_by_paragraph` | **"PARAGRAPH 2060"** — the block is pairs, not prose |
| `test_colon_inside_a_time_is_not_a_field_separator` | `11:58` must not split into `key="…11"` |
| `test_abbreviated_keys_are_accepted` | `Ref. Dr.` and `Req No.` are valid labels |
| `test_each_pair_segments_into_three_roles` | Roles on both paths |
| `test_words_on_one_baseline_group_into_one_line` | Form rows arrive as separate PDF blocks |
| `test_photograph_with_rectangular_edges_is_not_a_table` | **"TABLE 111 is a PAN card"** |
| `test_a_single_ink_table_is_not_rejected_as_a_stamp` | A table ruled in one ink looks like a mark — it must survive the content gate |
| `test_a_real_table_is_still_detected` | Content gate must not suppress real tables |

## `test_quality.py` — 19

The two measurable quality signals. **Coverage** asks "was anything lost?" and
needs no ground truth, which is why it is the only detection quality number
available today. **Accuracy** asks "was it given the right type?" and needs
someone to have written the answer down first.

| Test | Protects |
|------|----------|
| `test_blank_page_loses_nothing` | No ink is not a division by zero |
| `test_fully_covered_page_scores_one` | The happy path |
| `test_uncovered_ink_is_reported` | The point of the measurement — unclaimed content surfaces |
| `test_nothing_detected_means_nothing_accounted` | No free credit for detecting nothing |
| `test_children_count_towards_coverage` | A word inside a sentence covers its own area — depth is walked |
| `test_boxes_outside_the_page_are_clipped` | A component running off the page must not crash the measurement |
| `test_specks_are_not_reported_as_gaps` | Dust is below the noise floor |
| `test_a_lost_paragraph_is_reported_even_on_a_noisy_page` | The speck filter must not hide a real loss |
| `test_perfect_detection_scores_one` | Scoring baseline |
| `test_missed_region_lowers_recall_not_precision` | The two errors stay separable |
| `test_spurious_region_lowers_precision_not_recall` | Likewise |
| `test_wrong_type_counts_against_both_types` | A mislabel is two errors, not one |
| `test_poorly_placed_box_is_not_a_match` | Right type, wrong place is not a hit |
| `test_two_detections_over_one_label_count_once` | Splitting a region is one hit plus one false positive |
| `test_uncertain_labels_are_excluded` | A case a person could not decide is not evidence about the detector |
| `test_reports_merge_across_pages` | Document-level totals |
| `test_labels_load_from_json` | The label format |
| `test_empty_page_with_no_labels_is_not_a_failure` | Empty is not an error |

**A note on the speck test.** It builds a 2550×3300 page on purpose, not the
800×600 canvas the other tests use. The speck filter is a fraction of page area,
so on a small canvas a two-pixel dot is proportionally a large region — which is
not what a speck is on a 300 DPI scan. Testing it at the wrong scale tests the
wrong thing.

**The accuracy half has never run against real data.** All eleven accuracy tests
use synthetic labels written inside the test. They prove the scoring arithmetic
is right; they prove nothing about the detectors. See
[quality.md](quality.md#current-state).

## `test_phase1_assess.py` / `test_phase2_enhance.py` — 27

Quality assessment (blur, noise, contrast, skew, rating) and enhancement
operations (deskew, denoise, CLAHE, sharpen, border repair), including that
enhancement applies only when the assessment flags it.

---

## `test_layout_knowledge.py` — 61

Describing a region so it can be recognised somewhere else, and storing it so
it stays interpretable.

| Test | Protects |
|------|----------|
| `test_the_same_layout_at_a_different_dpi_describes_identically` | The whole point of ratios — a header is near the top at any resolution |
| `test_position_is_recorded_as_a_fraction_of_the_page` | Normalised geometry |
| `test_aspect_ratio_comes_from_the_box_even_with_no_image` | Describable without a crop |
| `test_page_bands_split_the_page_where_headers_and_footers_live` | Band edges at 0.15 / 0.85, not arbitrary fifths |
| `test_the_band_uses_the_centre_not_the_top_edge` | A tall block starting at the top is not a header |
| `test_neighbours_are_recorded_in_all_four_directions` | Relationships, the signal that transfers |
| `test_the_nearer_of_two_neighbours_wins` | Adjacency measured edge to edge |
| `test_a_region_that_barely_shares_a_span_is_not_a_neighbour` | **The overlap guard** — a page number in the margin is not above a table |
| `test_alignment_counts_the_siblings_sharing_an_edge` | Column edges, the header-row signal |
| `test_a_small_drift_still_counts_as_aligned` | Scanner drift absorbed |
| `test_children_are_described_against_their_siblings_not_the_page` | Cells positioned inside their table, not against a logo |
| `test_geometry_stays_relative_to_the_page_even_inside_a_container` | A cell's position stays comparable across documents |
| `test_a_crop_is_measured_by_the_same_function_the_classifier_uses` | **One extractor** — store and classifier cannot drift |
| `test_a_region_too_small_to_measure_records_absence_not_zero` | "No ink" and "nobody measured it" stay different facts |
| `test_a_record_from_an_older_extractor_is_not_current` | Version awareness |
| `test_an_unknown_action_is_refused` | Only the five actions |
| `test_the_five_actions_answer_two_separate_questions` | Finding a region and naming it are scored apart |
| `test_collapsing_the_actions_would_hide_the_difference` | Two detectors, same disagreement count, opposite problems |
| `test_a_detector_nobody_reviewed_scores_none_not_zero` | Unmeasured must not read as failed |
| `test_a_detector_cannot_teach_itself` | **The rule the store exists for** — only human sources are accepted |
| `test_knowledge_from_an_older_extractor_is_not_offered_for_matching` | Stale features never quietly answer |
| `test_the_store_says_how_much_of_itself_is_unusable` | A full-looking store that answers nothing is visible |
| `test_export_and_import_preserve_the_features_exactly` | Round trip |
| `test_the_action_log_travels_with_the_knowledge` | Separated, the counts that make a detector measurable are lost |
| `test_stale_records_are_carried_across_and_counted` | An export is a copy, not a filtered view |
| `test_an_unreadable_export_format_is_refused_not_guessed_at` | Format version checked |
| `test_reopening_the_file_keeps_what_was_written` | It is a real file other applications can read |
| `test_a_correction_teaches_the_humans_answer_not_the_detectors` | **Storing the corrected-from type would teach the error** |
| `test_a_deleted_region_teaches_the_detector_not_the_knowledge_base` | No region, nothing to learn a region from |
| `test_a_detectors_record_becomes_measurable_once_people_review` | The signal that turns itself on, with no code change |
| `test_learning_from_one_document_is_visible_to_the_next` | The compounding asset, in miniature |
| `test_a_perceptual_hash_survives_rescaling` | 2-4 bits of 64 at 2x — the property the hash exists for |
| `test_a_perceptual_hash_reads_structure_not_words` | **Measured**: different words, same layout, 6 bits apart |
| `test_hog_is_not_stored_at_all` | 1,764 floats a region is what made the text KB 41 MB |
| `test_a_backup_is_read_back_before_it_is_called_one` | A copy nobody opened is a belief |
| `test_a_corrupt_backup_is_refused_not_reported_as_success` | Finding out at restore time is the failure |
| `test_old_copies_are_pruned_but_only_after_the_new_one_verifies` | A failed backup must not delete the last good one |
| `test_restoring_refuses_to_overwrite_a_live_knowledge_base` | Restoring is the moment to be boring |

*(38 of 61 shown — the rest are the parametrised band cases and store filters.)*

---

## `test_confidence.py` — 55

Confidence derived from evidence rather than declared. Less about any
particular number than about three properties.

| Test | Protects |
|------|----------|
| `test_an_unmeasured_signal_does_not_drag_the_score_down` | **Missing is not zero** — the rule the design rests on |
| `test_a_region_nobody_could_measure_scores_zero` | Not 1.0 — nothing sayable means look at it |
| `test_signals_are_weighted_not_averaged_flat` | Track record must not carry the score |
| `test_the_same_signal_twice_is_refused` | Would silently double that signal's weight |
| `test_a_single_contradiction_sends_a_comfortable_component_to_review` | One bad signal outranks a good average |
| `test_the_score_itself_is_not_distorted_to_force_a_review` | Number and decision stay separate |
| `test_an_operator_can_ask_why` | The score can be taken apart |
| `test_unmeasured_signals_are_shown_not_hidden` | "Nothing similar seen" is itself worth knowing |
| `test_the_evidence_travels_with_the_answer` | The governing principle, as stored metadata |
| `test_a_header_in_the_middle_of_the_page_does_not` | Geometry contradicts a misplaced header |
| `test_a_header_one_band_off_is_doubted_not_condemned` | A wide top margin is not a broken detection |
| `test_a_separator_is_scored_against_being_a_line` | A rule is long and thin, by definition |
| `test_a_container_too_small_to_hold_a_cell_is_doubted` | A table has to be big enough to be one |
| `test_a_type_with_no_definitional_shape_invents_no_evidence` | A paragraph can be any shape |
| `test_the_ink_confirms_a_claim_it_matches` | Structural evidence from the image |
| `test_the_ink_contradicts_a_claim_from_the_wrong_family` | Catches a detector firing for the wrong reason |
| `test_the_ink_supports_without_confirming_inside_a_family` | The classifier has no concept of a header |
| `test_an_empty_knowledge_base_says_so_rather_than_scoring_zero` | Absent, with a reason |
| `test_a_detectors_track_record_is_read_from_the_feedback_log` | Historical reliability wired to `tally()` |
| `test_a_contradicted_region_jumps_the_queue` | Specific fault beats a smooth ranking |
| `test_capacity_is_the_control_an_operator_actually_has` | The worst twenty, not everything below 95% |
| `test_identical_literal_scores_are_reported_as_unrankable` | **The regression this replaces**, as a test |
| `test_evidence_derived_scores_separate_enough_to_rank` | The same page, now sortable |
| `test_a_cell_escaping_its_table_is_a_broken_grid` | A grid built from lines that are not there |
| `test_a_cells_shape_is_never_held_against_it` | Only containment is definitional for a grid part |
| `test_a_grid_part_with_no_parent_cannot_be_placed` | None, not zero |
| `test_the_classifier_is_not_asked_about_crops_the_size_of_a_cell` | **Measured**: it calls 80% of cells handwriting |
| `test_a_container_is_not_judged_by_the_ink_of_its_children` | A panel holding a signature is still a panel |

The fixture in this suite renders **real glyphs with `cv2.putText`**. An earlier
version drew rows of solid rectangles as a stand-in for words; the classifier
read them as `HANDWRITING`, and it was right to — uniform blocks have neither
the stroke-width variation nor the ruled baseline that printing has.

---

## `test_predictor.py` — 13

Reading the layout knowledge base back. Two properties matter more than any
number: it must recognise the same kind of region on a document it has not
seen, and it must not announce a match that is wrong.

| Test | Protects |
|------|----------|
| `test_a_second_document_of_the_same_shape_is_recognised` | **The return on review** — four regions taught from one page, recognised on the next at 97-100% |
| `test_a_mislabelled_region_is_contradicted_by_what_people_confirmed` | The case worth having: a header called `PARAGRAPH` scores 0.0 |
| `test_regions_in_different_places_are_not_confused` | Header and footer: same shape, opposite ends, 0.41 alike |
| `test_an_empty_store_says_nothing_rather_than_zero` | Unmeasured, not negative |
| `test_matching_nothing_in_a_sparse_store_is_not_evidence_against` | A thin store is not a strange region |
| `test_weak_resemblances_are_not_offered_as_matches` | A confident wrong match stops anybody looking again |
| `test_records_from_an_older_extractor_are_never_matched_against` | The predictor must not work around the version filter |
| `test_a_match_reports_which_groups_agreed` | A score nobody can take apart gets believed or ignored |
| `test_it_searches_every_type_not_just_the_claimed_one` | Filtering by the claim would hide the wrong claims |
| `test_a_group_neither_record_has_is_skipped_not_scored_zero` | Missing is not zero, here too |

---

## Not covered

| Area | Backlog |
|------|---------|
| **Measured precision/recall vs ground truth** | H1, H2 |
| **Borderless table structure** (rows and cells) | F7, F11 |
| **Table segmentation** (row/column/cell) | F8 |
| **Which way up a sideways page goes** | I17 |
| **Manifest structure and completeness** | B1, B6 |
| **Reading order** | B3 |
| **Whole `app/` layer** — routes, persistence, services | — |
| **Knowledge base** — matching, feedback, clustering | — |
| **Reconstruction / HTML** | D1–D3 |
| **Multi-page documents** | C1 |
| **Performance / large documents** | — |
| **Bad scans** — blur, bleed-through, torn edges | H6 |

Cleared since earlier revisions: `PANEL` (F1), `STAMP` (F3), `SEPARATOR`,
`HEADING`, decision rules 0–4, the `ink_accounted` invariant (H3), the OCR layer
(H7), sideways-page **detection** (I17, partly), the three-image pipeline (I21)
and the baseline model with fusion (I18).

The first row is still the one that matters. Everything else on this list is a
feature that is missing; that one is the inability to tell whether the features
that exist are **right**.

The largest gap is unchanged: **no test measures detection accuracy.** Coverage
now proves little is being *dropped*, which is real progress, but it says
nothing about whether what was kept was understood. The suite proves
consistency and prevents known regressions; correctness on unseen real
documents remains unmeasured until labelled pages exist.

---

## Real documents

The generated corpora prove the logic is consistent. They cannot show how the
system behaves on real scans, so a second harness runs a folder of real files:

```bash
python tools/run_corpus.py "path/to/documents"
```

It processes every PDF and image, records what each produced, and writes
`_corpus_results.json`.

**Current state:** 16 documents, 88 pages (10 digital, 4 scanned, 2 images).
All 16 process without error. This checks robustness and catches large
behaviour changes; it does **not** measure accuracy, because the documents are
not labelled. See [quality.md](quality.md).

Three bugs were found this way that no generated test had caught — all of them
about detectors interacting, which a single-feature test cannot show.

### Reading the pages

Coverage and counts cannot say whether a paragraph was really a paragraph.
[audit.md](audit.md) records the one check that can: every detected box drawn
onto the page and compared with the original, across all 88 pages. It found
nine defects while the suite was green.

```bash
python tools/draw_overlay.py "path/to/documents" --out=_overlay_out
```

### Coverage on real documents

The same folder can be measured for ink coverage — the share of page ink that
ended up inside some detected component:

```bash
python tools/check_coverage.py "path/to/documents"
```

It prints a line per page with the coverage figure and the largest unclaimed
region, so a loss can be located rather than merely counted.

**Result:** mean **0.9945**, worst page **0.9477**, **23 of 88 pages** below the
0.995 target. The failures cluster in three documents rather than spreading
across all of them, which means a short list of specific layouts is being
missed — not a general leak. Breakdown in
[quality.md](quality.md#where-ink-is-being-lost).

This is the first number in the project that measures the detectors against
real documents instead of against generated ones. It is deliberately not a
build gate yet: gating at today's figure would make the current losses
permanent (backlog H4).

---

## Keeping these numbers true

The count above appears in six files and used to go stale — a change added
tests, two documents were updated, the rest quietly claimed a number that had
not been right for weeks. A reader cannot tell which is current, which makes
every figure in the docs a little less believable.

So it is derived rather than typed:

```bash
python tools/sync_docs.py            # check, non-zero exit when stale
python tools/sync_docs.py --write    # update
```

It caught its own author: the function count here was hand-written as 227 and
was actually 231.

Internal links are checked the same way:

```bash
python tools/check_doc_links.py
```

## Running

```bash
conda activate py313_piply_opdf
pytest tests/unit -v
```

```bash
pytest tests/unit/test_deskew.py -v
```

> `test_phase3_layout.py`, `test_phase4_extract.py` and `test_phase5_ocr.py`
> were deleted (backlog E2). They imported `piply_opdf.phases.phase3/4/5`,
> which the restructure replaced with `detectors/` and `segmentation/`, so they
> failed at collection and blocked the whole suite. Their subject matter is
> covered by the detector and segmentation suites above — **except OCR**, which
> now lives in `piply_opdf/modules/ocr_engine.py` and has no tests (backlog H7).
