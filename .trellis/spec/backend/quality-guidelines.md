# Quality Guidelines

> Code quality standards for backend development.

---

## Scenario: Python Commands Must Use `uv run`

### 1. Scope / Trigger

- Trigger: any backend verification command that imports project modules, runs tests, compiles Python files, or executes Python helper scripts.
- Applies to Codex/AI sessions and developer terminal commands in this repository.
- This project has `requirements.txt` but no `pyproject.toml`; running bare `python ...` or bare `uv run ...` can use the wrong interpreter environment and produce false failures such as missing `jinja2` or `requests`.

### 2. Signatures

- Import check: `uv run --with-requirements requirements.txt python -c "<imports>"`
- Compile check: `uv run --with-requirements requirements.txt python -m compileall <paths>`
- Test suite: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`
- Windows PowerShell UTF-8 import check when project startup prints Unicode: `$env:PYTHONIOENCODING='utf-8'; uv run --with-requirements requirements.txt python -c "<imports>"`

### 3. Contracts

- All Python commands that touch project code must be executed through `uv run --with-requirements requirements.txt`.
- Do not diagnose missing project dependencies from a bare `python` or bare `uv run` result unless the same command also fails with `--with-requirements requirements.txt`.
- On Windows consoles, set `PYTHONIOENCODING=utf-8` or use an equivalent UTF-8 Python mode when command output may include emoji or Chinese text.
- Keep command output interpretation scoped: dependency/environment failures are not code regressions until reproduced in the project `uv` environment.

### 4. Validation & Error Matrix

- Bare `python -c "import app..."` reports `AssertionError: jinja2 must be installed` -> rerun with `uv run --with-requirements requirements.txt`; treat the first result as invalid environment evidence.
- Bare `uv run python -c "import app..."` reports `ModuleNotFoundError: No module named 'requests'` -> rerun with `--with-requirements requirements.txt`; bare `uv run` did not load project dependencies.
- Bare `python ...` reports `UnicodeEncodeError: 'gbk' codec can't encode ...` on Windows -> rerun with `PYTHONIOENCODING=utf-8` plus `uv run --with-requirements requirements.txt`.
- `uv run --with-requirements requirements.txt ...` reports syntax/import errors inside changed modules -> treat as a real code issue and fix.
- `uv run --with-requirements requirements.txt --with pytest pytest ...` fails tests -> inspect and fix the test failure, not the command environment.

### 5. Good/Base/Bad Cases

- Good: `$env:PYTHONIOENCODING='utf-8'; uv run --with-requirements requirements.txt python -c "import app.routers.clients; print('imports ok')"`
- Base: `uv run --with-requirements requirements.txt python -m compileall app/dao/client_dao.py app/routers/clients.py`
- Good: `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v`
- Bad: `python -c "import app.routers.clients"` followed by reporting missing `jinja2` as a project failure.
- Bad: `uv run python -c "import app.routers.clients"` followed by reporting missing `requests` as a project failure.

### 6. Tests Required

- For focused backend refactors, run `uv run --with-requirements requirements.txt python -m compileall <changed-python-files>`.
- For import-sensitive changes, run an import check through `uv run --with-requirements requirements.txt python -c ...`; add `PYTHONIOENCODING=utf-8` on Windows if startup output includes non-ASCII text.
- For behavior changes or before final completion, run `uv run --with-requirements requirements.txt --with pytest pytest tests/ -v` unless the user explicitly narrows verification scope.

### 7. Wrong vs Correct

#### Wrong

```powershell
python -c "import app.routers.clients"
```

#### Correct

```powershell
$env:PYTHONIOENCODING='utf-8'; uv run --with-requirements requirements.txt python -c "import app.routers.clients"
```

---

## Forbidden Patterns

- Do not run project Python verification with bare `python` or bare `uv run` and treat dependency errors as actionable code failures.
- Do not omit `--with-requirements requirements.txt`; imports can still initialize project dependencies.

---

## Required Patterns

- Use `uv run --with-requirements requirements.txt` for Python commands that execute or import repository code.
- Mention when verification could not be completed and include the exact `uv run` command that failed or was skipped.

---

## Testing Requirements

- Focused refactors need at least compile checks for changed Python files.
- Route/DAO/query boundary refactors should include import checks for the changed route, DAO, and query modules.
- Broader behavior changes should run the pytest command documented above.

---

## Code Review Checklist

- [ ] Verification commands use `uv run --with-requirements requirements.txt`.
- [ ] Windows Unicode output is handled with UTF-8 mode when needed.
- [ ] Dependency errors are reproduced under `uv run` before being reported as code issues.
