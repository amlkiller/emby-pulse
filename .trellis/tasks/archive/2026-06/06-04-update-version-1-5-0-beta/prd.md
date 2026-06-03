# Update Version to 1.5.0-beta

## Goal

Update the main application version metadata from `1.4.6` to `1.5.0-beta` so runtime views and project packaging metadata report the requested beta release version.

## Requirements

* Change the main application version constant to `1.5.0-beta`.
* Change the Python project metadata version to `1.5.0-beta`.
* Keep lockfile project metadata consistent if it records the local project version.
* Add a concise user-facing changelog entry covering changes from `1.4.6` to `1.5.0-beta`.
* Do not change plugin-specific version fields.
* Do not change dependencies or runtime behavior.

## Acceptance Criteria

* [x] `app.shared.version.APP_VERSION` is `1.5.0-beta`.
* [x] `pyproject.toml` reports project version `1.5.0-beta`.
* [x] `uv.lock` local project entry reports version `1.5.0-beta`.
* [x] `CHANGELOG.md` includes a concise `1.5.0-beta` entry before `1.4.6`.
* [x] No plugin version fields are modified.

## Definition of Done

* Relevant version files are updated.
* A focused verification confirms no stale `1.4.6` main application version remains.

## Technical Approach

Update only the version metadata files discovered by repository inspection: `app/shared/version.py`, `pyproject.toml`, and the local project package entry in `uv.lock`.

## Decision (ADR-lite)

**Context**: The repository has a side-effect-free application version constant used by views and notifications, plus Python project metadata used by packaging tooling.

**Decision**: Keep the application constant and package metadata aligned at `1.5.0-beta`.

**Consequences**: The displayed and packaged application version match the requested beta version without altering plugin release versions.

## Out of Scope

* Plugin version bumps.
* Detailed technical migration notes.
* Dependency updates.

## Technical Notes

* `app/shared/version.py` currently defines `APP_VERSION = "1.4.6"`.
* `pyproject.toml` currently defines `[project] version = "1.4.6"`.
* `uv.lock` records the local `embypulse-next` package at version `1.4.6`.
