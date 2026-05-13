# Releasing BinPackage to PyPI

This guide explains how to release a new version of BinPackage to PyPI.

## Prerequisites

- Write access to the GitHub repository
- PyPI account with maintainer access to `islenska` package
- `gh` CLI tool installed and authenticated
- Python 3.9+ with `build` and `twine` packages

## Release Process

### 1. Update Version Number

Edit `pyproject.toml` and update the version:
```toml
version = "1.2.0"  # Update this
```

### 2. Commit and Tag

```bash
git add pyproject.toml
git commit -m "Bump version to 1.2.0 for release"
git tag -a 1.2.0 -m "Release version 1.2.0

[Brief description of changes]
"
git push origin main
git push origin 1.2.0
```

Pushing the tag triggers the wheel building workflow on GitHub Actions.

### 3. Wait for Wheel Builds

Monitor the build progress:
```bash
gh run list --workflow=wheels.yml --limit 3
```

Or visit: https://github.com/mideind/BinPackage/actions/workflows/wheels.yml

Builds typically take 10-15 minutes.

### 4. Download and Prepare Release

Once the build completes successfully, use the automated release script:

```bash
# Get the run ID from step 3
RUN_ID=18731185158  # Example - use actual ID

# Run the release script
./release-to-pypi.sh $RUN_ID
```

The script will:
- Download wheel artifacts from all platforms
- Build the source distribution (`.tar.gz`)
- Collect everything into `dist-release/`
- Verify all distributions with `twine check`

### 5. Upload to PyPI

#### Option A: Test Upload First (Recommended)

```bash
python -m twine upload --repository testpypi dist-release/*
```

Then verify at: https://test.pypi.org/project/islenska/

#### Option B: Direct Production Upload

```bash
python -m twine upload dist-release/*
```

You'll be prompted for your PyPI credentials (or use API token).

### 6. Verify Release

- Check PyPI page: https://pypi.org/project/islenska/
- Test installation: `pip install islenska==1.2.0`
- Verify abi3 wheels are available for multiple Python versions

## Expected Wheel Artifacts

For version 1.2.0, expect 8 wheels plus the source distribution.
One `cp39-abi3` wheel covers all CPython 3.9+ versions; PyPy support
is limited to PyPy 3.11 (`pp311`).

**Linux (x86_64):**
- `islenska-1.2.0-cp39-abi3-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl`
- `islenska-1.2.0-pp311-pypy311_pp73-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl`

**macOS (x86_64 + arm64):**
- `islenska-1.2.0-cp39-abi3-macosx_10_9_x86_64.whl`
- `islenska-1.2.0-cp39-abi3-macosx_11_0_arm64.whl`
- `islenska-1.2.0-pp311-pypy311_pp73-macosx_10_15_x86_64.whl`
- `islenska-1.2.0-pp311-pypy311_pp73-macosx_11_0_arm64.whl`

**Windows (AMD64):**
- `islenska-1.2.0-cp39-abi3-win_amd64.whl`
- `islenska-1.2.0-pp311-pypy311_pp73-win_amd64.whl`

**Source:**
- `islenska-1.2.0.tar.gz`

## Troubleshooting

### Build Failed

Check the GitHub Actions logs for errors. Common issues:
- C++ compilation errors
- Missing dependencies in CI
- Test failures

### Twine Upload Fails

- Ensure you have PyPI credentials configured
- Use API token instead of password (more secure)
- Check network connectivity

### Wrong Wheels Downloaded

- Verify the run ID corresponds to the correct tag
- Re-run the workflow if needed: `gh workflow run wheels.yml --ref 1.2.0`

## Post-Release

1. Announce the release (if applicable)
2. Update documentation with new features
3. Monitor PyPI download stats
4. Watch for user-reported issues

## Version Numbering

Follow semantic versioning (semver):
- **Major (2.0.0)**: Breaking API changes
- **Minor (1.2.0)**: New features, backward compatible
- **Patch (1.0.5)**: Bug fixes only
