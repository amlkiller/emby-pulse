# Refactor Reports Daily Poster Data Service

## Goal

Split the non-rendering daily poster preparation logic out of `app/domains/reports/report_service.py` into a smaller reports-domain service, following `docs/架构审计.md` P2 item 5. Keep `ReportGenerator` as the public rendering entry point and preserve current behavior.

## Requirements

* Extract the daily poster period-context and ranked-item preparation logic from `ReportGenerator.generate_daily_poster()` into a domain-local module.
* Keep existing `ReportGenerator.generate_daily_poster()` signature and return behavior.
* Preserve external-data behavior: when `tv_list` or `movie_list` is provided, skip database/plugin query logic and use the provided lists after normalizing missing inputs to empty lists.
* Preserve internal-data behavior: plugin exclude types, report top query limit, ranked item query, debug logging, TV/movie grouping, TV episode aggregation, top-5 truncation, and empty-list `None` behavior.
* Preserve existing monkeypatch compatibility where tests or callers patch legacy globals on `report_service.py`; providers in the extracted module must read those legacy globals dynamically.
* Add focused boundary tests for the extracted service and compatibility wrapper path.

## Acceptance Criteria

* [ ] `report_service.py` is smaller and delegates daily poster data preparation to a new reports-domain module.
* [ ] Existing public `ReportGenerator.generate_daily_poster()` remains behavior-compatible.
* [ ] Focused tests cover external data passthrough, internal ranked-item aggregation, plugin exclude type parsing, and wrapper delegation.
* [ ] Focused report tests pass.
* [ ] Full test suite passes.
* [ ] Git working tree is clean after code/test commit, task archive, and journal record.

## Definition of Done

* Tests added or updated for the extracted boundary.
* Project verification run through `uv run`.
* No unrelated refactors or metadata churn in code commits.
* Task scaffold, activation, work commit, task archive, and journal record are separate commits.

## Technical Approach

Create `app/domains/reports/report_daily_poster_data_service.py` with provider injection for time helpers, plugin config, ranked-item query, settings, logger, and regex compilation. `ReportGenerator.generate_daily_poster()` will request a prepared data object/dict from that module, then keep the existing layout dispatch and drawing methods in `report_service.py`.

## Decision (ADR-lite)

Context: `report_service.py` is currently the largest domain file and mixes querying/grouping with image rendering.

Decision: Extract only the data preparation logic first, not the large drawing layout methods.

Consequences: This reduces mixed responsibilities with a small blast radius. Rendering code remains in place for later slices, so image output changes are avoided in this task.

## Out of Scope

* Moving `_draw_*_layout()` methods or changing visual output.
* Reworking `report_queries.py`, theme assets, or poster fetcher behavior.
* Changing plugin configuration semantics.
* Introducing new public report APIs.

## Technical Notes

* Source requirement: `docs/架构审计.md` P2 item 5 recommends small behavior-preserving slices for large domain files.
* Current target: `app/domains/reports/report_service.py` is about 1.2k lines and mixes report querying, daily poster data preparation, and image rendering.
* Related existing extraction pattern: `app/domains/reports/report_poster_fetcher_service.py` plus compatibility wrapper methods on `ReportGenerator`.
