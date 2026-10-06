# Head, reservoir sampling, and structural witnesses

[Home](../README.md) · [Raw measurements](../benchmarks/synthetic.json) ·
[Public synthetic corpus](../benchmarks/synthetic.jsonl) · [Runner](../scripts/compare_sampling.py)

## What this demonstrates

With an eight-row budget on this particular 1,000-row corpus, ShapeWitness selected
rows covering **43 of 47** observed structural features. The first eight rows covered
**8 of 47**. Reservoir samples for seeds 0–19 covered **8–13 of 47**, with a median
of **8**. Four observed features remain uncovered by ShapeWitness at this budget.

This intentionally tail-heavy corpus has 990 ordinary same-shape records followed
by ten varied cases. It makes the structural-selection use case visible, and is not
an unbiased model of production exports or a claim of statistical representativeness.
The generator, exact bytes, corpus digest, seed-by-seed results, and selected lines
are public. Every method uses the same corpus and row budget.

## Timing, with the differences visible

Measured locally on Linux x86_64, Python 3.12.14, five repetitions per method/seed:

| Method | Structural coverage | Median selection time |
| --- | --- | ---: |
| Head, first eight rows | 8 / 47 | about 0.001 ms |
| Reservoir, seeds 0–19 | median 8 / 47; range 8–13 | about 0.225 ms |
| ShapeWitness, eight rows | 43 / 47 | about 100 ms |

These tiny-input timings are illustrative, not a throughput benchmark. ShapeWitness
is substantially slower here because it validates every row, learns missing-member
semantics, writes a SQLite spool, selects witnesses, and creates provenance. The
baselines do none of that; head can stop after eight rows. Corpus generation and
independent coverage scoring are outside all timings; the corpus is already in
memory. The same-process repetitions do not measure cold startup or cold storage.
No speedup claim follows from these measurements.

## Reproduce

```sh
python -m pip install .
python scripts/compare_sampling.py --output /tmp/shapewitness-comparison.json \
  --dataset-output /tmp/shapewitness-synthetic.jsonl
```

The structural results and corpus SHA-256 are reproducible for this code and Python
random algorithm; timings depend on the machine. The tests check a separate feature
oracle against the report, corpus reproducibility, selected-row identity, and the
explicit remaining coverage gap. The fixed seeds describe these runs only, not a
confidence interval.

For your own evaluation, use your real data under its privacy constraints, disclose
the budget and feature model, and check useful downstream assertions. Random samples
remain appropriate when frequency/statistical sampling is the goal. Structural
witnesses do not replace that goal.
