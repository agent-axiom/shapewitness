# Changelog

## Release automation

- New stable version tags run cross-platform verification and publish the same
  hash-verified wheel/sdist using the owner-configured GitHub Actions secret.

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
