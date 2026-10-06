# ShapeWitness

**Turn a JSONL export into a small fixture that shows the shapes your code needs to handle.**

ShapeWitness selects real, unchanged input rows to cover observed paths, types,
nulls, missing members, and empty collections. Each choice comes with a coverage
explanation and byte-level provenance. It runs offline with **zero runtime dependencies**.

Use it when `head -n 20` gives you twenty happy-path rows but your parser also needs
the record with a null user, missing email, empty tags, or an unexpected field type.

> Structural coverage is not statistical representativeness. This is a deterministic
> greedy heuristic, not an optimal/minimum set cover, a JSON Schema, or a guarantee
> about data you have not observed. Review selected data before sharing it.

## Ten-second demo

Requires Python 3.10+ with SQLite support. From a checkout:

```sh
python -m pip install .
shapewitness examples/events.jsonl -n 4 --report coverage.json > fixture.jsonl
```

Stderr:

```text
shapewitness: 4/6 rows; 19/19 observed features; complete
```

The fixture contains original lines **1, 3, 4, and 5**. Ordinary repeated records
are skipped; the rows with absent, null, empty, and mixed-type values survive.
See the committed [input](examples/events.jsonl), [fixture](examples/witness.jsonl),
and [coverage report](examples/coverage.json).

No PyPI release is claimed. Install from a checkout, or directly from GitHub:

```sh
python -m pip install 'git+https://github.com/agent-axiom/shapewitness.git'
```

For reproducible deployments, pin a reviewed commit instead of the moving default
branch. Installation may download build tooling; the installed tool makes no network calls.

## Useful workflows

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

## Exactly what is covered?

A feature is a **path plus a kind**. The kinds are `object`, `array`, `string`,
`number`, `boolean`, `null`, `missing`, `empty-object`, and `empty-array`.
Integers and fractional/exponent numbers share the `number` kind.

Paths are JSON arrays in the report:

- `[]`: the root value
- `["user", "email"]`: that object member
- `["events", null, "code"]`: `code` in any object inside the `events` array
- `["*"]`: a literal key named `*`, distinct from the `null` array wildcard

Keys containing dots, slashes, empty strings, or Unicode are unambiguous. Array
indexes collapse to a wildcard: length, ordering, exact index, and co-occurrence
combinations are not covered. Scalar JSON values and top-level arrays are supported.

**Missing is local to an existing object.** The tool first learns the union of
immediate keys observed at each object path across the entire input. It then records
`missing` when an object at that path lacks one of those keys. For example:

```jsonl
{"user":{}}
{"user":{"email":"ada@example.test"}}
{}
{"user":null}
```

Line 1 witnesses missing `user.email`; line 3 witnesses missing `user`. Lines 3 and 4
do not claim that `user.email` is missing because its parent is absent or not an
object. Keys discovered late in the file still count. Within an array, one object
can witness a member's presence and another its absence in the same row. An empty
array does not stand in for a missing member inside an array element.

### How rows are chosen

1. Read and validate the input once; spool raw lines and learn the key vocabulary.
2. Re-read the private spool to construct exact feature-to-row incidence, including
   missing members relative to the complete observed vocabulary.
3. Repeatedly pick the row covering the most **currently uncovered** features.
   Equal gains prefer the earliest physical input line. There are no random seeds.
4. Stop at complete observed coverage, the row budget, or the output-byte budget.
   Emit selected rows in original source order.

A row that cannot fit the remaining output-byte budget is excluded; selection then
continues with the next best feasible row. This is not byte-optimal selection.
The same bytes and options yield the same fixture and report, regardless of Python
hash seed. Reordering the input can change the result. Duplicate shapes do not add
weight just because they are common.

## Trust the bytes, inspect the explanation

Rows are **never reserialized**. Spaces, key order, decimal lexemes, very large
integers, CRLF endings, and an absent final newline are retained. The parser validates
numeric syntax using a type marker, without floating-point conversion or a digit-size
limit. The output is an ordered subsequence of original physical lines.

The report has a versioned format (`format_version: 1`) and includes:

- SHA-256 of the entire input byte stream, including explicitly skipped blank lines
- Each selected row's 1-based physical line, 0-based byte offset, byte length, and SHA-256
- Selection rank, all covered feature IDs, and newly covered IDs explaining each choice
- Every observed feature, coverage state, and explicit uncovered feature IDs
- Effective limits, selection budget, and why selection stopped

