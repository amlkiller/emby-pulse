# Refactor Report Poster Fetcher Service

## Goal

Continue the architecture-audit refactor by splitting a focused responsibility out of the large reports domain file. Extract poster lookup/fetching from `app/domains/reports/report_service.py` into a domain-local service module while preserving existing report generation behavior and compatibility.

## Requirements

* Add a reports-domain module responsible for poster lookup/fetching from Emby and TMDB.
* Keep `ReportGenerator` as the public entry point for existing callers.
* Preserve legacy private methods on `ReportGenerator` (`_get_series_id`, `_fetch_emby_poster`, `_fetch_tmdb_poster`, `_get_best_poster`) as compatibility wrappers.
* Preserve monkeypatch compatibility for legacy globals in `report_service.py` by using lazy dependency providers where needed.
* Do not change report image layout, SQL behavior, plugin config behavior, or router/API behavior.
* Add focused boundary tests for the extracted poster fetcher path.

## Acceptance Criteria

* [ ] `report_service.py` line count is reduced by moving poster-fetching implementation into a new domain-local module.
* [ ] Existing callers can still call `report_gen.generate_report()` and `report_gen.generate_daily_poster()`.
* [ ] Existing code that calls or monkeypatches `ReportGenerator._get_best_poster()` keeps working.
* [ ] Emby poster, TV series poster fallback, TMDB fallback, and missing-image fallback behavior are covered by focused tests.
* [ ] Focused report tests pass.
* [ ] Full test suite passes before the code commit.

## Definition of Done

* Tests added or updated for the extracted service boundary.
* Focused compile/import verification passes.
* Focused tests and full tests pass through `uv run`.
* Work commit is separate from Trellis archive and journal commits.

## Technical Approach

Create `app/domains/reports/report_poster_fetcher_service.py` containing a small `ReportPosterFetcher` service and module-level dependency providers. `report_service.py` will configure those providers with lambdas that read the legacy globals (`media_api`, `tmdb_client`, `network_client`, `HAS_PIL`, `logger`) at call time. `ReportGenerator` keeps the old private method names as thin wrappers delegating to the extracted service.

## Decision (ADR-lite)

**Context**: `report_service.py` is currently one of the largest domain files and mixes report orchestration, SQL preparation, image drawing, and external poster fetching.

**Decision**: Extract only poster fetching in this slice. Keep drawing/layout code in place for now to avoid a high-blast-radius change.

**Consequences**: The file becomes smaller and one responsibility has a clear testable boundary. The remaining drawing layouts are still large and can be split in later slices.

## Out of Scope

* Rewriting report layouts.
* Changing poster provider priority.
* Changing plugin configuration handling.
* Changing router authentication or response behavior.
* Introducing a cross-domain public reports facade.

## Technical Notes

* Source audit: `docs/架构审计.md` P2 item 5 recommends behavior-preserving small slices for large domain files.
* Current target: `app/domains/reports/report_service.py`.
* Existing public import path: `app.domains.reports.report_service.report_gen`.
* Existing consumers include reports router, notification bot stats command service, and `view_report` plugin.
