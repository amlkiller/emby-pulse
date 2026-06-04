# Fix Starlette TemplateResponse Compatibility

## Goal

Fix the runtime failure introduced by the Python 3.12 dependency refresh where Starlette treats legacy `TemplateResponse(name, context)` positional calls as the new `(request, name, context)` signature, causing `TypeError: unhashable type: 'dict'` while rendering `/request`.

## Requirements

* Migrate existing app-owned template calls from legacy positional `TemplateResponse(name, context)` to Starlette's current `TemplateResponse(request, name, context)` API.
* Use Starlette's current template construction and response APIs directly; avoid keeping a compatibility helper when direct migration is practical.
* Add focused coverage that fails on the reported regression and passes with the compatibility fix.
* Keep the fix localized to template construction and response call sites.

## Acceptance Criteria

* [x] `/request` uses the current Starlette template response signature and does not treat the context dict as the template name.
* [x] A test covers the reported `/request` rendering regression.
* [x] `uv run pytest tests/ -v` passes.
* [x] Related backend spec notes stay accurate.

## Definition of Done

* Regression test added.
* Full test suite passes through `uv run`.
* Changes are committed before finish-work.

## Technical Notes

* Reported production stack: `app/domains/system/views.py`, `request_page`, `templates.TemplateResponse(...)`, then Jinja2 `TypeError: unhashable type: 'dict'`.
* Likely root cause: Starlette/FastAPI `TemplateResponse` positional signature changed in the refreshed dependency set.
* Existing app code contains many legacy positional template calls; the chosen approach is to migrate call sites to the current API rather than hide the change behind a compatibility shim.
* `app/shared/template_factory.py` is removed because direct `Jinja2Templates(directory="templates")` is now sufficient.
