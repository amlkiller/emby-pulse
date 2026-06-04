# Unify Avatar Upload Validation

## Goal

Make Emby avatar upload validation consistent with the existing strong local-avatar validation. Uploaded or downloaded avatar bytes must not rely on client-provided `Content-Type`; they should be verified with magic bytes, parsed by PIL, and re-encoded to strip metadata before being sent to the media server.

## Requirements

* Reuse the existing image validation utility for binary avatar upload paths.
* Apply strong validation to `/api/manage/user/image` for both file uploads and URL downloads.
* Apply strong validation to `/api/user/avatar`.
* Use the validator-derived MIME type for the media server upload header instead of trusting upload or response `Content-Type`.
* Preserve existing authorization checks, size limit behavior, and response shape as much as practical.

## Acceptance Criteria

* [ ] Invalid image bytes that pass only superficial content-type assumptions are rejected before media server mutation.
* [ ] Valid PNG/JPEG/WEBP/GIF bytes are accepted, parsed, and re-encoded before upload.
* [ ] The media server `Content-Type` header comes from the validated image format.
* [ ] Existing unauthorized request behavior remains unchanged.
* [ ] Focused tests cover the stronger validation path.

## Definition of Done

* Tests added or updated for the avatar binary upload validation behavior.
* Changed Python files compile through `uv run`.
* Relevant focused pytest subset passes through `uv run`.

## Technical Approach

Add a binary-image validator helper beside `validate_base64_image` so routes do not need to round-trip through data URLs. Inject that helper into `avatar_router` the same way current dependencies are injected, use its sanitized bytes and MIME result for media server posts, and remove direct trust in file or URL `Content-Type`.

## Out of Scope

* Changing the local-account `/api/auth/avatar` base64 storage flow.
* Changing avatar size limits or allowed formats.
* Changing media server avatar delete/post ordering.

## Technical Notes

* Current weak paths are in `app/domains/users/avatar_router.py`.
* Existing strong validation is in `app/utils/image_validator.py`.
* Existing backend quality guidance requires `uv run` for compile and tests.
