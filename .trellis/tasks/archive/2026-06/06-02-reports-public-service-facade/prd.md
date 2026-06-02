# Reports Public Service Facade

## Goal

Continue the architecture audit P2 cross-domain boundary work by introducing a narrow public reports facade and moving the `view_report` plugin away from direct imports of `app.domains.reports.report_queries` and `app.domains.reports.report_service`.

## Requirements

- Add a public reports facade module such as `app/domains/reports/public_service.py`.
- Expose the current report query and poster-generation operations needed by the `view_report` plugin:
  - `count_report_plays(...)`
  - `sum_report_duration(...)`
  - `count_report_distinct_users(...)`
  - `list_report_top_users(...)`
  - `list_report_content_items(...)`
  - `has_pillow_support()`
  - `generate_daily_poster(...)`
- Preserve existing behavior, return values, exception behavior, and call arguments by delegating to the existing query/service implementation.
- Migrate `app/plugins/view_report/plugin.py` away from direct `report_queries` and `report_service` imports to the facade.
- Keep reports-domain-internal direct query/service usage out of scope.
- Keep `app/domains/reports/router.py` compatibility behavior out of scope.
- Add focused regression tests that prove the facade delegates correctly and the selected plugin no longer imports reports private query/service modules directly.
- Do one consolidated verification pass and one work commit for this task.

## Acceptance Criteria

- `app/domains/reports/public_service.py` exists and exposes narrow functions for the selected query and poster operations.
- `app/plugins/view_report/plugin.py` no longer directly imports:
  - `app.domains.reports.report_queries`
  - `app.domains.reports.report_service`
- Call-site arguments and behavior are unchanged for migrated plugin callers.
- Facade delegation tests cover representative return-value and argument forwarding.
- Boundary tests fail if `view_report` reintroduces direct reports query/service imports.
- Compile, focused tests, ruff `E9,F63,F7,F82`, `git diff --check`, and full pytest pass in one consolidated verification pass.

## Out of Scope

- Do not split `app/domains/reports/report_service.py`.
- Do not change report query SQL, poster design, themes, report text, schedule behavior, or plugin configuration behavior.
- Do not migrate reports-domain-internal direct imports in this slice.
- Do not migrate other plugins or routes unless required by tests.

## Technical Approach

- Create `app/domains/reports/public_service.py` as a thin facade over `report_queries` and `report_service.report_gen`.
- Replace the `view_report` plugin's top-level `report_queries` import with `reports.public_service`.
- Replace local `from app.domains.reports.report_service import report_gen, HAS_PIL` imports with facade calls.
- Add focused AST/source boundary tests for the plugin import boundary.
- Add unit tests that monkeypatch facade dependencies and assert arguments/return values are forwarded.

## Technical Notes

- Audit reference: `docs/架构审计.md` P2 issue 6, cross-domain direct imports.
- Existing architecture spec: `.trellis/spec/backend/directory-structure.md` says cross-domain behavior should prefer a public service function, narrow facade, or event boundary.
- This is a small plugin-facing reports facade slice so it can be verified and committed as one coherent task.
