# Replace Redundant Public Service Function References

## Goal

Remove redundant public service exposures whose functions only forward to another
implementation without validation, orchestration, error handling, caching, or
other domain semantics. Callers should import the module that actually performs
the work.

## Scope

- Remove `app.domains.system.public_service.save_code_registration_meta_and_finish_invitation`.
- Replace callers with `app.domains.system.invitation_dao.save_code_registration_meta_and_finish_invitation`.
- Remove focused tests that assert the public service re-export exists.
- Audit all `app/domains/*/public_service.py` modules for pure forwarding
  functions.
- For pure forwarders, replace callers with the real implementation module and
  remove tests that only assert the redundant forwarding layer.
- Keep public service functions that add extra semantics such as caching,
  permission policy, lazy runtime lookup, exception handling, normalization, or
  cross-call orchestration.

## Verification

- Compile changed Python files with `uv run`.
- Run focused tests covering updated imports and removed facade assertions with
  `uv run`.
