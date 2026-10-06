# Recipes

[Home](../../README.md) · [Documentation index](../README.md)

Runnable examples use only the repository's public, synthetic data. Run commands
from the repository root after installing ShapeWitness. Review real data before
committing fixtures or sharing bug reports; the tool does not redact anything.

1. [Pytest fixtures](pytest-fixtures.md): generate a structural fixture and retain its provenance
2. [ETL regression](etl-regression.md): compare a reviewed transformation result against a golden output
3. [Importer bug reproduction](importer-bug-repro.md): turn a selected failing row into an exact repro

All three examples are exercised by the release-readiness workflow. The pytest
recipe alone needs pytest; ShapeWitness itself and its core test suite remain
standard-library-only.
