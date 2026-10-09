# Review structural drift and retain a known regression

[Recipes](README.md) · [Runnable pytest recipe](../../examples/recipes/structural_regression.py)

## What this example checks

An importer needs a compact test fixture from a new JSONL delivery. Compare its
full observed structural inventory with a reviewed baseline, then preserve a
known value-sensitive problem row even though its shape is already covered.
Test application behavior separately, with explicit expected outputs.

The example uses synthetic orders only. It keeps these review artifacts in
[`examples/regression`](../../examples/regression/):

| Artifact | Purpose |
| --- | --- |
| `baseline.jsonl` | Original three-row synthetic delivery |
| `baseline-report.json` | Checked-in report for that original delivery |
| `current.jsonl` | New five-row delivery; changed values and a zero-quantity order |
| `pins.json` | Reviewed source line and expected SHA-256 for the known problem row |
| `current.witness.jsonl` | Reviewed refreshed fixture: current source lines 2, 3, and 5 |
| `drifted.jsonl` | Deliberate structural change for the negative gate example |

The baseline report's `tool_version` records its generation version. It is a
historical artifact, not something tests rewrite on each release. The tests
verify its source digest and compare inventories through `compare_reports`,
not through report-local feature IDs or a whole-report text comparison.

## Run the complete regression

From the repository root, with Python 3.10 or newer:

```sh
python -m pip install . pytest==9.1.1
python -m pytest -q examples/recipes/structural_regression.py
# 12 passed
```

Pytest is an optional development dependency. ShapeWitness itself still uses
only the standard library. To test an uninstalled checkout with pytest already
available, prefix the test command with `PYTHONPATH=src` on POSIX systems.

By default pytest keeps outputs in its temporary directory. On POSIX systems,
keep all review artifacts in an explicit fresh directory instead:

```sh
export SHAPEWITNESS_REGRESSION_ARTIFACTS="$(mktemp -d)"
python -m pytest -q examples/recipes/structural_regression.py
printf 'Review artifacts: %s\n' "$SHAPEWITNESS_REGRESSION_ARTIFACTS"
```

Use a fresh directory for every run. The recipe creates output directories and
JSON files exclusively so old results cannot be mistaken for new ones. Tests
never overwrite the checked-in baseline, pin manifest, or expected fixture.

The generated `current/` directory contains `witness.jsonl`, `report.json`, and
`comparison.json`. Each CLI case has its own directory with a JSON status and
exit code. The intentional drift case additionally retains the changed fixture
and comparison for review. Pin failures leave no CLI fixture/report/comparison
outputs; their captured error status is still useful for debugging.

## Why the pin matters

The default feature model groups numeric values as `number`. Changing a quantity
from 2 to 0 does not add a structural feature. The current input has the same
11 observed features as the baseline, despite different source bytes.

Without pins, a three-row budget selects current lines **1, 2, 3** with complete
observed structural coverage. The deliberately buggy application calculation,
`total_cents // quantity`, succeeds on those rows. It misses the zero-quantity
order on line 5.

The reviewed pin is:

```text
5:4fbbf6ce0e2f14041203066ea64a029aa7444ea40b7f0392f4b678bcce7c7fb0
```

That digest covers the exact raw physical line, including its final LF byte.
The tests load the expected digest from `pins.json`; they do not compute a new
expected digest from current data. Changing the value, changing LF to CRLF,
removing the final newline, deleting the row, or relocating it requires review.

Using `select(source, pins=(Pin(line=5, sha256=...),), max_rows=3)` selects the
pin first and fills remaining uncovered features greedily. It emits lines
**2, 3, 5** in source order. The pin counts against the same row and output-byte
budgets. Insufficient pin budgets, missing pins, and digest mismatches fail
before CLI outputs are created.

The pinned report uses format 3, states its `feature_model`, and records
`selection_reason` for each row. Pinning does not change the inventory feature
model, so this report can be compared with the format-1 baseline. The tests also
assert that the zero-quantity row has selection rank 1 even though it is emitted
last. A positive pin does not imply every remaining observed feature fits; keep
`coverage.complete` or `--require-complete` as a separate check.

The recipe proves the buggy function raises `ZeroDivisionError` on the retained
row. It also tests the example fixed importer, whose explicitly chosen behavior
is `unit_cents=None` for zero quantity. Assertions check the complete expected
outputs for the three retained orders, including missing/null/text note handling.
Replace that function and those expectations with your application's actual
importer and intended behavior.

## Inspect the CLI gates directly

The following POSIX-shell commands use the checked-in pin. Each command writes
to fresh paths; running the same command again against existing files fails
rather than overwriting them.

