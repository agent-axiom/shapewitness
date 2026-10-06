# ShapeWitness documentation

[Project overview and quick start](../README.md)

## Use the tool

- [Usage](usage.md): CLI workflows, exit codes, failure examples, Python API
- [Feature model](feature-model.md): path notation, local missing-member semantics, greedy selection
- [Provenance](provenance.md): exact bytes, SHA-256, report fields, verification boundaries
- [Limits and privacy](limits-privacy.md): strict JSONL contract, every default cap, memory/disk behavior, sensitive outputs
- [Related tools](related-tools.md): scope alongside JSONLKit and jselect

- [Recipes](recipes/README.md): pytest fixtures, ETL regression, importer repro
- [Synthetic comparison](benchmark.md): disclosed coverage and timing against head/reservoir

## Work on the tool

- [Architecture](architecture.md): data flow, invariants, complexity, compatibility
- [Development](development.md): installation, tests, packaging, CI matrix
- [Agent guide](../AGENTS.md): short repository map and validation checklist
- [Contributing](../CONTRIBUTING.md): change expectations
- [Security](../SECURITY.md): trust boundaries and reporting
- [Changelog](../CHANGELOG.md): implemented changes
- [Release readiness](release/README.md): build candidates, metadata checks, publisher setup checklist

Examples and CLI commands assume the repository root as the working directory.
The [committed fixture](../examples/witness.jsonl) and [report](../examples/coverage.json)
are generated from the [synthetic example input](../examples/events.jsonl).
