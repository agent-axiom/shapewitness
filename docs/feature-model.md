# Feature model and selection

[Home](../README.md) · [Documentation index](README.md)

A feature is a **path plus a kind**. By default, the kinds are `object`, `array`, `string`,
`number`, `boolean`, `null`, `missing`, `empty-object`, and `empty-array`.
Integers and fractional/exponent numbers share the `number` kind.

### Optional numeric-syntax coverage

Available since the published 0.1.2 release.

Use `--number-mode syntax` (Python: `select(source, number_mode="syntax")`) when
integer versus fractional/exponent syntax matters to an importer. It replaces the
`number` kind with two kinds at each path:

- `integer`: JSON integer syntax, including `0`, `-0`, and arbitrarily large integers
- `float`: JSON syntax with a fraction or exponent, including `1.0`, `1e0`, and `1E-2`

These are **syntax categories**, not computed numeric values or range guarantees.
The parser still never converts numbers: `1e9999999` and long decimal lexemes remain
valid and byte-identical. Booleans remain `boolean`; numeric strings remain `string`.
No mode accepts non-JSON constants such as `NaN` or `Infinity`.

For two otherwise same-shaped rows containing `1` and `1.5` at the same path, the
default mode can keep just the first. Syntax mode needs both to cover that path.
This can need more rows, bytes, features, and associations; the usual limits and
partial-coverage reporting still apply. `--require-complete` checks the chosen model.

Without pins, syntax mode emits report **format 2** with
`feature_model: "json-structure-number-syntax-v1"` and `options.number_mode: "syntax"`.
Without pins, default `--number-mode json` keeps the original format-1 report and selection exactly.
Consumers must check the format/model before interpreting feature kinds or comparing
coverage scores. The deterministic greedy algorithm itself is unchanged.

This mode addresses the tested integer/float inference examples in the
[real-importer recipe](recipes/real-importers.md). It does not preserve value ranges,
precision, signed zero, duplicate primary keys, order-dependent inference, or
combinations of values/features. Run downstream behavior checks for those needs.

### Paths and missing members

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

### Retaining known cases

Nonempty pins add a mandatory, SHA-256 checked selection stage before greedy
coverage. Pinned rows are selected in source order, count toward both budgets,
and may contribute no new features. Report format 3 records each selection reason
and the same explicit numeric feature model; the feature universe does not change.
See [pinning behavior and failures](usage.md#keep-a-known-problem-row).