```sh
work="$(mktemp -d)"
pin='5:4fbbf6ce0e2f14041203066ea64a029aa7444ea40b7f0392f4b678bcce7c7fb0'
python -m shapewitness examples/regression/current.jsonl \
  -n 3 --pin-row "$pin" \
  --baseline examples/regression/baseline-report.json \
  --output "$work/current.jsonl" \
  --report "$work/current-report.json" \
  --comparison-report "$work/current-comparison.json" \
  --require-complete --require-unchanged --status json
# Exit 0: inventory unchanged; source bytes and selected rows can still differ.

status=0
python -m shapewitness examples/regression/drifted.jsonl \
  -n 4 --pin-row "$pin" \
  --baseline examples/regression/baseline-report.json \
  --output "$work/drifted.jsonl" \
  --report "$work/drifted-report.json" \
  --comparison-report "$work/drifted-comparison.json" \
  --require-complete --require-unchanged --status json || status=$?
test "$status" -eq 4
python -m json.tool "$work/drifted-comparison.json"
```

The deliberate drift adds `discount_code` on one row and changes the only
`note:null` value to a string. The comparison reports:

- Added: `discount_code:string` and `discount_code:missing`
- Removed: `note:null`

`missing` is local to an existing object and uses each input's full observed key
vocabulary. It is not a schema declaration. The original pinned line is unchanged
in this input, so pin validation still succeeds. Four selected rows cover the
changed inventory; this isolates drift exit **4** from incomplete-coverage exit
**3**. Invalid inputs or pin failures use exit **2**.

Inventory and coverage gates write their review artifacts before exiting 3 or 4.
Do not publish/use those outputs merely because files exist; respect the exit
status. If both gates fail, incomplete coverage takes precedence. The test suite
passes because it explicitly expects exit 4 for this deliberate negative example.
For a real current-delivery gate, let a nonzero exit fail CI rather than swallowing
it with `|| true`.

## GitHub Actions recipe

Save this as `.github/workflows/structural-regression.yml` in a repository that
contains the recipe and artifacts. This is a complete job; it runs the positive
and intentional-negative pytest cases and keeps their evidence even on failure.
It installs the local checkout so library and subprocess CLI tests use the same
build.

```yaml
name: Structural regression
on: [push, pull_request, workflow_dispatch]
permissions:
  contents: read
jobs:
  regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803 # v6
        with:
          persist-credentials: false
      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6
        with:
          python-version: '3.12'
      - run: python -m pip install . pytest==9.1.1
      - run: python -m pytest -q examples/recipes/structural_regression.py
        env:
          SHAPEWITNESS_REGRESSION_ARTIFACTS: ${{ runner.temp }}/shapewitness-regression
      - uses: actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f # v6
        if: always()
        with:
          name: structural-regression
          path: ${{ runner.temp }}/shapewitness-regression/
          retention-days: 7
          if-no-files-found: error
```

All uploaded rows in this demo are synthetic. Before adapting this job to real
exports, review whether the fixture, property names, provenance, and captured
input fragments may be stored as CI artifacts, who can read them, and for how
long. ShapeWitness does not redact values.

## Deliberate updates, not automatic approval

1. Keep the reviewed baseline report and pin manifest in version control. A
   passing test must not depend on regenerating either from the candidate input.
2. When a new delivery fails, inspect `comparison.json`, current report, and
   selected rows. Decide whether the added/removed features are expected and
   check application behavior separately. Increase the fixture budget only if
   the reviewed coverage requirement calls for it.
3. For an intentional baseline change, generate a candidate report into a new
   directory. Review its source digest, feature model, full feature delta, and
   changed fixture before promoting it with the corresponding input snapshot.
   Update the example's explicit inventory/row/output assertions as part of that
   same review; never turn them into assertions against freshly generated answers.
4. If a pinned row legitimately moves or changes, inspect its exact bytes and
   confirm it still exercises the known problem before updating its line/hash.
   For byte-safe review on this demo, print the candidate physical line and hash:

   ```sh
   python - <<'PY'
   import hashlib
   from pathlib import Path
   with Path('examples/regression/current.jsonl').open('rb') as source:
       for line_number, raw in enumerate(source, 1):
           if line_number == 5:
               print(repr(raw))
               print(hashlib.sha256(raw).hexdigest())
               break
       else:
           raise SystemExit('Reviewed physical line is missing')
   PY
   ```

   This is a manual review aid. It is not part of test setup and does not rewrite
   `pins.json`. The repository's `*.jsonl -text` Git attribute preserves fixture
   line endings across checkouts.

Equal observed inventories do not validate an application contract, establish
runtime equivalence, or prove every input value is handled. Pins retain known
cases, not unknown bugs. Keep separate value-boundary, ordering, relationship,
and full-input tests appropriate to your application.
