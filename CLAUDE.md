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

### 1.5.0 (released 2026-10-02)

Deterministic order of case lookups (PR #28) and Python 3.10+ only, with
`cp310-abi3` wheels (PR #29). Python 3.9 users stay on 1.4.0. The wheel set is
unchanged otherwise, so PyPy wheels are still `pp73` only.

### 1.6.0: data package, modern PyPy wheels

Do the data package split first: it is what makes the extra wheels affordable.

**Split the BÍN data into its own package.**

- Publish `compressed.bin` (and the DAWG files) as a separate pure
  `py3-none-any` package, released only when the BÍN data changes, and make
  `islenska` depend on it. The binary wheels (and the `islenska` sdist) then
  shrink to ~1-2 MB each.
- Why: the `islenska` project uses about 8.7 GB of PyPI's default 10 GB
  project limit after 1.5.0. Each release so far is ~454 MB, because every
  wheel and the sdist carries the same ~50 MB `compressed.bin`; adding the PyPy
  wheels below without the split would make it ~860 MB per release. The split
  removes the storage problem for good and makes every additional wheel nearly
  free. If 1.6.0 must add wheels before the split is ready, first request a
  limit increase (`pypi/support`, "Project Limit Request"). The 1.0.2–1.0.4
  releases take 4.6 GB (mostly wheels for end-of-life Pythons), but deleting
  them is irreversible and would push anyone pinned to them onto source
  builds, so treat that as a last resort.
- PyPI's size limit is per project, so the data package gets its own 10 GB.
  Ship it as a wheel only (an sdist would just duplicate the data); with
  BÍN updates a few times a year that lasts for hundreds of releases. After
  the split an `islenska` release is ~20-40 MB, so its remaining ~1.3 GB lasts
  for dozens of releases.
- Ship only the compact build (`tools/binpack.py --compact`, about half the
  size, same answers per `tools/parity.py`). Before switching, check what the
  parity tool does not: `Bin`-level results (including `only_bin=True` and
  `add_compounds=False`, where a dropped compound must still come back as a
  genuine BÍN entry), lookup speed on a mixed word list, and whether anyone
  still needs the full file (`ISLENSKA_BIN_FILE` can point at one).
- Before the first upload, configure a pending Trusted Publisher for the new
  project name on PyPI (it does not reserve the name; the first upload does).
- Design points: how the code locates the data package (with
  `ISLENSKA_BIN_FILE` still taking precedence), pinning the data package to
  the data format (`Greynir 05.00.00`) the code expects, and a two-package
  release process in `RELEASING.md` and `wheels.yml`.

**PyPy wheels for the new ABI, and PyPy 3.12.**

- PyPy 8.0.0 (September 2026) changed the ABI tag from `pp73` to `pp80`.
  Our PyPy wheels (up to 1.5.0) are `pypy311_pp73` only, so PyPy 8.0 users
  build from the sdist (C++17 compiler needed). PyPy 8.0 is the last 3.11
  release; PyPy 3.12 (also `pp80`, beta in 8.0) is the line going forward.
- Ship `pp311` for both ABIs plus `pp312`: pip installs the newest version even
  if that means building from source, so dropping `pp73` would move the
  breakage to PyPy 7.3 users.
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

**Linux aarch64 wheels** (CPython and PyPy), on GitHub's native ARM runners.
CPython and PyPy users on ARM Linux build from source today. Cheap once the
data package exists.

### Possible later step: one wheel for every non-CPython interpreter

Load `libbin` as a plain shared library through CFFI's ABI mode (`dlopen`)
and ship it as a `py3-none-<platform>` wheel. Such a wheel works on every PyPy
version, including future ABI bumps, and on GraalPy, with no rebuilds.
CPython keeps the faster API-mode `cp310-abi3` wheels, which installers prefer
over `py3-none` when both match.
