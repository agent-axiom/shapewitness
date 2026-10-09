# Usage and Python API

[Home](../README.md) · [Documentation index](README.md)

## Command line

```sh
# Pipes need no seekable input. Data is privately spooled on disk.
cat export.jsonl | shapewitness -n 12 > fixtures/export.jsonl

# A CI gate: exit 3 if the row budget cannot cover all observed features.
shapewitness export.jsonl -n 12 --require-complete \
  --output fixtures/export.jsonl --report reports/export.json

# Machine-readable stderr status, with a separate full report.
shapewitness export.jsonl --status json --report report.json > sample.jsonl

# Keep integer and fractional/exponent witnesses separately (report format 2).
shapewitness export.jsonl --number-mode syntax --require-complete \
  --output numeric-fixture.jsonl --report numeric-coverage.json

# Inspect coverage without selecting rows.
shapewitness export.jsonl -n 0 --report inventory.json --status quiet

# Explicitly opt into ignoring blank physical lines.
shapewitness export.jsonl --skip-blank-lines > sample.jsonl

# Set boundaries for a particular job; limits fail rather than truncate discovery.
shapewitness export.jsonl -n 10 --max-records 50000 \
  --max-input-bytes 67108864 --max-spool-bytes 268435456 > sample.jsonl
```

`--output` and `--report` only create new files. Existing paths, including symlinks,
are refused. Choose new filenames or remove old artifacts yourself. Shell redirection
is controlled by your shell: `> existing.jsonl` can truncate that file before the tool runs.
Never redirect output onto the input file.

### Exit status

- **0**: valid input processed; coverage may be partial unless `--require-complete` is set
- **1**: the downstream output pipe closed
- **2**: invalid input, invalid arguments, resource limit, or I/O failure
- **3**: successful selection with uncovered features under `--require-complete`
- **4**: observed inventory changed under `--require-unchanged` (source checkout)
- **130**: interrupted

Status belongs to stderr; stdout contains JSONL only. `--status json` provides a
single JSON success/error record for processing failures; command-line syntax
errors from `argparse` use its normal text format. `--status quiet` hides success
status, but still shows errors. Exit 3 still writes the selected rows and report.

### Deliberate failure cases

```sh
printf 'NaN\n' | shapewitness --status json           # exit 2: invalid_json
printf '{"id":1,"id":2}\n' | shapewitness             # exit 2: duplicate_key
printf '{}\n\n' | shapewitness                        # exit 2: blank_line
shapewitness examples/events.jsonl -n 2 --require-complete
# exit 3: 14/19 features covered; the two selected rows are still emitted
```

## Compare a structural baseline

The comparison API and flags below are available in this source checkout, pending
release. Install a reviewed commit rather than expecting them in PyPI 0.1.2.

```sh
# Capture the full observed inventory without selecting rows.
shapewitness baseline.jsonl -n 0 --report baseline.json --status quiet
# Compare another export; emit the full inventory and a separate delta artifact.
shapewitness current.jsonl -n 0 --baseline baseline.json --require-unchanged \
  --report current.json --comparison-report delta.json --status json
```

`--baseline` compares all observed features, including those left uncovered by the
selection budget. `--require-unchanged` exits **4** if any feature was added or
removed. Without that flag, changes are reported but do not fail the command.
Exit 3 takes precedence if both `--require-complete` and `--require-unchanged` fail.
Both gate failures still write their outputs. `--comparison-report` and
`--require-unchanged` require `--baseline`.

The ordinary coverage report is unchanged. The separate delta report has its own
`format_version: 1`, `comparison_model: "observed-structure-diff-v1"`, the shared
feature model, both input SHA-256 hashes, sorted `added_features` and
`removed_features` lists, an `unchanged_features` count, and a `changed` boolean.
Each listed feature contains only `path` and `kind`. Report-local feature IDs and
selection coverage are never used as identities. With a baseline, JSON stderr also
has a `comparison` summary with `changed` and added/removed counts.

Supported inputs are default format-1 reports (implicit `json-structure-v1`) and
syntax-mode format-2 reports (`json-structure-number-syntax-v1`). The two models
cannot be compared with each other, even if neither input contains numbers.
Unknown formats, conflicting model metadata, duplicate/malformed feature entries,
invalid hashes/counts, or malformed JSON fail with exit 2 before any output. The CLI
limits a baseline report to 16 MiB. Python's `read_report` accepts an explicit
`max_bytes=`. Inventory checks do not authenticate a saved report or validate its
row provenance. Keep baselines under review in source control.

Missing-member features use each input's own observed key vocabulary: a new key
can add both its type and `missing` for unchanged older rows. Added/removed features
are observed structural changes, not schema violations. Equal inventories can still
hide changes in values, frequency, array lengths, combinations, and importer behavior.
A changed input hash with an unchanged inventory is normal. Review intended changes
before replacing a baseline; keep application assertions as a separate CI check.

```python
from shapewitness import compare_reports, read_report, select

with open("baseline.json", "rb") as source:
    baseline = read_report(source)
with open("current.jsonl", "rb") as source:
    current = select(source, max_rows=0)
delta = compare_reports(baseline, current.report)
assert not delta["changed"], delta  # Contains property names; review before sharing.
```

## Python API

```python
from shapewitness import Limits, ShapeWitnessError, select

try:
    with open("events.jsonl", "rb") as source:
        result = select(source, max_rows=12, limits=Limits())
    with open("fixture.jsonl", "xb") as target:
        result.write_jsonl(target)
    print(result.report["coverage"])
    for row in result.rows:
        print(row.line, row.offset, row.sha256, row.new_feature_ids)
except ShapeWitnessError as error:
    print(error.code, error.line, str(error))
```

The library takes a binary stream with `readline(size)`, including non-seekable pipes.
It returns only after full validation and selection. `Result.rows` are in source
order; `selection_rank` preserves greedy order. `temp_dir=` chooses the private
spool's parent directory. `skip_blank_lines=True` is the explicit blank-line opt-in.
`number_mode="syntax"` opts into separate integer and fractional/exponent feature
kinds; `number_mode="json"` is the compatible default. See the
[feature model](feature-model.md#optional-numeric-syntax-coverage) for syntax rules,
report versioning, and limitations. No numeric values are converted in either mode.
