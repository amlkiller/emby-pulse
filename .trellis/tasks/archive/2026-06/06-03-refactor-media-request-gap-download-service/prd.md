# Refactor Media Request Gap Download Service

## Goal

Continue the architecture-audit P2 domain split work by moving the gap download and torrent interception logic out of `app/domains/media_requests/gaps.py` into a smaller media-request domain service. Keep the `/api/gaps/download` route behavior and existing internal helper names compatible.

## Requirements

* Extract the bottom-of-file gap download responsibilities from `gaps.py`:
  * `extract_episodes_from_filename`;
  * `hook_qbittorrent`;
  * `hook_transmission`;
  * the async body used by `download_gap_item`.
* Preserve the public route function `download_gap_item(request=None, payload=None)` in `gaps.py`.
* Preserve existing helper names in `gaps.py` as compatibility wrappers where external/internal callers may import them.
* Preserve admin-check behavior:
  * request-based calls require `user_service.is_admin_user(request)`;
  * internal calls with `request=None` skip the check.
* Preserve MoviePilot submission behavior and response shape:
  * return `{"status": "success", "message": "种子已提交到后台队列，正在处理..."}` immediately after starting the background thread;
  * submit `{"torrent_in": pure_torrent_in}` via `moviepilot_client.add_download`.
* Preserve scan-state and DAO side effects after successful MoviePilot submission:
  * update gap records to status `2`;
  * update matching in-memory `scan_state["results"]` gaps to status `2`.
* Preserve qBittorrent and Transmission hook behavior, messages, polling shape, and safe-error fallbacks.
* Add focused boundary tests for episode extraction and the download service boundary, including admin denial, immediate background-thread submission, MoviePilot success side effects, and hook dispatch.

## Acceptance Criteria

* [ ] `gaps.py` no longer owns the full download/hook implementation body.
* [ ] A domain-local media request service owns the download and hook behavior.
* [ ] Existing route and helper names remain import-compatible.
* [ ] Focused tests pass for the extracted service.
* [ ] Existing gap-related tests still pass.
* [ ] Full test suite passes before committing.

## Definition of Done

* Tests added or updated for the extracted boundary.
* `uv run` is used for Python commands that execute project code.
* `git diff --check` passes.
* Code/test changes are committed separately from Trellis archive and journal commits.

## Technical Approach

Create `app/domains/media_requests/gap_download_service.py` and configure it from `gaps.py` using provider lambdas for settings, clients, DAO functions, scan state, lock, and thread creation. `gaps.py` will keep thin wrappers for the route and legacy helper functions.

## Out of Scope

* Changing HDHive or MoviePilot search behavior.
* Changing scanner lifecycle or cache refresh behavior.
* Reworking all gap routes.
* Introducing new public cross-domain facades.

## Technical Notes

* Architecture audit target: `docs/架构审计.md` P2 item 5, "domain 已迁移，但内部仍是大文件混合职责".
* This slice targets the current largest domain file, `app/domains/media_requests/gaps.py`.
* Keep behavior-preserving wrapper functions in `gaps.py` because `update_router.py` lazily imports `download_gap_item`, and other code/tests may import the hook helpers by name.
