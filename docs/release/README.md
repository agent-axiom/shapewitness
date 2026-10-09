# Releases and automatic publishing

[Home](../../README.md) · [Development](../development.md)

The repository owner authorized automatic production-PyPI publishing after successful
`main` CI. The [publishing workflow](../../.github/workflows/publish.yml) uses the
existing GitHub Actions secret **PYPI_API_TOKEN**. It does not create credentials or
configure a Trusted Publisher grant.

## Release contract

A merge/push to `main` that increases the package version is a release request. Both
**CI** and **Release readiness** must finish successfully for that exact commit.
The publisher wakes when either completes and checks both through the GitHub API;
it does not mistake the first successful workflow for aggregate success. A newer
failed, cancelled, skipped, or pending run cannot be replaced by an older green run.
Only same-repository `push` runs on `main` count, never pull-request or fork runs.

The source checkout uses the successful run's immutable `head_sha`, not whichever
commit happens to be the current branch tip. It must still belong to fetched `main`
history. The version must be strict `MAJOR.MINOR.PATCH`, without leading zeroes, and
increase from the commit's first parent. Unchanged versions skip publication.
Versions are not guessed or automatically incremented on ordinary commits.

A complete version already on PyPI is an idempotent no-op. Only an HTTP 404 for the
specific project/version means unpublished. Network/authentication/server errors,
malformed responses, unexpected package identity, or a partially uploaded release
fail closed. All production publication runs share a serialized queue; they do not
cancel a running upload. Stable tags and manual dispatch no longer publish.

## Verification and secret boundary

The exact source passes Linux/Python 3.10, 3.12, 3.14, macOS, and Windows tests again.
A secretless job builds wheel/sdist, checks metadata, installs/tests the wheel, and
runs the pytest, ETL, and real-importer recipes. The publishing job downloads only
the same immutable artifact ID and verifies source/version, filenames, sizes, and
SHA-256 hashes without checking out source or executing distribution contents.
Immediately before upload it rechecks both CI workflows and the current PyPI state.
The PyPI token is passed only to the pinned PyPA action, never build/test steps.

`skip-existing: false` remains deliberate: a race or partial upload must not silently
look successful. If one file uploads and the other fails, inspect the original
artifact and compare registry hashes before attempting recovery. Do not blindly
rebuild/re-upload; PyPI does not allow replacing uploaded filenames, even if deleted.
A complete existing version is skipped at the registry gate, not overwritten.

There is no OIDC permission or new persistent access. Limit repository and workflow
write access to trusted maintainers; CI/ancestry checks do not replace access controls.

## Make a release

1. Update both `pyproject.toml` and `src/shapewitness/_version.py`, the changelog, and
   the example coverage report. Distribution checks reject version drift.
2. Open/review the release PR. Merging its version increase into `main` starts the
   release automatically after both exact-commit workflows turn green.
3. Monitor **Publish after main CI**, then verify official PyPI files/hashes, a clean
   installation, and CLI behavior. A workflow artifact alone is not a release.

If CI initially fails, fix/re-run it; publication still requires both workflows to
succeed. To retry a transient publisher failure, rerun that publishing run. If the
version is already complete on PyPI the retry exits successfully without uploading.
A code fix that keeps an unpublished version unchanged does not itself release it;
rerun the original release only if its original source is correct, otherwise bump
the fixed source to a new version. This avoids silently releasing different bytes.

## Local release checks

Use Python 3.12 for release tooling; the package supports Python 3.10+. Build into
an empty output directory to keep earlier artifacts out of the candidate set.

```sh
python -m pip install build==1.6.1 twine==7.0.0 pytest==9.1.1
python scripts/prepare_pypi_readme.py --check
python -m build --outdir dist
python -m twine check --strict dist/*
python scripts/check_distribution.py dist
python -m pip install --no-deps dist/*.whl
python -m unittest discover -s tests -v
python -m pytest -q examples/recipes/pytest_fixtures.py
python -m pip install -r tests/integration/requirements.txt
python -m unittest discover -s tests/integration -v
```

The package description is generated from the README with absolute GitHub links.
Regenerate with `python scripts/prepare_pypi_readme.py` after README changes.
The [readiness workflow](../../.github/workflows/release-readiness.yml) also checks
wheel-based uvx/pipx execution and retains candidate artifacts for 14 days. It has
no publishing secret or action. Optional importer packages are test dependencies;
the shipped wheel has zero runtime dependencies.

The owner manages **PYPI_API_TOKEN** directly in GitHub Actions secrets; never put it
in chat, source, issues, or logs. Prefer a token scoped only to `shapewitness`.
The [Trusted Publisher template](publish.yml.example) remains inactive.

Official references: [GitHub workflow completion triggers](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run),
[PyPI JSON API](https://docs.pypi.org/api/json/),
[filename reuse](https://pypi.org/help/#file-name-reuse),
[PyPA's publishing action](https://github.com/pypa/gh-action-pypi-publish).
