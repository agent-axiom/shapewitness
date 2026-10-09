# Byte preservation and provenance

[Home](../README.md) · [Documentation index](README.md)

Rows are **never reserialized**. Spaces, key order, decimal lexemes, very large
integers, CRLF endings, and an absent final newline are retained. The parser validates
numeric syntax using a type marker, without floating-point conversion or a digit-size
limit. The output is an ordered subsequence of original physical lines.

The report has a versioned format and includes:

- SHA-256 of the entire input byte stream, including explicitly skipped blank lines
- Each selected row's 1-based physical line, 0-based byte offset, byte length, and SHA-256
- Selection rank, all covered feature IDs, and newly covered IDs explaining each choice
- Every observed feature, coverage state, and explicit uncovered feature IDs
- Effective limits, selection budget, and why selection stopped

Default numeric coverage retains `format_version: 1` and its existing report fields.
Without pins, opt-in `--number-mode syntax` uses `format_version: 2`, declares
`feature_model: "json-structure-number-syntax-v1"`, and records
`options.number_mode: "syntax"`. Its `integer`/`float` feature kinds replace `number`;
all other report fields retain their meaning. Check the format/model before
interpreting kinds or comparing coverage. See the [feature model](feature-model.md).

Nonempty `--pin-row` / `pins=` uses format **3** with the same explicit numeric
feature model and a pinned-first algorithm. `options.pins` stores the reviewed line
and digest pairs in source order. Each report row and Python `Witness` has a
`selection_reason` of `pinned` or `greedy`. A pinned row may add zero new features;
its bytes still consume the selection budgets. Empty pins preserve formats 1/2.

Feature IDs are deterministic for identical input, but are report-local, not stable
identifiers across different datasets. They index the report's `features` collection.
A digest is an identity check, not proof of authenticity. Retain the original input
if you need to verify or recover the exact source records later.
