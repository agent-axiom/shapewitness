# Working on ShapeWitness

ShapeWitness selects unchanged JSONL rows that cover an explicitly defined set of
observed structural features. It is a Python 3.10+ CLI/library with no runtime or
core-test dependencies outside the standard library. Release tooling and the optional
pytest recipe have separate development dependencies.

## Read only what you need

- Overview and runnable demo: [README](README.md)
- Public behavior: [usage](docs/usage.md), [feature model](docs/feature-model.md), [provenance](docs/provenance.md)
- Trust/resource contract: [limits and privacy](docs/limits-privacy.md)
- Internals: [architecture](docs/architecture.md)

## Repository map

- `src/shapewitness/core.py`: parsing, limits, private SQLite spool, feature extraction, greedy selector, reports
- `src/shapewitness/cli.py`: arguments, stream routing, exclusive output creation, exit status
- `tests/test_core.py`: edge cases, limit failures, seeded independent feature/selection oracle
- `tests/test_cli.py`: process-level interface, output safety, hash-seed determinism
- `tests/test_resources.py`: Linux-only bounded-address-space smoke test
- `examples/`: synthetic input, reproducible outputs, and runnable recipes
- `scripts/`: benchmark, package-description generation, and local distribution checks
- `docs/release/`: release checklist and an inactive publisher template
- `benchmarks/`: synthetic corpus and disclosed measured results

## Preserve these contracts

1. Output rows are byte-identical, unique source lines in original order.
2. Selection is deterministic; ties prefer the first physical line.
3. Missing-member coverage is local to an existing object and uses the full observed vocabulary.
4. Input/discovery limits fail before output; selection budgets report uncovered features explicitly.
5. No telemetry, network access, evaluation of input, or raw input values in errors.
6. Report format and feature semantics must be versioned when compatibility changes.
7. Never describe the result as representative, minimum/optimal, or a guarantee about unseen data.

Use synthetic fixtures, especially in issues and tests. Do not add user exports,
credentials, or confidential data. Keep README short; details belong in linked docs.
Badges must reflect real workflows or package metadata.

## Validate a change

```sh
python -m pip install --no-deps -e .
python -m unittest discover -s tests -v
python -m compileall -q src tests
shapewitness examples/events.jsonl -n 4 --require-complete --status json
```

Add a regression test for each bug fix. For changed selection/report behavior,
reproduce and review both committed example artifacts. Run packaging checks for
metadata/build changes; see [development](docs/development.md). Check CI on the
exact pushed commit. Publishing a registry release is a separate maintainer action.
