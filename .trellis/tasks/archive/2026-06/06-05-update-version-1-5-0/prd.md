# Update Repository Versions to 1.5.0

## Goal

Update the repository's application release version from the previous prerelease form to `1.5.0` so runtime metadata, packaging metadata, Docker metadata, lock metadata, and public docs agree on the final release version.

## Requirements

* Set the application release version to `1.5.0`.
* Update the runtime version source in `app/shared/version.py`.
* Update project packaging metadata in `pyproject.toml` and the matching project entry in `uv.lock`.
* Update Docker image metadata in `Dockerfile`.
* Update README release badge and pinned GHCR tag.
* Update the changelog entry for the release.
* Add a reusable version update guide under `docs/version-update.md`.
* Do not rewrite unrelated version values such as plugin versions, dependency versions, API/protocol versions, XML versions, Docker Compose schema versions, or Trellis internal versions.

## Acceptance Criteria

* [x] No previous prerelease application-version references remain outside archived Trellis task history.
* [x] Runtime `APP_VERSION` is `1.5.0`.
* [x] Packaging and lock metadata agree on `1.5.0`.
* [x] Existing version boundary tests pass.
* [x] Version update steps are documented for future releases.

## Definition of Done

* Relevant version references are updated.
* Version update documentation is added.
* Targeted tests pass through `uv run`.
* Specs are reviewed for whether new guidance is needed.

## Technical Approach

Search the repository for application release version strings, then update only the release-version sources and documentation. Preserve unrelated version semantics.

## Decision (ADR-lite)

Context: The repository contains many `version` fields with different meanings.

Decision: Treat the previous prerelease value and its normalized/rendered forms as the release version to update, while leaving unrelated plugin, dependency, protocol, XML, and schema versions unchanged.

Consequences: The release metadata becomes consistent without corrupting dependency locks or external protocol expectations.

## Out of Scope

* Changing plugin version numbers.
* Changing third-party dependency versions.
* Changing API protocol versions, XML declarations, Docker Compose schema version, or Trellis internal metadata.
* Creating a release tag or pushing Docker images.

## Technical Notes

* Runtime version metadata belongs in `app/shared/version.py`.
* `CLAUDE.md` notes Docker/CI version mirroring is handled by existing release workflow files.
* Search found application-version references in `pyproject.toml`, `app/shared/version.py`, `Dockerfile`, `README.md`, `CHANGELOG.md`, and the `embypulse-next` package entry in `uv.lock`.
