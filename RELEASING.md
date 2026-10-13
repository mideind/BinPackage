# Releasing BinPackage to PyPI

This guide explains how to release a new version of BinPackage to PyPI.

Releases are **fully automated** by the `wheels.yml` GitHub Actions workflow:
pushing a version tag builds the wheels and source distribution and then
publishes them to PyPI. There is no manual `twine upload` step — see
[How publishing works](#how-publishing-works) below.

## Prerequisites

- Write access to the GitHub repository (to push the release tag)
- `gh` CLI tool installed and authenticated
- `uv` (for the local checks below)

A PyPI account/token is **not** required for a normal release: the workflow
authenticates to PyPI with [Trusted Publishing](#how-publishing-works) (OIDC),
so no long-lived credentials are stored or needed.

## Release Process

### 1. Pre-flight checks

From a clean `main`, make sure the suite is green before tagging:

```bash
uv sync --extra dev
uv run pytest
uv run pyright
ruff check src/islenska   # using a separately installed ruff, as CI does
```

### 2. Update the version number

The version lives in a single place — `pyproject.toml`
(`src/islenska/__init__.py` reads it at runtime via
`importlib.metadata.version`). Edit it:

```toml
version = "1.3.1"  # Update this
```

Follow [semantic versioning](#version-numbering).

### 3. Commit, tag and push

```bash
git add pyproject.toml
git commit -m "Bump version to 1.3.1 for release"
git tag -a 1.3.1 -m "Release version 1.3.1

[Brief description of changes]
"
git push origin main
git push origin 1.3.1
```

**Pushing the tag triggers the `wheels.yml` workflow, which builds the
distributions and then publishes them to PyPI automatically.** Any tag whose
name does not contain `test` will publish (see
[Dry runs](#dry-runs-without-publishing)), so only push a version tag when you
intend to release.

### 4. Monitor the workflow

```bash
gh run list --workflow=wheels.yml --limit 3
gh run watch <run-id>          # follow a specific run
```

Or visit: https://github.com/mideind/BinPackage/actions/workflows/wheels.yml

The run has four jobs: prepare the compressed BÍN data, build the wheels
(one `cp310-abi3` wheel per platform plus PyPy), build the sdist, and finally
`Publish to PyPI`. Builds typically take 10–15 minutes. The `publish` job runs
only after the build jobs succeed.

### 5. Create the GitHub release

Once published, create a GitHub release for the tag with user-facing notes:

```bash
gh release create 1.3.1 --title "1.3.1" --notes "….release notes…."
```

### 6. Verify the release

- Check the PyPI page: https://pypi.org/project/islenska/
- Test installation: `pip install islenska==1.3.1`
- Verify abi3 wheels are available for multiple Python versions

## How publishing works

The final `publish` job in `.github/workflows/wheels.yml` uploads to PyPI with
[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) via the
[`pypa/gh-action-pypi-publish`](https://github.com/pypa/gh-action-pypi-publish)
action. The job:

- runs only on tags: `if: startsWith(github.ref, 'refs/tags/') && !contains(github.ref, 'test')`;
- requests an OIDC token (`permissions: id-token: write`) that PyPI exchanges
  for a short-lived upload token — no API token or password is stored;
- deploys through the `pypi` GitHub environment
  (`https://pypi.org/project/islenska/`). The environment currently has no
  protection rules, so the upload proceeds as soon as the build jobs pass. Add
  a required reviewer to that environment in the repository settings if you
  want a manual approval gate before publishing.

## Dry runs (without publishing)

To exercise the build (wheels + sdist) without publishing, push a tag whose
name contains `test`; the `publish` job is skipped for such tags:

```bash
git tag 1.3.1-test1
git push origin 1.3.1-test1
```

Delete the test tag afterwards (`git push origin :1.3.1-test1`).

## Manual upload (fallback only)

If you ever need to publish outside of CI (e.g. the workflow is broken), the
`release-to-pypi.sh` script downloads the wheel artifacts from a completed run
and stages them in `dist-release/` for a manual `twine upload`:

```bash
./release-to-pypi.sh <run-id>          # downloads artifacts + builds sdist + twine check
python -m twine upload dist-release/*  # requires PyPI credentials/token
```

This path is **not** the normal release process and requires your own PyPI
credentials.

## Expected wheel artifacts

Expect 8 wheels plus the source distribution. One `cp310-abi3` wheel covers all
CPython 3.10+ versions; PyPy support is limited to PyPy 3.11 (`pp311`).
(Substitute the version you are releasing for `X.Y.Z` below.)

**Linux (x86_64):**
- `islenska-X.Y.Z-cp310-abi3-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl`
- `islenska-X.Y.Z-pp311-pypy311_pp73-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl`

**macOS (x86_64 + arm64):**
- `islenska-X.Y.Z-cp310-abi3-macosx_10_13_x86_64.whl`
- `islenska-X.Y.Z-cp310-abi3-macosx_11_0_arm64.whl`
- `islenska-X.Y.Z-pp311-pypy311_pp73-macosx_10_15_x86_64.whl`
- `islenska-X.Y.Z-pp311-pypy311_pp73-macosx_11_0_arm64.whl`

**Windows (AMD64):**
- `islenska-X.Y.Z-cp310-abi3-win_amd64.whl`
- `islenska-X.Y.Z-pp311-pypy311_pp73-win_amd64.whl`

**Source:**
- `islenska-X.Y.Z.tar.gz`

## Troubleshooting

### Build failed

Check the GitHub Actions logs for errors. Common issues:
- C++ compilation errors
- Missing dependencies in CI
- Test failures

### Publish job failed

- Confirm the tag is a version tag and does not contain `test`.
- Confirm the `pypi` Trusted Publisher is still configured on PyPI for this
  repository and the `wheels.yml` workflow.
- A version already present on PyPI cannot be re-uploaded; bump the version and
  tag again.

### Wrong wheels built

- Verify the tag points at the intended commit.
- Re-run the workflow if needed: `gh workflow run wheels.yml --ref <tag>`.

## Post-Release

1. Announce the release (if applicable)
2. Update documentation with new features
3. Monitor PyPI download stats
4. Watch for user-reported issues

## Releasing the data package (islenska-data)

> **Not in use yet.** As of 2026-10-02, islenska still ships its own data
> files and does not depend on islenska-data, and islenska-data has never
> been uploaded. Its first upload creates the project on PyPI, so do it only
> as part of the switch described in the roadmap in `CLAUDE.md`.

`islenska-data` (in `islenska-data/`) holds the data files: `compressed.bin`
and the three DAWGs. It is released only when the data change, from its
own workflow, `.github/workflows/data-release.yml`, as a single
`py3-none-any` wheel (no sdist).

1. Bump `version` in `islenska-data/pyproject.toml`. The major and minor
   numbers follow the data format (`Greynir 05.00.00` is 5.0); bump the
   patch number for new BÍN data in the same format. A new data format
   needs a matching islenska release and a new major or minor version here.
2. Commit, then tag and push `data-X.Y.Z` (the tag must match the version,
   or the workflow stops):

   ```bash
   git tag -a data-5.0.1 -m "islenska-data 5.0.1"
   git push origin data-5.0.1
   ```

3. The workflow builds the data (or restores it from the cache), stages it
   with `tools/data_package.py`, builds the wheel, runs the test suite with
   an islenska wheel that has no data files of its own, and publishes the
   wheel through the `pypi` environment. PyPI's Trusted Publisher for
   islenska-data names `data-release.yml` and `pypi`; keep both.

`data-*` tags do not trigger `wheels.yml`. For a dry run, push a tag that
contains `test` (`data-5.0.1-test1`) or start the workflow by hand from the
Actions tab: both build and test without publishing.

When islenska depends on islenska-data, release islenska-data first, so that
the islenska release can be installed as soon as it is published.

## Version Numbering

Follow semantic versioning (semver):
- **Major (2.0.0)**: Breaking API changes
- **Minor (1.3.0)**: New features, backward compatible
- **Patch (1.3.1)**: Bug fixes only
