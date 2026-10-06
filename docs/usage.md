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
