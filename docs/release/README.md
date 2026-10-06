# Release readiness, without publishing

[Home](../../README.md) · [Development](../development.md)

The repository builds release candidates and validates their metadata. It has not
uploaded a package to PyPI or TestPyPI, created an account/token, configured a
Trusted Publisher, or claimed a package namespace.

## Current name check

On 2026-10-06, the official [PyPI JSON endpoint](https://pypi.org/pypi/shapewitness/json)
returned HTTP 404. This means no visible project was returned at that moment; it is
not a reservation or a guarantee that PyPI will accept the name. Recheck immediately
before publishing. A pending publisher also does not reserve a name, as explained in
[PyPI's project-creation guide](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

## Validate locally

Use Python 3.12 for release tooling; the installed package supports Python 3.10+.
Build into a new or empty directory so older artifacts cannot be uploaded by mistake.

```sh
python -m pip install build==1.6.1 twine==7.0.0 pytest==9.1.1
python scripts/prepare_pypi_readme.py --check
python -m build --outdir dist
python -m twine check --strict dist/*
python scripts/check_distribution.py dist
python -m pip install --no-deps dist/shapewitness-0.1.0-py3-none-any.whl
python -m unittest discover -s tests -v
python -m pytest -q examples/recipes/pytest_fixtures.py
python examples/recipes/etl_regression.py
python examples/recipes/importer_bug_repro.py > repro.jsonl
```

The package description is generated from the short README, with absolute GitHub
links so it renders sensibly on a package index. After editing README, regenerate it
with `python scripts/prepare_pypi_readme.py`. The metadata checker verifies the name,
version, Python requirement, MIT license expression, zero runtime dependencies,
console entry point, typed marker, and source-archive contents, then emits hashes.

The [release-readiness workflow](../../.github/workflows/release-readiness.yml) also
checks wheel-based `uvx` and `pipx` invocation and stores candidates as workflow
artifacts for 14 days. It has read-only repository permissions and no upload-to-PyPI
step or OIDC permission. An artifact is a candidate, not a published release.

## Run without a PyPI release

With a locally built wheel and the corresponding tools installed:

```sh
uvx --no-index --from dist/shapewitness-0.1.0-py3-none-any.whl shapewitness --version
pipx run --no-cache --spec dist/shapewitness-0.1.0-py3-none-any.whl shapewitness --version
```

See the official [uv tools guide](https://docs.astral.sh/uv/guides/tools/) and
[pipx documentation](https://pipx.pypa.io/stable/). Bare `uvx shapewitness` or
`pipx install shapewitness` must not be advertised until the correct package is
actually published and verified on PyPI.

## Owner decisions before publishing

1. Confirm which existing PyPI account will own the project, the public author
   metadata, version, and final release commit. Do not share passwords or API tokens.
2. Review and explicitly approve creating a Trusted Publisher binding and a protected
   GitHub `pypi` environment. This establishes persistent publishing authority.
3. On that account, configure a pending publisher with these exact fields:
   - PyPI project: `shapewitness`
   - GitHub owner: `agent-axiom`
   - Repository: `shapewitness`
   - Workflow filename: `publish.yml`
   - Environment: `pypi`
4. Configure the environment with the intended required reviewer and approved tag
   restrictions. Verify those protections before enabling the publishing workflow.
5. Review [the inactive template](publish.yml.example), then separately approve
   placing it at `.github/workflows/publish.yml`. It obtains short-lived OIDC-based
   upload credentials only in the publishing job; no stored API key is required.
6. Update the release status text, regenerate the package README, verify all checks
   on the chosen commit, and review artifact hashes. Create the approved version tag
   and dispatch the manual workflow only after the release itself is authorized.
7. Verify the official project/version, artifact hashes, installation, `uvx` and
   `pipx` behavior, and CLI smoke test after upload. Only then announce availability.

The template is deliberately inactive and performs no setup. TestPyPI is a separate
service/account/publisher configuration; any test upload also needs an approved
account and destination. PyPI names/releases can have reuse restrictions; confirm
metadata before sending an irreversible public release.

Official references: [adding publishers](https://docs.pypi.org/trusted-publishers/adding-a-publisher/),
[publishing with OIDC](https://docs.pypi.org/trusted-publishers/using-a-publisher/),
[TestPyPI](https://packaging.python.org/en/latest/guides/using-testpypi/).
