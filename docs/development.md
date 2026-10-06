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
builds/installs the package. Tests include a seeded independent feature oracle,
greedy-choice verification, cross-hash-seed determinism, precision-preserving bytes,
strict failures, nested missing semantics, provenance, and resource-bound checks.

See [architecture](architecture.md), [contributing](../CONTRIBUTING.md), and
[security guidance](../SECURITY.md). MIT licensed. Version 0.1 is an initial release;
report/feature semantics are versioned and may evolve in future releases.

Release tooling and the optional pytest recipe are separate development dependencies.
See [release readiness](release/README.md) for building and checking candidates;
see [recipes](recipes/README.md) for their runnable commands.
