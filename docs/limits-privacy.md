# Input limits and privacy

[Home](../README.md) · [Documentation index](README.md)

## Input and resource contract

UTF-8 JSONL means one complete JSON value on every physical line. By default, the
tool rejects blank lines, malformed JSON, duplicate object keys, a UTF-8 BOM, invalid
UTF-8, non-finite constants (`NaN`, `Infinity`), and unpaired Unicode surrogates.
It accepts LF and CRLF and a final line without a newline. Multiline JSON and a single
JSON array spread over multiple lines are not JSONL. Nothing is silently repaired.
Errors identify the line and category without echoing raw values.

Discovery limits are **fail-closed**: exceeding one returns an error, never a claim
about a truncated input. Row/output budgets instead produce explicitly partial
coverage. Explicit pins are mandatory: if their rows/bytes exceed those budgets,
the request fails before output rather than dropping a pin or exceeding a budget.
Defaults (all byte counts are binary bytes):

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
Traversal uses one lazy iterator per active ancestor, so its sibling bookkeeping
does not grow with a wide array/object before enforcing the node limit. Parsing
still allocates the decoded line. Memory also depends on Python object overhead,
per-line fanout, and report size;
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
