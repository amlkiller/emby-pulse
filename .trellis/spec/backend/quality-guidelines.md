# Quality Guidelines

> Code quality standards for backend development.

---

## Scenario: Python Commands Must Use The Locked uv Project

### 1. Scope / Trigger

- Trigger: any backend verification command that imports project modules, runs tests, compiles Python files, or executes Python helper scripts.
- Applies to Codex/AI sessions and developer terminal commands in this repository.
- This project uses `pyproject.toml` plus `uv.lock` as the source of truth for Python dependencies. `requirements.txt` is a compatibility export only.

### 2. Signatures

- Install dependencies: `uv sync --locked`
- Import check: `uv run python -c "<imports>"`
- Compile check: `uv run python -m compileall <paths>`
- Test suite: `uv run pytest tests/ -v`
- Windows PowerShell UTF-8 import check when project startup prints Unicode: `$env:PYTHONIOENCODING='utf-8'; uv run python -c "<imports>"`

### 3. Contracts

- Update dependencies in `pyproject.toml`, then regenerate `uv.lock` with `uv lock`.
- Run commands that touch project code through `uv run` so they use the locked project environment.
- Run `uv sync --locked` before verification when the environment may be stale.
- Do not diagnose missing project dependencies from a bare `python` result unless the same command also fails through `uv run`.
- On Windows consoles, set `PYTHONIOENCODING=utf-8` or use an equivalent UTF-8 Python mode when command output may include emoji or Chinese text.
- Keep command output interpretation scoped: dependency/environment failures are not code regressions until reproduced in the locked `uv` environment.

### 4. Validation & Error Matrix

- Bare `python -c "import app..."` reports missing packages -> rerun with `uv run python -c "import app..."`; treat the first result as invalid environment evidence.
- `uv run python -c "import app..."` reports syntax/import errors inside changed modules -> treat as a real code issue and fix.
- Bare `python ...` reports `UnicodeEncodeError: 'gbk' codec can't encode ...` on Windows -> rerun with `PYTHONIOENCODING=utf-8` plus `uv run`.
- `uv sync --locked` reports that the lockfile needs an update -> run `uv lock`, inspect the dependency diff, then rerun `uv sync --locked`.
- `uv run pytest tests/ -v` fails tests -> inspect and fix the test failure, not the command environment.

### 5. Good/Base/Bad Cases

- Good: `uv sync --locked`
- Good: `$env:PYTHONIOENCODING='utf-8'; uv run python -c "import app.domains.notifications.router; print('imports ok')"`
- Base: `uv run python -m compileall app/domains/notifications/router.py tests/test_notification_router_public_auth_facade_boundary.py`
- Good: `uv run pytest tests/ -v`
- Bad: `python -c "import app.domains.notifications.router"` followed by reporting missing `jinja2` as a project failure.
- Bad: editing `requirements.txt` directly as the dependency source of truth.

### 6. Tests Required

- For focused backend refactors, run `uv run python -m compileall <changed-python-files>`.
- For import-sensitive changes, run an import check through `uv run python -c ...`; add `PYTHONIOENCODING=utf-8` on Windows if startup output includes non-ASCII text.
- For behavior changes or before final completion, run `uv run pytest tests/ -v` unless the user explicitly narrows verification scope.

### 7. Wrong vs Correct

#### Wrong

```powershell
python -c "import app.domains.notifications.router"
```

#### Correct

```powershell
$env:PYTHONIOENCODING='utf-8'; uv run python -c "import app.domains.notifications.router"
```

---

## Forbidden Patterns

- Do not run project Python verification with bare `python` and treat dependency errors as actionable code failures.
- Do not edit `requirements.txt` as the primary dependency manifest.
- Do not use `uv run --with-requirements requirements.txt` for project verification; use the locked project environment instead.

---

## Required Patterns

- Use `pyproject.toml` and `uv.lock` as the dependency source of truth.
- Use `uv run` for Python commands that execute or import repository code.
- Mention when verification could not be completed and include the exact `uv run` command that failed or was skipped.

---

## Scenario: Jinja Template Construction And Responses

### 1. Scope / Trigger

- Trigger: any backend code that creates or changes a FastAPI/Starlette `Jinja2Templates` instance or `TemplateResponse` call.
- Applies to shared config, system views, notification views, and any future HTML-rendering route or plugin.

### 2. Signatures

- Use `Jinja2Templates(directory="templates")` for normal app template rendering.
- Current Starlette construction signature is `Jinja2Templates(directory=..., context_processors=..., env=...)`; it does not accept `autoescape=...`.
- Current Starlette response signature is `TemplateResponse(request, name, context=None, status_code=200, headers=None, media_type=None, background=None)`.

### 3. Contracts

- Prefer the direct Starlette constructor unless a task needs a custom Jinja `Environment`.
- Pass `request` as the first `TemplateResponse` argument. Existing context dicts should still include `"request": request` when templates rely on that value.
- Do not add compatibility wrappers for old positional signatures when the call sites are practical to migrate.

### 4. Validation & Error Matrix

- `Jinja2Templates(directory="templates", autoescape=True)` -> invalid on current Starlette; raises `TypeError` during import/test collection.
- `templates.TemplateResponse("page.html", {"request": request})` -> invalid on current Starlette; the context dict is treated as the template name and can raise `TypeError: unhashable type: 'dict'`.
- Custom template directory needed -> pass the directory to `Jinja2Templates(directory=<directory>)`.

### 5. Good/Base/Bad Cases

- Good: `templates = Jinja2Templates(directory="templates")`
- Good: `templates.TemplateResponse(request, "page.html", {"request": request})`
- Bad: `templates = Jinja2Templates(directory="templates", autoescape=True)`
- Bad: `templates.TemplateResponse("page.html", {"request": request})`

### 6. Tests Required

- For template construction or response-call changes, run `uv run python -m compileall <changed files>`.
- Add or update a focused test for any route that previously failed during rendering.
- Run `uv run pytest tests/ -v` or the affected import/rendering-heavy test subset.

### 7. Wrong vs Correct

#### Wrong

```python
return templates.TemplateResponse("request.html", {"request": request})
```

#### Correct

```python
return templates.TemplateResponse(request, "request.html", {"request": request})
```

---

## Testing Requirements

- Focused refactors need at least compile checks for changed Python files.
- Route/DAO/query boundary refactors should include import checks for the changed route, DAO, and query modules.
- Broader behavior changes should run the pytest command documented above.

---

## Code Review Checklist

- [ ] Dependency changes are represented in `pyproject.toml` and `uv.lock`.
- [ ] Verification commands use `uv run`.
- [ ] Windows Unicode output is handled with UTF-8 mode when needed.
- [ ] Dependency errors are reproduced under `uv run` before being reported as code issues.
