# ShapeWitness

[![CI](https://github.com/agent-axiom/shapewitness/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/agent-axiom/shapewitness/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/shapewitness.svg)](https://pypi.org/project/shapewitness/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![MIT license](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Runtime dependencies: 0](https://img.shields.io/badge/Runtime_dependencies-0-success)](pyproject.toml)

**Small JSONL fixtures that show the shapes your code needs to handle.**

`head -n 20` often gives you twenty happy-path rows. ShapeWitness keeps the records
with missing fields, nulls, empty collections, and mixed types, then explains why
each row was selected.

- **Real records:** original bytes, numeric precision, whitespace, and line endings
- **Explainable coverage:** observed structural features, uncovered gaps, source hashes
- **Reproducible and local:** deterministic selection, bounded disk spooling, no network calls

## Install

Python 3.10+ with SQLite support. [Available on PyPI](https://pypi.org/project/shapewitness/):

```sh
python -m pip install shapewitness
# Isolated CLI alternatives:
uvx shapewitness --help
pipx install shapewitness
```

For a source checkout, use `python -m pip install .`. Pin a version or reviewed
commit for reproducibility. See [release guidance](docs/release/README.md).

## Ten-second demo

From a checkout:

```sh
shapewitness examples/events.jsonl -n 4 --report coverage.json > fixture.jsonl
# shapewitness: 4/6 rows; 19/19 observed features; complete
```

Lines **1, 3, 4, and 5** survive. See the [input](examples/events.jsonl),
[selected fixture](examples/witness.jsonl), and [explanation](examples/coverage.json).
Use `--require-complete` to fail CI when the selected rows leave observed features uncovered.
In this source checkout, opt into `--number-mode syntax` for integer versus fractional/exponent witnesses;
see the [numeric feature model](docs/feature-model.md#optional-numeric-syntax-coverage).

## Read next

| I want to… | Start here |
| --- | --- |
| Use the CLI, pipes, or Python API | [Usage](docs/usage.md) |
| Build pytest fixtures, test ETL, or reproduce an importer bug | [Recipes](docs/recipes/README.md) |
| Inspect a reproducible head/random comparison | [Synthetic benchmark](docs/benchmark.md) |
| Build a wheel or prepare a release | [Release readiness](docs/release/README.md) |
| Understand null, missing, arrays, and tie-breaking | [Feature model](docs/feature-model.md) |
| Verify selected bytes and coverage explanations | [Provenance](docs/provenance.md) |
| Check strict input rules, resource limits, and privacy | [Limits & privacy](docs/limits-privacy.md) |
| Understand the implementation or contribute | [Architecture](docs/architecture.md) · [Development](docs/development.md) |
| Work on this repository with an agent | [Agent guide](AGENTS.md) |
| Compare the scope with JSONLKit and jselect | [Related tools](docs/related-tools.md) |

**Know the boundaries:** this is greedy structural coverage, not a statistically
representative sample, an optimal minimum set, or a schema guarantee. Selected rows
retain private data; reports can expose property names. [Details](docs/limits-privacy.md).

[Documentation index](docs/README.md) · [Contributing](CONTRIBUTING.md) ·
[Security](SECURITY.md) · [Changelog](CHANGELOG.md) · [MIT license](LICENSE)
