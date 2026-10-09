# Changelog

## 0.1.3 — 2026-10-09

- Compare full baseline/current observed inventories by path and kind with
  `compare_reports`, `--baseline`, and a separate `--comparison-report` artifact.
  `--require-unchanged` exits 4 on added or removed features. Unknown report
  formats and different numeric models fail closed before output.
- Add exact SHA-256 checked `Pin` / `--pin-row` selection before greedy completion.
  Pins consume the existing row and output-byte budgets and fail closed on
  missing/changed source rows or insufficient budgets. Opt-in report format 3
  preserves feature models and explains pinned versus greedy rows.
- Add a complete pytest/GitHub Actions regression case with reviewed baseline,
  value-sensitive pinned row, structural-change failure, and importer assertions.
- Test installed wheel and sdist on the full five-environment CI matrix; document
  a reproducible growth case and targets for three external trials and one CI adoption.
- Keep default selection and coverage-report formats unchanged. Fix outdated
  documentation about the already published numeric-syntax option.

## 0.1.2 — 2026-10-09

- Add opt-in `--number-mode syntax` / `number_mode="syntax"` to distinguish
  integer tokens from fractional/exponent tokens. Default JSON-number coverage and
  report format 1 stay unchanged; the opt-in feature model uses report format 2.
- Add seeded selection-oracle, byte/provenance, strict-input, CLI, determinism, and
  real sqlite-utils/dlt regression tests for numeric syntax coverage.
- Publish version increases merged into `main` automatically after both CI and
  Release readiness succeed on that exact commit. Unchanged/already-published
  versions are no-ops; partial releases and uncertain registry responses fail closed.
- Keep isolated builds, exact artifact-ID/hash verification, serialized uploads,
  and the existing owner-configured PyPI token. Stable tags no longer publish.

## 0.1.1 — 2026-10-09

- Add executable sqlite-utils and dlt/DuckDB regression recipes with pinned optional
  development dependencies, source-byte verification, real schema/value comparisons,
  and counterexamples where complete structural coverage loses importer behavior.
- Exercise the optional importer suite in a separate CI job; runtime and core tests
  remain standard-library-only.
- Walk wide objects/arrays lazily so traversal bookkeeping is bounded by nesting
  depth and node limits are checked before expanding siblings. Selection, report
  format, and feature semantics are unchanged.
- Use one runtime version for the API, CLI, and provenance report, and verify it
  against package metadata in both built distributions.
- Remove the 0.1.0 filename from readiness checks and test real importers against
  the installed release wheel before any future publishing step.

- Introduce stable-tag publishing with cross-platform verification and hash-verified
  artifacts (superseded by the main-CI publishing gate in 0.1.2).

- Add runnable pytest, ETL regression, and importer bug-repro recipes.
- Add a disclosed synthetic structural-coverage/timing comparison.
- Prepare wheel/sdist metadata checks, a package-index-friendly description, and a
  non-publishing release-readiness workflow. The OIDC alternative remains inactive.

## 0.1.0 — 2026-10-07

Published to [PyPI](https://pypi.org/project/shapewitness/0.1.0/) from
[tag v0.1.0](https://github.com/agent-axiom/shapewitness/releases/tag/v0.1.0).

Initial implementation: deterministic greedy structural witness selection for JSONL;
local missing-member coverage; strict UTF-8/JSON validation; byte-preserving output;
versioned coverage/provenance reports; bounded private SQLite spooling; Python API;
pipeline-friendly CLI; generated invariant and resource tests. See the official package index and publishing run for release status.
