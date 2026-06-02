# Refactor Report Rendering Assets

## Goal

Reduce `app/domains/reports/report_service.py` by extracting report rendering assets and font/PIL helpers into a domain-local module while preserving existing report generation behavior.

## Scope

- Move the poster theme catalog and theme-list helper out of `report_service.py`.
- Move PIL availability detection and font cache/loading helpers out of `report_service.py`.
- Keep `report_service.py` compatibility exports for existing callers/tests, including `HAS_PIL`, `get_theme_list`, `_get_font`, and `report_gen`.
- Do not change route URLs, response shapes, notification/plugin call behavior, image output logic, query logic, or startup side effects.

## Verification

- Compile changed Python files with `uv run python -m compileall`.
- Run import compatibility checks through `uv run python -c`.
- Run focused reports tests.
- Run the full test suite with `uv run pytest tests/ -v`.
