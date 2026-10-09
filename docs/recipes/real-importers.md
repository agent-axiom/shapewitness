# Real sqlite-utils and dlt regression fixtures

[Recipes](README.md) · [Runnable comparison](../../examples/recipes/importer_regression.py) ·
[Integration tests](../../tests/integration/test_importers.py)

This is a small, executable pilot using **real importers and synthetic data**. It is
not evidence of adoption by either project or a benchmark on production exports.
The public [orders fixture](../../examples/integrations/orders.jsonl) has 10 records:
repeated happy paths, absent/null members, empty objects/arrays, mixed numeric/text
values, nested line items, and a top-level column introduced late in the stream.

## Run from a checkout

Use a virtual environment, then install ShapeWitness and the optional test packages:

```sh
python -m pip install --no-deps .
python -m pip install -r tests/integration/requirements.txt
python examples/recipes/importer_regression.py sqlite-utils
python examples/recipes/importer_regression.py dlt
python examples/recipes/importer_regression.py sqlite-utils --number-mode syntax
python examples/recipes/importer_regression.py dlt --number-mode syntax
python -m unittest discover -s tests/integration -v
```

The integration versions are sqlite-utils 4.2.1, dlt 1.31.0, and DuckDB 1.5.6.
The dedicated Linux/Python 3.12 CI job runs both recipes and the optional suite.
These packages are not runtime dependencies of ShapeWitness; transitive development
packages are resolved by pip. Upgrade importer versions deliberately and rerun the
behavior assertions, since their inference rules can change.

Both recipes retain lines **1, 3, 4, 5, 6, and 7**, covering **28/28 observed
structural features**. Each prints a JSON summary with the source digest and whether
its actual importer comparisons passed. To keep the raw selection and its full report:

```sh
shapewitness examples/integrations/orders.jsonl -n 6 --require-complete \
  --output orders-fixture.jsonl --report orders-coverage.json
```

Use fresh output paths. Original row bytes are preserved; importer parsing and
storage can still change numeric precision, types, and null/missing distinctions.

## What is verified

Before importing, the recipe checks complete structural coverage and verifies each
selected row against its original physical line, byte offset/length, and SHA-256.
Incomplete coverage and invalid JSON fail before either import begins.

- sqlite-utils runs its actual `insert --nl --alter --pk id --batch-size 1` command
  against two fresh local SQLite databases. The recipe compares column definitions,
  retained record values, and SQLite storage classes. One-record batches exercise
  the late `discount` column; a regression test verifies that both full and reduced
  inputs fail with the expected missing-column error if `--alter` is omitted.
- dlt runs two isolated local DuckDB pipelines. The recipe compares normalized
  columns/types/nullability, retained parent values, and child line items using the
  business `id` and array index. Generated load IDs differ between loads and are
  intentionally excluded. Unexpected normalized tables cause a failure instead of
  being silently ignored. Optional dlt telemetry is disabled before import, and
  project, pipeline, and database state live in temporary directories.
- Reviewed assertions check specific outcomes too, such as the pending-total variant
  column, empty item lists, missing email, the late discount, and two ordered child
  rows belonging to the first order. Comparing two outputs alone would miss a bug
  that affects both equally.

The scripts clean up their temporary databases/state. They target this orders schema,
not every possible normalized dataset. For another pipeline, adapt the stable row
identity, normalized-table projection, expected outputs, and failure assertions.

## Complete shape coverage does not prove importer equivalence

The optional suite contains passing tests that deliberately demonstrate failures of
that inference:

1. **Numeric inference:** `1` and `1.5` are both the structural feature `number`.
   Selecting one row can change sqlite-utils' batch-inferred column from `REAL` to
   `INTEGER`, or remove dlt's `amount__v_double` variant column entirely.
2. **Cross-row constraints:** two otherwise same-shaped records with the same primary
   key fail the full sqlite-utils import. A structurally complete one-row witness
   succeeds and therefore does not reproduce the original failure.

### Opt into numeric-syntax witnesses

`--number-mode syntax` distinguishes integer tokens from tokens with a fraction or
exponent. The optional suite verifies that reducing three rows with amounts `1`,
`1.5`, and `2` to the first two now preserves sqlite-utils' batch-inferred `REAL`
column and dlt's `amount__v_double` variant. It compares schemas, retained values,
and SQLite storage classes using real imports. Integral exponent syntax (`1e0`)
is tested too: sqlite-utils infers `REAL`, while dlt coerces it to the existing
integer column. Existing default-mode counterexamples remain in the suite.

The [comparison recipe](../../examples/recipes/importer_regression.py) accepts the
same option. In Python, use `select(source, number_mode="syntax")`. This is an
explicit feature-model change with report format 2; see
[numeric-syntax coverage](../feature-model.md#optional-numeric-syntax-coverage).

It is still possible to lose failures: a new regression shows a full sqlite-utils
import failing on an integer above SQLite's signed 64-bit range, while a complete
syntax-mode witness keeps only a small integer and succeeds. Numeric ranges,
precision and cross-row relationships remain outside the declared feature model.
Another negative test uses amounts `1`, `1e0`, then `1.5`: syntax mode selects the
first two, but dlt coerces `1e0` to an integer and loses the fractional variant column.
`1e0` and `1.5` share the same `float` syntax kind; syntax coverage cannot establish
which values an importer will coerce.

Keep value-sensitive, ordering, duplicate-key, cross-record, and failure-predicate
cases separately. Run the real importer and compare the behavior you need; a 100%
structural score alone is insufficient. `--require-complete` checks only ShapeWitness'
declared feature model. It does not require importer success or semantic equivalence.

References: [sqlite-utils CLI](https://sqlite-utils.datasette.io/en/stable/cli.html),
[dlt DuckDB destination](https://dlthub.com/docs/dlt-ecosystem/destinations/duckdb),
[dlt telemetry](https://dlthub.com/docs/reference/telemetry).