Feature IDs are deterministic for identical input, but are report-local, not stable
identifiers across different datasets. They index the report's `features` collection.
A digest is an identity check, not proof of authenticity. Retain the original input
if you need to verify or recover the exact source records later.

## Python library

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

## Input and resource contract

UTF-8 JSONL means one complete JSON value on every physical line. By default, the
tool rejects blank lines, malformed JSON, duplicate object keys, a UTF-8 BOM, invalid
UTF-8, non-finite constants (`NaN`, `Infinity`), and unpaired Unicode surrogates.
It accepts LF and CRLF and a final line without a newline. Multiline JSON and a single
JSON array spread over multiple lines are not JSONL. Nothing is silently repaired.
Errors identify the line and category without echoing raw values.

Discovery limits are **fail-closed**: exceeding one returns an error, never a claim
about a truncated input. Row/output budgets instead produce explicitly partial
coverage. Defaults (all byte counts are binary bytes):

| Bound | Default |
| --- | ---: |
| Physical line, including ending | 1 MiB |
| Total input | 256 MiB |
| Records | 100,000 |
| Container nesting | 64 (hard configurable ceiling: 256) |
| Value nodes per record | 100,000 |
| Distinct features | 10,000 |
| ASCII-escaped serialized path | 4,096 bytes |
| Record/feature associations | 2,000,000 |
| SQLite main spool file | 512 MiB |
| Selected raw output | 16 MiB |

`shapewitness --help` exposes every bound. The default row budget is 20; `max_rows`
must be between zero and the configured record cap.

The input is not held entirely in RAM. One decoded line, the bounded observed
vocabulary, SQLite's cache (8 MiB target), and the selected result/report reside in
memory. Raw rows and feature incidence live in a private temporary SQLite database.
Memory also depends on Python object overhead, per-line fanout, and report size;
these are **not an exact RSS limit**. SQLite may use extra transient storage beyond
the main-file cap, and free disk space is still required. Use OS/container limits
when processing hostile input or when a hard process/disk quota is required.

The test suite includes a 30 MB-class stream under a 192 MiB Linux address-space
limit. This is a smoke test, not a universal memory or throughput claim. Increasing
limits can make work substantially more expensive. Selection uses an indexed
incremental gain table; worst-case work still grows with feature incidence and the
number of selected rows. This MVP targets bounded fixture jobs, not unbounded
multi-terabyte analytics.

All input/limit errors occur before data output starts. The spool is removed on
normal exit and handled exceptions; forced termination or machine failure may leave
temporary files. Output/report writes are exclusive but are not a multi-file atomic
transaction. Disk, pipe, or permission failures during delivery can leave partial
artifacts; treat a nonzero error exit accordingly.

## Privacy

No telemetry, network calls, API keys, external models, or persistent index. Input is
spooled locally in a private temporary directory; use `--temp-dir` to choose its disk.
Cleanup is ordinary deletion, not secure erasure. Selected rows retain original data,
including any secrets or personal information. Reports omit scalar values and source
filenames, but **property names, structure, hashes, and provenance may also be sensitive**.
ShapeWitness is not a redactor or anonymizer.

## Where this fits

- [JSONLKit](https://github.com/tinytoolkit-org/jsonlkit-cli) provides a broader JSONL
  workbench: validation, statistics, conversion, repair, and sampling. ShapeWitness
  focuses on explainable selection for a defined structural feature model.
- [jselect](https://github.com/keltokhy/jselect) selects task-relevant, source-linked
  evidence under a context budget. ShapeWitness uses no semantic task or relevance
  model; its budget is rows/bytes and its target is observed structural features.

These tools are useful neighbors. This comparison describes their documented scope,
not a speed, quality, or uniqueness claim. ShapeWitness does not cover string enums,
value ranges, rare business outcomes, relationships across records, or meaningful
semantic diversity. Use targeted fixtures and domain tests alongside it.

## Development

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

See [architecture](docs/architecture.md), [contributing](CONTRIBUTING.md), and
[security guidance](SECURITY.md). MIT licensed. Version 0.1 is an initial release;
report/feature semantics are versioned and may evolve in future releases.
