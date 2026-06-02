# Risk settings typed contract convergence

## Goal

Strengthen the risk configuration settings boundary so callers receive typed, bounded, supported values instead of raw `cfg.get()` output.

## What I already know

* `docs/架构审计.md` identifies weak settings contracts as a P3 architecture issue.
* `app/infra/config/risk_settings.py` is a small settings module with raw integer casts and free-form string reads.
* `app/domains/risk/router.py` and `app/domains/risk/risk_service.py` already recognize three violation actions: `warn_only`, `warn_user`, and `auto_ban`.
* Existing router tests monkeypatch the settings functions, so focused settings tests can be added without changing router API behavior.

## Requirements

* Make risk numeric getters resilient to missing, empty, malformed, and negative values.
* Clamp device/concurrency limits to sensible minimums so invalid config cannot produce nonsensical runtime policy.
* Normalize boolean settings to real `bool` values for common string/int representations.
* Normalize `violation_action` to one of the supported actions, defaulting to `warn_only`.
* Normalize setters for numeric and action values before writing to config.
* Preserve public function names and call sites.

## Acceptance Criteria

* [ ] `get_max_devices()` returns an integer of at least 1, defaulting to 10 for invalid values.
* [ ] `get_default_max_concurrent()` returns an integer of at least 1, defaulting to 2 for invalid values.
* [ ] risk boolean getters return actual booleans for bool, numeric, and common string config values.
* [ ] `get_violation_action()` returns only `warn_only`, `warn_user`, or `auto_ban`.
* [ ] setters normalize written values for default concurrency and violation action.
* [ ] Focused tests cover defaults, invalid values, clamping, boolean normalization, and action normalization.
* [ ] Changed Python files compile through `uv run`.
* [ ] Full `uv run pytest tests/ -v` passes.

## Definition of Done

* Code and tests committed as one work commit.
* Trellis task archived after the work commit.
* Session journal records the work commit.
* Spec update considered; update only if this establishes durable guidance beyond the audit's existing P3 note.

## Technical Approach

Add small private normalization helpers in `risk_settings.py` rather than introducing a broad settings object. Keep behavior conservative: invalid config falls back to existing defaults, and supported action strings pass through unchanged.

## Decision (ADR-lite)

Context: The audit calls for settings readers to define return type, default, empty-value semantics, and legal ranges.

Decision: Harden one concrete settings module first with private helpers and focused tests instead of starting a cross-project typed settings rewrite.

Consequences: Risk runtime policy gets a dependable config boundary while keeping the public API stable.

## Out of Scope

* UI/API schema changes.
* A global typed settings framework.
* Wrapper/pass-through cleanup.
* Changes to risk monitoring behavior beyond config normalization.

## Technical Notes

* Relevant specs: `.trellis/spec/backend/directory-structure.md`, `.trellis/spec/backend/quality-guidelines.md`, `.trellis/spec/guides/index.md`.
* Relevant files: `app/infra/config/risk_settings.py`, focused test file to add under `tests/`.
