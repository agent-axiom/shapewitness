# Architecture and invariants

[Home](../README.md) · [Documentation index](README.md)

The implementation is deliberately small: `core.py` owns the selection contract;
`comparison.py` validates and compares inventories by path/kind;
`cli.py` adapts files/streams, exclusive output creation, reports, and exit status.
There is no hidden state, external configuration, plugin system, network client,
or dependency on locale, wall-clock time, or a random generator.

## Data flow

1. The reader requests at most `max_line_bytes + 1` bytes. A line larger than the
   explicit limit fails without an unbounded `readline()`. Total bytes, records,
   nesting, value nodes, path lengths, and vocabulary are bounded.
2. A lexical nesting check runs before `json.loads`. Numeric callbacks produce a
   type marker rather than computing an arbitrary numeric value. The opt-in syntax
   mode uses separate integer and fractional/exponent markers in both discovery
   passes; the default retains one `number` marker. Duplicate object
   keys and non-finite constants fail. Values remain in memory only for traversal.
   Lazy child iterators keep traversal bookkeeping O(nesting depth); wide objects
   and arrays do not allocate a second stack entry/path for every sibling before
   the node limit is checked. The parsed line itself is still materialized.
3. Each original line is copied into a private SQLite spool, alongside physical
   line and offset. The first pass collects observed object-member vocabularies.
   Requested pins are checked against exact spooled bytes and shared budgets.
4. A second spool pass builds exact row/feature edges. This is necessary because a
   key discovered on the last line can make its absence on the first line meaningful.
5. An indexed gain table orders rows by uncovered-feature count and physical line.
   When a feature becomes covered, all incident row gains decrement once. No
   per-record feature matrix is accumulated in Python memory. Explicit pins are
   selected first by source line, then the same gain table drives greedy completion.
6. Selected bytes plus the bounded report form a `Result`. The spool closes before
   CLI delivery. Only then does the CLI create outputs or emit stdout.

SQLite transactions and `journal_mode=OFF` are used only for disposable scratch
state, never a user database. A crash can destroy the scratch index; rebuilding
from the source is the recovery strategy. The max-page setting bounds the main
SQLite file, not every SQLite transient allocation. The private directory protects
scratch data from other ordinary users on the machine; it is not encrypted storage.

## Selection invariants

- Every output record is exactly one original physical line.
- Output records are unique and ordered by source position.
- Each greedy row adds at least one previously uncovered feature. Pinned rows may
  add none; they are retained for the explicitly reviewed byte identity.
- `new_feature_ids` partition the final covered-feature set in selection order.
- After pins, at each greedy round, the feasible row with greatest new coverage wins; ties choose the
  smallest physical line number. A previously excluded oversized row cannot become
  feasible because remaining output bytes never increase.
- Selection is deterministic for identical input bytes, tool version, and options.
- Full observed coverage means exactly the declared feature universe is covered.
  It does not imply coverage of feature combinations, semantics, or future records.

## Complexity and tradeoffs

Let B be input bytes, E row/feature associations, F distinct features, R records,
and K selected rows. Parsing traverses the spool twice. Missing-member extraction
also examines the union vocabulary at each observed object. It can be more costly
than ordinary parsing for wide, heterogeneous objects, so node/feature/record limits
matter. SQLite stores O(B + E + R + F) data. Index construction and incidence gain
updates add database/indexing overhead; each newly covered feature traverses its
incident rows once, up to E total decrements for a complete cover. The report and
selected rows are materialized within configured feature/association/output caps.

Greedy set cover is chosen for inspectability and useful fixture reduction, not a
minimum cardinality claim. Returning fewer than the requested number of rows is
intentional when no uncovered features remain. Frequency weighting, value buckets,
array-position coverage, approximate discovery, persisted indexes, and parallel
selection are deliberately outside this MVP.
Optional numeric-syntax coverage classifies tokens only; it adds no magnitude or
precision buckets and never converts numeric values.

## Future compatibility

`format_version` governs report structure; the named algorithm governs tie-breaking
and selection semantics. Path segments are tagged by JSON value type: strings are
object members, `null` is an array wildcard. No dotted-path escape convention is
needed. Feature IDs are local to one report. A future model must not silently
reinterpret old reports or describe a partial/truncated inventory as complete.
Numeric-syntax mode opts into format 2 and declares its feature model explicitly;
default-mode report bytes and selection semantics remain unchanged.
Nonempty pins opt into format 3 and a pinned-first algorithm name, with explicit
feature-model metadata and selection reasons. Inventory comparison accepts the
same declared feature model across formats 1/2/3; selection changes do not change
the observed feature universe. It rejects unknown formats/models and mismatches.
