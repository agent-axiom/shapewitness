# Recipes

[Home](../../README.md) · [Documentation index](../README.md)

Most runnable examples use the repository's public, synthetic data. The opt-in
countries case uses a pinned, licensed external dataset. Run commands from the
repository root after installing ShapeWitness. Review real data before
committing fixtures or sharing bug reports; the tool does not redact anything.

1. [Pytest fixtures](pytest-fixtures.md): generate a structural fixture and retain its provenance
2. [ETL regression](etl-regression.md): compare a reviewed transformation result against a golden output
3. [Importer bug reproduction](importer-bug-repro.md): turn a selected failing row into an exact repro
4. [sqlite-utils and dlt](real-importers.md): execute full and reduced inputs, compare
   retained behavior, and test cases where structural coverage is insufficient
5. [Structural regression and pinned rows](structural-regression.md): compare a reviewed
   inventory, retain a known value-sensitive row, and run pytest/CI gates
6. [Public countries through sqlite-utils](public-countries.md): reproduce a real-data
   importer failure, compare retained behavior, and measure modest reduction and costs

The first three examples are exercised by the release-readiness workflow. The
pytest recipes need pytest. The real-importer recipe has a separate CI job with
pinned optional dependencies; ShapeWitness and its core tests remain
standard-library-only.
