# Releasing BinPackage to PyPI

This guide explains how to release a new version of BinPackage to PyPI.

BinPackage publishes two packages: `islenska` (the code, with a binary wheel
per platform and Python implementation) and `islenska-data` (the data files,
one pure wheel), on which `islenska` depends. A code release needs only the
first; a release of new BÍN data, or of a new data format, needs the second,
and that one goes first (see
[Releasing the data package](#releasing-the-data-package-islenska-data)).

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

The run has four jobs: build the BÍN data and an islenska-data wheel, build
the wheels (one `cp310-abi3` wheel per platform plus free-threaded CPython and
PyPy), build the sdist, and finally `Publish to PyPI`. The wheels and the
sdist contain no data files, and every expected wheel is there (the workflow
checks both). Every wheel is smoke-tested by
cibuildwheel (`test/wheel_smoke.py`) with the islenska-data wheel of the
same run installed, so the tests do not depend on what is on PyPI. Builds
typically take 15–20 minutes. The `publish` job runs only after the build
jobs succeed.

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
  (`https://pypi.org/project/islenska/`). Since 2026-10-14 that environment
  accepts only tags matching `*.*.*` or `data-*.*.*`, so no branch can
  deploy to it. It has no required reviewer, so the upload proceeds as soon
  as the build jobs pass. Add one in the repository settings if you want a
  manual approval gate before publishing.

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

Expect 30 wheels plus the source distribution. One `cp310-abi3` wheel per
platform covers all CPython 3.10+ versions with the GIL. Free-threaded
CPython has no stable ABI, so 3.14t and 3.15t get a wheel each
(`cp314-cp314t`, `cp315-cp315t`). PyPy gets a wheel per ABI:
PyPy 3.11 as PyPy 7.3 (`pp73`, built with cibuildwheel 4.2.1) and as
PyPy 8.0 (`pp80`), and PyPy 3.12 (`pp80`); the last two are built with
cibuildwheel 4.3.1. (Substitute the version for `X.Y.Z`; the exact
platform tags may differ.)

**Linux (x86_64 and aarch64; `manylinux_2_28` tags):**
- `islenska-X.Y.Z-cp310-abi3-manylinux_..._{x86_64,aarch64}.whl`
- `islenska-X.Y.Z-cp314-cp314t-manylinux_..._{x86_64,aarch64}.whl`
- `islenska-X.Y.Z-cp315-cp315t-manylinux_..._{x86_64,aarch64}.whl`
- `islenska-X.Y.Z-pp311-pypy311_pp73-manylinux_..._{x86_64,aarch64}.whl`
- `islenska-X.Y.Z-pp311-pypy311_pp80-manylinux_..._{x86_64,aarch64}.whl`
- `islenska-X.Y.Z-pp312-pypy312_pp80-manylinux_..._{x86_64,aarch64}.whl`

**macOS (x86_64 + arm64):**
- `islenska-X.Y.Z-cp310-abi3-macosx_10_13_x86_64.whl`,
  `islenska-X.Y.Z-cp310-abi3-macosx_11_0_arm64.whl`
- the two free-threaded and three PyPy wheels for each of x86_64 and arm64

**Windows (AMD64):**
- `islenska-X.Y.Z-cp310-abi3-win_amd64.whl`
- the two free-threaded and three PyPy wheels

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
- Confirm the tag matches one of the `pypi` environment's deployment tag
  patterns (`*.*.*`, `data-*.*.*`); GitHub refuses the deployment otherwise.
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

3. The workflow restores the islenska-data wheel from the Actions cache (the
   one the tests on `main` built from the same inputs; on a miss it builds
   the data, stages them with `tools/data_package.py` and builds the wheel;
   see `.github/actions/islenska-data`), runs the test suite with
   an islenska wheel that has no data files of its own, and publishes the
   wheel through the `pypi` environment. PyPI's Trusted Publisher for
   islenska-data names `data-release.yml` and `pypi`; keep both.

`data-*` tags do not trigger `wheels.yml`. For a dry run, push a tag that
contains `test` (`data-5.0.1-test1`) or start the workflow by hand from the
Actions tab: both build and test without publishing.

Release islenska-data before an islenska release that needs it, so that
the islenska release can be installed as soon as it is published. islenska
requires `islenska-data ~= M.N.0` (`pyproject.toml`), where M.N is the data
format it reads: a new patch release of islenska-data reaches existing
islenska installations without an islenska release, while a new data format
needs both a new islenska-data major or minor version and an islenska
release that requires it.

## Version Numbering

Follow semantic versioning (semver):
- **Major (2.0.0)**: Breaking API changes
- **Minor (1.3.0)**: New features, backward compatible
- **Patch (1.3.1)**: Bug fixes only
