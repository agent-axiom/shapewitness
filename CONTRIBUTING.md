# Contributing

Small, well-tested changes are welcome. Start with an issue for changes to feature
semantics or selection strategy. Describe the input, expected fixture/coverage, and
tradeoff. Use synthetic examples; never attach confidential JSONL exports.

Install a checkout with `python -m pip install --no-deps -e .`, then run
`python -m unittest discover -s tests -v` and `python -m compileall -q src tests`.
The runtime and core test suite use the standard library only. The optional pytest
recipe and release tooling use separate development dependencies; see
[release readiness](docs/release/README.md).

Please preserve deterministic ordering, raw input bytes, strict error behavior,
explicit bounds, and report-version compatibility. Add regression tests for every
bug fix. Generated/seeded tests must use fixed seeds. Document new limits and any
privacy impact. Keep changes focused; new runtime dependencies need a concrete
benefit that outweighs their installation and supply-chain cost.
