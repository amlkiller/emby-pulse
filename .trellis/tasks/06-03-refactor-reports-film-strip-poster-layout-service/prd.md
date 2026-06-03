# Refactor Reports Film Strip Poster Layout Service

## Goal

Split the large film-strip daily poster drawing layout out of `app/domains/reports/report_service.py` into a smaller reports-domain rendering module, following `docs/架构审计.md` P2 item 5. Keep `ReportGenerator` as the compatibility/public entry point and preserve current image-generation behavior.

## Requirements

* Extract only `ReportGenerator._draw_film_strip_layout()` implementation into a domain-local reports module.
* Keep `ReportGenerator._draw_film_strip_layout()` signature and return behavior as a compatibility wrapper.
* Preserve current layout behavior: canvas sizing, background gradients, theme decorations, header, TV/movie sections, poster fetching concurrency, placeholders, rankings, duration labels, footer, JPEG output format, and warning logging.
* Preserve monkeypatch compatibility for `ReportGenerator._get_best_poster()` by routing poster lookups through the wrapper's instance method.
* Avoid moving other layouts in this slice.
* Add focused boundary tests proving wrapper delegation and poster provider behavior.

## Acceptance Criteria

* [ ] `report_service.py` is smaller and delegates film-strip layout rendering to a new reports-domain module.
* [ ] Existing `ReportGenerator._draw_film_strip_layout()` still works through its original signature.
* [ ] Focused tests cover wrapper delegation and extracted service poster-provider usage.
* [ ] Focused reports tests pass.
* [ ] Full test suite passes.
* [ ] Git working tree is clean after code/test commit, task archive, and journal record.

## Definition of Done

* Tests added or updated for the extracted boundary.
* Project verification run through `uv run`.
* Code/test changes committed separately from Trellis archive and journal bookkeeping.
* No unrelated refactors.

## Technical Approach

Create `app/domains/reports/report_film_strip_poster_layout_service.py` with a `draw_film_strip_layout(...)` function and a small logger provider. `ReportGenerator._draw_film_strip_layout()` will call this function and pass a lambda that invokes `self._get_best_poster(...)`, preserving existing method monkeypatch chains.

## Decision (ADR-lite)

Context: after extracting daily poster data preparation, `report_service.py` remains dominated by large rendering methods. The film-strip layout is the largest single method and has a clear rendering-only responsibility.

Decision: Extract only the film-strip layout in this task, keeping other layout methods in place.

Consequences: This reduces `report_service.py` without changing the public report generator contract. Other layouts can be extracted in later slices with the same pattern.

## Out of Scope

* Moving text-list, card-grid, waterfall, or hero-poster layouts.
* Changing image dimensions, colors, font sizes, placeholder text, or JPEG settings.
* Changing poster-fetching policy or data preparation logic.
* Introducing new public report APIs.

## Technical Notes

* Source requirement: `docs/架构审计.md` P2 item 5 recommends small behavior-preserving slices for large domain files.
* Current target: `app/domains/reports/report_service.py` is about 1.0k lines after the previous data-service extraction.
* Existing pattern: report extraction modules use domain-local services plus compatibility wrappers on `ReportGenerator`.
