# Remove Config Save Redirect

## Goal

Remove the module-level `save_config()` helper because it only forwards to `cfg.save()`.

## Scope

- Update callers to invoke `cfg.save()` directly.
- Delete `save_config()` from `app/core/config.py`.
- Do not change config read accessors such as `cfg.get`, `get_all`, or environment/variable access.
- Preserve configuration save behavior and existing route behavior.

## Acceptance Criteria

- No `save_config()` definition or call remains.
- System settings routes still save configuration through `cfg.save()`.
- Focused compile/import checks and the full test suite pass.
