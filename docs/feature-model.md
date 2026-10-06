# Feature model and selection

[Home](../README.md) · [Documentation index](README.md)

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
