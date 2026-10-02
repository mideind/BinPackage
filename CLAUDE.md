# CLAUDE.md

Guidance for Claude Code in this repository. `AGENTS.md` holds the full project
overview and architecture notes; the day-to-day essentials are below.

## Tooling

This project is managed with [uv](https://docs.astral.sh/uv/) — dependencies
are declared in `pyproject.toml` and pinned in `uv.lock`. Run dev tools through
`uv run` so they use the locked project environment.

## Key commands

```bash
# Sync the environment, including dev tools (pytest, pyright)
uv sync --extra dev

# Run the test suite
uv run pytest

# Type-check (strict pyright; config in pyrightconfig.json, target Python 3.10)
uv run pyright
```

`ruff` is not a project dependency; lint with `ruff check src/islenska` using a
separately installed ruff (this is how CI runs it).

The C++ code is the `libbin` library in `libbin/` (C API in
`libbin/include/libbin/bin.h`; see `libbin/README.md`). Rebuild the CFFI
extension after editing it with `uv pip install -e . --no-build-isolation` —
never run `bin_build.py` directly (see `AGENTS.md` for the reason). The
library also builds standalone: `cmake -S libbin -B libbin/build && cmake
--build libbin/build && ctest --test-dir libbin/build`.

The compressed data comes in a full and a compact variant (`tools/binpack.py
--compact`); see "Compact build" in `AGENTS.md`. After changing the selection
rules (`tools/compact.py`) or the restoration code (`libbin/src/dict.cpp`),
run `tools/parity.py` against a fresh compact build.

## Roadmap (recorded 2026-10-02)

Packaging work agreed but not yet done. Re-check the facts below before
acting on them; the PyPy and cibuildwheel landscape was moving quickly.

### Next point release: PyPy wheels for the new ABI

- PyPy 8.0.0 (September 2026) changed the ABI tag from `pp73` to `pp80`.
  Our PyPy wheels (up to 1.4.0) are `pypy311_pp73` only, so PyPy 8.0 users
  build from the 50 MB sdist (C++17 compiler needed). PyPy 8.0 is the last
  3.11 release; PyPy 3.12 (also `pp80`, beta in 8.0) is the line going forward.
- Ship both ABIs: pip installs the newest version even if that means building
  from source, so dropping `pp73` would move the breakage to PyPy 7.3 users.
- cibuildwheel 4.2.1 can only build `pp73`. `pp80` for `pp311` plus a new
  `pp312` landed on cibuildwheel `main` on 2026-09-30 (commit `088b48b`), with
  no release yet. Use 4.3.0 or later once released (or pin a `main` commit)
  with `enable: pypy`, and add a second cibuildwheel 4.2.1 step that builds
  only `pp311-*` to keep the `pp73` wheels.
- Add a `CIBW_TEST_COMMAND` smoke test (import plus one lookup) so that every
  wheel is exercised before upload, and add `pypy-3.12` to the test matrix in
  `python-package.yml`.
- PyPy's abi3 support (`cp312-abi3`) is incomplete in 8.0 and does not suit
  a CFFI extension anyway (PyPy loads CFFI modules natively, not via its
  C-API emulation), so wheels per PyPy ABI remain the route.

### Blocker: PyPI project size

The `islenska` project uses about 8.25 GB of PyPI's default 10 GB project
limit (as of 2026-10-02). Each release is ~454 MB, because every wheel and the
sdist carries the same ~50 MB `compressed.bin`. With the extra PyPy wheels a
release grows to ~17 files and ~860 MB. Request a limit increase
(`pypi/support`, "Project Limit Request") before the release that adds wheels.
The 1.0.2–1.0.4 releases take 4.6 GB (mostly wheels for end-of-life Pythons),
but deleting them is irreversible and would push anyone pinned to them onto
source builds, so treat that as a last resort.

### 1.5.0: split the BÍN data into its own package

- Publish `compressed.bin` (and the DAWG files) as a separate pure
  `py3-none-any` package, released only when the BÍN data changes, and make
  `islenska` depend on it. The binary wheels then shrink to ~1 MB each.
- This removes the storage problem for good and makes every additional
  wheel (PyPy ABIs, Linux aarch64, ...) nearly free. Linux aarch64 is the
  obvious next platform: CPython and PyPy users on ARM Linux build from source
  today.
- Design points: how the code locates the data package (with
  `ISLENSKA_BIN_FILE` still taking precedence), pinning the data package to
  the data format (`Greynir 05.00.00`) the code expects, and a two-package
  release process in `RELEASING.md` and `wheels.yml`.

### Possible later step: one wheel for every non-CPython interpreter

Load `libbin` as a plain shared library through CFFI's ABI mode (`dlopen`)
and ship it as a `py3-none-<platform>` wheel. Such a wheel works on every PyPy
version, including future ABI bumps, and on GraalPy, with no rebuilds.
CPython keeps the faster API-mode `cp310-abi3` wheels, which installers prefer
over `py3-none` when both match.
