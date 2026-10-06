# ETL regression with reviewed golden output

[Recipes](README.md) · [Source](../../examples/recipes/etl_regression.py) ·
[Golden output](../../examples/recipes/etl_expected.json)

## Pain

An ETL refactor changes the handling of missing, null, or empty values. Full-export
runs are noisy, while a tiny happy-path fixture misses those branches.

## Run

```sh
python examples/recipes/etl_regression.py
# ETL regression: 4 reviewed outputs match; source lines 1, 3, 4, 5
```

The recipe selects the same four structural witnesses, applies a small example
transformation, then compares its normalized output against a reviewed golden file.
Any difference or incomplete structural coverage exits nonzero. Change the null
user branch from `null` to `missing` to see the regression check fail, then revert it.

## Adapt

Call your old and new transformation on the exact same selected bytes, and review
meaningful differences before updating a golden file. Keep value assertions in the
application layer; ShapeWitness does not infer the correct transformation.

A reduced fixture cannot establish equivalence over the full export. Run full-data
checks when required, especially for aggregations, ordering, and cross-row joins.
