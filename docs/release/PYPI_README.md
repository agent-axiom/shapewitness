# ShapeWitness

[![CI](https://github.com/agent-axiom/shapewitness/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/agent-axiom/shapewitness/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://github.com/agent-axiom/shapewitness/blob/main/pyproject.toml)
[![MIT license](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/agent-axiom/shapewitness/blob/main/LICENSE)
[![Runtime dependencies: 0](https://img.shields.io/badge/Runtime_dependencies-0-success)](https://github.com/agent-axiom/shapewitness/blob/main/pyproject.toml)

**Small JSONL fixtures that show the shapes your code needs to handle.**

`head -n 20` often gives you twenty happy-path rows. ShapeWitness keeps the records
with missing fields, nulls, empty collections, and mixed types, then explains why
each row was selected.

- **Real records:** original bytes, numeric precision, whitespace, and line endings
- **Explainable coverage:** observed structural features, uncovered gaps, source hashes
- **Reproducible and local:** deterministic selection, bounded disk spooling, no network calls

## Install

Python 3.10+ with SQLite support. Install from a checkout:

```sh
python -m pip install .
```

Or directly from GitHub:

```sh
python -m pip install 'git+https://github.com/agent-axiom/shapewitness.git'
```

Pin a reviewed commit for reproducible source installations. See [release guidance](https://github.com/agent-axiom/shapewitness/blob/main/docs/release/README.md).

## Ten-second demo

From a checkout:

```sh
shapewitness examples/events.jsonl -n 4 --report coverage.json > fixture.jsonl
# shapewitness: 4/6 rows; 19/19 observed features; complete
```

Lines **1, 3, 4, and 5** survive. See the [input](https://github.com/agent-axiom/shapewitness/blob/main/examples/events.jsonl),
[selected fixture](https://github.com/agent-axiom/shapewitness/blob/main/examples/witness.jsonl), and [explanation](https://github.com/agent-axiom/shapewitness/blob/main/examples/coverage.json).
Use `--require-complete` to fail CI when the selected rows leave observed features uncovered.

## Read next

| I want to… | Start here |
| --- | --- |
| Use the CLI, pipes, or Python API | [Usage](https://github.com/agent-axiom/shapewitness/blob/main/docs/usage.md) |
| Build pytest fixtures, test ETL, or reproduce an importer bug | [Recipes](https://github.com/agent-axiom/shapewitness/blob/main/docs/recipes/README.md) |
| Inspect a reproducible head/random comparison | [Synthetic benchmark](https://github.com/agent-axiom/shapewitness/blob/main/docs/benchmark.md) |
| Build a wheel or prepare a release | [Release readiness](https://github.com/agent-axiom/shapewitness/blob/main/docs/release/README.md) |
| Understand null, missing, arrays, and tie-breaking | [Feature model](https://github.com/agent-axiom/shapewitness/blob/main/docs/feature-model.md) |
| Verify selected bytes and coverage explanations | [Provenance](https://github.com/agent-axiom/shapewitness/blob/main/docs/provenance.md) |
| Check strict input rules, resource limits, and privacy | [Limits & privacy](https://github.com/agent-axiom/shapewitness/blob/main/docs/limits-privacy.md) |
| Understand the implementation or contribute | [Architecture](https://github.com/agent-axiom/shapewitness/blob/main/docs/architecture.md) · [Development](https://github.com/agent-axiom/shapewitness/blob/main/docs/development.md) |
| Work on this repository with an agent | [Agent guide](https://github.com/agent-axiom/shapewitness/blob/main/AGENTS.md) |
| Compare the scope with JSONLKit and jselect | [Related tools](https://github.com/agent-axiom/shapewitness/blob/main/docs/related-tools.md) |

**Know the boundaries:** this is greedy structural coverage, not a statistically
representative sample, an optimal minimum set, or a schema guarantee. Selected rows
retain private data; reports can expose property names. [Details](https://github.com/agent-axiom/shapewitness/blob/main/docs/limits-privacy.md).

[Documentation index](https://github.com/agent-axiom/shapewitness/blob/main/docs/README.md) · [Contributing](https://github.com/agent-axiom/shapewitness/blob/main/CONTRIBUTING.md) ·
[Security](https://github.com/agent-axiom/shapewitness/blob/main/SECURITY.md) · [Changelog](https://github.com/agent-axiom/shapewitness/blob/main/CHANGELOG.md) · [MIT license](https://github.com/agent-axiom/shapewitness/blob/main/LICENSE)
