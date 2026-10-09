# Development and verification

[Home](../README.md) · [Documentation index](README.md)

Python's standard library supplies parsing, hashing, SQLite, CLI handling, and tests.
That keeps the runtime small, audit-friendly, and easy to embed. Setuptools is a build
dependency only; no service, framework, or database installation is needed.

```sh
python -m pip install --no-deps -e .
python -m unittest discover -s tests -v
python -m compileall -q src tests
# Optional packaging check (requires the build frontend):
python -m build
```

CI tests Linux on Python 3.10, 3.12, and 3.14, plus macOS and Windows on 3.12, and
builds and independently installs both wheel and sdist on that same five-environment
matrix. Distribution checks clear `PYTHONPATH`, verify the installed module is outside
the source directory, and run the full core test suite plus the demo against each artifact. Tests include a seeded independent feature oracle,
greedy-choice verification, cross-hash-seed determinism, precision-preserving bytes,
strict failures, nested missing semantics, provenance, and resource-bound checks.

The separate `importers` CI job installs the pinned packages in
`tests/integration/requirements.txt` and runs
`python -m unittest discover -s tests/integration -v`. These tests use actual
sqlite-utils CLI imports and local dlt/DuckDB pipelines on synthetic data, including
negative cases. They are deliberately outside dependency-free core discovery.
See the [real-importer recipe](recipes/real-importers.md) for runnable examples.

The separate `regression` CI job runs the complete
[pytest/GitHub Actions recipe](recipes/structural-regression.md), preserving its
synthetic witness, inventory, delta, and expected-failure status artifacts. Release
readiness and the publisher's build stage run the recipe against the candidate wheel.
Pytest remains an optional development dependency, outside core test discovery.

See [architecture](architecture.md), [contributing](../CONTRIBUTING.md), and
[security guidance](../SECURITY.md). MIT licensed. Version 0.1 is an initial release;
report/feature semantics are versioned and may evolve in future releases.

Release tooling and the optional pytest recipe are separate development dependencies.
See [release readiness](release/README.md) for building and checking candidates;
see [recipes](recipes/README.md) for their runnable commands.
