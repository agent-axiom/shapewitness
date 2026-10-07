# Releases and automatic publishing

[Home](../../README.md) · [Development](../development.md)

The repository owner authorized automatic production-PyPI publishing from new stable
version tags. The active [publishing workflow](../../.github/workflows/publish.yml)
uses the existing GitHub Actions secret **PYPI_API_TOKEN**. It does not create a token,
read one into developer tools, or configure a Trusted Publisher grant.

## Release contract

A new tag such as `v0.1.0` triggers the release. Ordinary branch commits do not publish.
Only strict `vMAJOR.MINOR.PATCH` tags without leading zeroes are accepted; prerelease
suffixes, modified/force-moved tags, and deletion events are rejected.

The first gate requires the checkout, tag target, and triggering event to identify
the same immutable commit. That commit must belong to the fetched `main` history,
and the package metadata name/version must match `shapewitness` and the tag.

The exact commit passes Linux/Python 3.10, 3.12, 3.14, macOS, and Windows tests. A
separate secretless job builds wheel/sdist, performs strict metadata validation,
installs/tests the wheel, and runs recipes. Only then does the publishing job fetch
the same immutable artifact ID and verify its source/version, file sizes, and SHA-256
hashes. It has no source checkout and executes no code from those distributions.
The secret is passed only to the PyPA publishing action, never to build/test steps.

There is no manual dispatch, release checkbox, OIDC permission, or implicit GitHub
environment. The tag push is the release action. Limit repository and version-tag
write access to trusted maintainers; the ancestry check does not replace access controls.

## Before tagging

1. Review package metadata and the intended stable version.
2. Wait for CI and Release readiness on the exact commit on `main`.
3. Confirm the official PyPI name/version state. HTTP 404 alone does not reserve or
   guarantee that a new name will be accepted.
4. Create the new version tag at that commit, which must include the publisher.
5. Monitor the publishing run, then verify the official PyPI files/hashes, clean
   installation, and CLI behavior. A workflow artifact alone is not a release.

Do not move a release tag or reuse a version to repair changed bytes. PyPI does not
allow replacing an uploaded filename, even after deletion. Duplicate uploads fail
loudly (`skip-existing: false`). If one file uploads and the other fails, inspect
PyPI and compare the original artifact hashes before any retry. Do not blindly
rebuild and re-upload a potentially partial release.

## Token scope

The owner enters **PYPI_API_TOKEN** directly in GitHub Actions secrets; it must never
appear in chat, source, issues, or logs. A new project's first token-based upload
needs an account-wide token. Restricting GitHub access to this repository does not
reduce that token's PyPI privileges. After the first successful release, replace the
secret with a token scoped only to `shapewitness` and revoke the bootstrap token
before further release tags.

The former [Trusted Publisher template](publish.yml.example) remains an inactive
alternative. It is not used by the token workflow, and no OIDC grant is assumed.

## Local release checks

Use Python 3.12 for release tooling; the package supports Python 3.10+. Build into
an empty output directory to keep earlier artifacts out of the candidate set.

```sh
python -m pip install build==1.6.1 twine==7.0.0 pytest==9.1.1
python scripts/prepare_pypi_readme.py --check
python -m build --outdir dist
python -m twine check --strict dist/*
python scripts/check_distribution.py dist
python -m pip install --no-deps dist/shapewitness-0.1.0-py3-none-any.whl
python -m unittest discover -s tests -v
python -m pytest -q examples/recipes/pytest_fixtures.py
```

The package description is generated from the short README with absolute GitHub
links. Regenerate with `python scripts/prepare_pypi_readme.py` after README changes.
The [non-publishing readiness workflow](../../.github/workflows/release-readiness.yml)
also checks wheel-based uvx/pipx execution and retains candidate artifacts for 14 days.
It has no upload credential or publishing action.

Official references: [GitHub tag triggers](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#push),
[PyPI token scopes](https://pypi.org/help/#apitoken),
[filename reuse](https://pypi.org/help/#file-name-reuse),
[PyPA's publishing action](https://github.com/pypa/gh-action-pypi-publish).
