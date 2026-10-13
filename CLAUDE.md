# CLAUDE.md

Guidance for Claude Code in this repository. `AGENTS.md` holds the full project
overview and architecture notes; the day-to-day essentials are below.

## Status (2026-10-13): 2.0.0 released

**islenska 2.0.0 and islenska-data 5.0.0 were released on 2026-10-13**
(tags `2.0.0` and `data-5.0.0`, GitHub release 2.0.0). PyPI holds 20
islenska wheels plus the sdist, and one islenska-data wheel (30 MB). A
fresh `pip install islenska==2.0.0` pulls in islenska-data and reads the
data from it. The islenska-data PyPI project now belongs to the Miðeind
organization. The 1.6.0 plan became 2.0.0 because of the data split and the
new result order; what changed is in the GitHub release notes and under
"Roadmap" below.

What went into 2.0.0 (PRs #30-#35):

- #30 canonical order of a form's readings: by bin_id, then paradigm order
  (`mark_order.csv`), then source order, in binpack and in libbin's compound
  restoration.
- #31 `compressed.bin` is always a compact build; the full build and
  `tools/parity.py` are gone.
- #32 the `islenska-data` package (`islenska-data/`) and its release
  workflow `data-release.yml`.
- #33 `lookup_variants` accepts the adverb degree marks FST/EST.
- #34 (external, sverrirs) `bincompress.py` takes `memoryview`s of the
  memory map instead of copying ~90 MB per process; its tracemalloc test is
  skipped on PyPy.
- #35 the switch:
  - islenska 2.0.0 depends on `islenska-data ~= 5.0.0`, not `~= 5.0`: that
    would accept a 5.1 data format, which the exact format check rejects.
  - The islenska wheels and sdist carry no data: `MANIFEST.in` prunes
    `resources/`.
  - `basics.data_dir()`: islenska's own `resources/` if it holds any data
    file (a source checkout; binpack needs the DAWGs there before
    `compressed.bin` exists), else islenska-data, else `RuntimeError`.
  - `[tool.uv.sources]` installs the local `islenska-data/` subproject
    (editable, normally empty) in the dev environment.
  - `wheels.yml`:
    - cibuildwheel 4.3.1 builds PyPy 8.0 (`pp80`) and 3.12; 4.2.1 still
      builds `pp73`.
    - Linux aarch64 wheels on `ubuntu-24.04-arm`.
    - `test/wheel_smoke.py` runs for every wheel with the run's own data
      wheel.
    - No `.bin` is allowed in any wheel or the sdist.
  - CI builds the islenska-data wheel once per set of inputs and caches it,
    through the composite action `.github/actions/islenska-data`, used by all
    three workflows (see "Data package" in `AGENTS.md`).
  - Copyright years are 2026.

GreynirKbd: mideind/GreynirKbd#5 (branch `binpackage-2.0.0`) moves its
submodule from 1.4.0 to 2.0.0 and its `data/grammar/compressed.bin` to the
islenska-data 5.0.0 file. Its replays and error sets are bit-identical to
1.4.0, and its docs no longer mention `--compact` or `tools/parity.py`.

Open: the CI warnings about Node.js 20 actions (`checkout@v4`,
`setup-python@v5`, `cache@v4`, `upload-artifact@v4`, `download-artifact@v4`)
and the move of `ubuntu-latest` to Ubuntu 26 from 2026-10-19. Neither
affected the release.

### Lessons from 2.0.0

- `tools/compact.py`'s `_candidates()` swallows every exception as "no
  splits". A broken compounder therefore used to yield a silent full build.
  `compact.select()` now loads the DAWGs up front, and binpack exits if
  nothing is dropped; keep both guards.
- Test data-location changes with a from-scratch build: remove
  `src/islenska/resources/compressed.bin` and run `tools/binpack.py`. The
  local file being present hid the bug above until CI ran.

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

`compressed.bin` is always a compact build: `tools/binpack.py` leaves out the
word forms of compounds that the compounder regenerates exactly, and libbin
restores them on lookup; see "Compact build" in `AGENTS.md`. There is no full
build or parity tool any more (removed 2026-10-02 by decision). After changing
the selection rules (`tools/compact.py`) or the restoration code
(`libbin/src/dict.cpp`), rebuild the data and run the test suite
(`test/test_compact.py`, `test/test_canonical_order.py`).

Installed islenska reads its data from the separate package `islenska-data`
(`islenska-data/` in this repo; see "Data package" in `AGENTS.md`), a
dependency since 2.0.0; `basics.data_dir()` uses islenska's own
`src/islenska/resources/` instead when it holds any data file.
Stage and build it with `uv run python tools/data_package.py && uv build
--wheel islenska-data -o dist-data`.

## Roadmap

### 1.5.0 (released 2026-10-02)

Deterministic order of case lookups (PR #28) and Python 3.10+ only, with
`cp310-abi3` wheels (PR #29). Python 3.9 users stay on 1.4.0.

### 2.0.0 (released 2026-10-13): data package, new wheels

Why the split: after 1.5.0 the `islenska` project used about 8.7 GB of
PyPI's default 10 GB project limit, ~454 MB per release, because every wheel
and the sdist carried the ~50 MB `compressed.bin`. The PyPy wheels would
have made that ~860 MB. The data package has its own 10 GB and is released
only when the data change, as a wheel only (an sdist would just duplicate
the data). The 2.0.0 islenska wheels total 4.9 MB. Do not delete old
releases to save space: 1.0.2-1.0.4 take 4.6 GB, but deleting them is
irreversible and would push anyone pinned to them onto source builds.

islenska-data versions are `<format major>.<format minor>.<data release>`:
5.0.x for `Greynir 05.00.00`. New BÍN data in the same format means a new
patch release of islenska-data and no islenska release. A new format needs a
new islenska-data minor or major version and an islenska release that
requires it. The process is in `RELEASING.md`.

Compact-only data, as verified on 2026-10-02 against the then-existing full
build with a Bin-level comparison: 11.9 k words, every public lookup method,
`Bin` with default and non-default options, and `GreynirBin`; 1.37 M
comparisons.

- Content is identical, dropped compounds included: they come back as
  genuine BÍN entries with their own bin_ids, even with compounding off.
- The order is identical after the canonical order (#30). Before it,
  `cast_to_dative("kvótakerfi")` gave *kvótakerfum*.
- Uncached `Bin.lookup` per word: random forms 14 -> 21 µs, forms of
  dropped compounds 12 -> 24 µs, made-up compounds 44 -> 61 µs (a trie miss
  now tries restoration first). Bin's cache absorbs much of this.
- `compressed.bin` is 55 MB (26 MB deflated); the data wheel is ~30 MB.
- Still open: whether anyone needs a full file. Nobody has asked;
  `ISLENSKA_BIN_FILE` can point at one built by an older checkout.

PyPy: PyPy 8.0 (September 2026) changed the ABI tag from `pp73` to `pp80`,
and PyPy 3.12 (beta in 8.0) is the line going forward. Both ABIs of
`pp311` ship, because pip installs the newest version even if it has to
build from source; dropping `pp73` would move that breakage to PyPy 7.3
users. Retire the cibuildwheel 4.2.1 step (pp73) once PyPy 7.3 is no longer
worth supporting. PyPy's abi3 support is incomplete in 8.0 and does not suit
a CFFI extension anyway, so PyPy keeps one wheel per ABI.

### Possible later step: one wheel for every non-CPython interpreter

Load `libbin` as a plain shared library through CFFI's ABI mode (`dlopen`)
and ship it as a `py3-none-<platform>` wheel. Such a wheel works on every PyPy
version, including future ABI bumps, and on GraalPy, with no rebuilds.
CPython keeps the faster API-mode `cp310-abi3` wheels, which installers prefer
over `py3-none` when both match.
