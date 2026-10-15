# CLAUDE.md

Guidance for Claude Code in this repository. `AGENTS.md` holds the full project
overview and architecture notes; the day-to-day essentials are below.

## Status (2026-10-15): 2.1.0 released

**islenska 2.1.0 was released on 2026-10-15** (tag `2.1.0`, GitHub release
2.1.0): free-threaded CPython. PyPI holds 30 islenska wheels plus the sdist.
The data are unchanged: 2.1.0 uses islenska-data 5.0.0, as 2.0.0 does. It is
2.1.0 and not 2.0.1 because it adds a feature, raises the cffi floor and
removes `LFU_Cache` (the semver rule in `RELEASING.md`).

What went into 2.1.0 (PR #39 by HaukurPall plus three review commits,
merged with a merge commit):

- Free-threaded CPython has no abi3, so `setup.py` and `bin_build.py` build
  a regular extension when `Py_GIL_DISABLED` is set. cffi `>=2.0.0` (build
  and runtime): the first cffi that runs without the GIL.
- `wheels.yml` builds `cp314t` and `cp315t`; `test/wheel_smoke.py` asserts
  that the GIL stays off. A step checks that all six wheel types exist for
  every architecture, because cibuildwheel passes when a build selector
  matches nothing.
- `python-package.yml` tests 3.14t and 3.15t, a second time with
  `pytest-run-parallel --parallel-threads=8` (tests that use `monkeypatch`
  run serially there).
- `GenerationalCache` (`basics.py`) replaces `LFU_Cache`: two generations of
  up to 4096 word forms, shared by all threads and read without a lock. A
  race at worst computes a key twice or drops a generation early. Each entry
  is a `_CachedLookup` (`bindb.py`) holding the Ksnid list and, made on first
  use, the BinEntry tuples without and with suffix-only (birting 'S') entries.
- `Bin._init_lock` serializes the one-time class setup in `Bin.__init__`
  (`_bc`) and `GreynirBin.__init__` (BinErrata.conf).
- The mmap buffers are released with `ffi.release`, which fixed a
  `BufferError` at shutdown on free-threaded builds.
- `bin_build.py` adds `-O2` when neither the interpreter's CFLAGS nor the
  CFLAGS/CXXFLAGS environment variables hold an `-O` flag (Gentoo's Python
  records none, which left libbin at `-O0`, 4× slower).
- New tests: `test/test_cache.py`, `test/test_threads.py`.

Measured in #39 (`Bin.lookup` on real text, thousands of lookups/s): GIL
build, 1 thread, 204 → 313; 3.14t, 8 threads, 155 → 1008 (8 processes on
the GIL build reach 890).

Verified: the dry run `2.0.1-test1` built all 30 wheels (the tag was deleted
afterwards), then the release run passed. A fresh `pip install
islenska==2.1.0` on CPython 3.14 (GIL) pulls in islenska-data 5.0.0 and
works. The free-threaded wheels are tested only by the CI smoke tests; 3.14t
is not installed on this box.

### 2.0.0 (released 2026-10-13)

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
    - Linux aarch64 wheels on `ubuntu-24.04-arm` (`ubuntu-26.04-arm` since
      #38).
    - `test/wheel_smoke.py` runs for every wheel with the run's own data
      wheel.
    - No `.bin` is allowed in any wheel or the sdist.
  - CI builds the islenska-data wheel once per set of inputs and caches it,
    through the composite action `.github/actions/islenska-data`, used by all
    three workflows (see "Data package" in `AGENTS.md`).
  - Copyright years are 2026.

GreynirKbd: mideind/GreynirKbd#5, merged 2026-10-13, moved its submodule
from 1.4.0 to 2.0.0 and its `data/grammar/compressed.bin` to the
islenska-data 5.0.0 file. Its replays and error sets are bit-identical to
1.4.0, and its docs no longer mention `--compact` or `tools/parity.py`.

Tested locally after the release, installed from PyPI into fresh venvs:
PyPy 3.12 (8.0.0) gets the `pp312-pypy312_pp80` wheel (42 passed, the
tracemalloc test skipped), and CPython 3.15.0 gets the `cp310-abi3` wheel
(43 passed, no deprecation warnings). 3.15 is in the CI matrix and the
classifiers since 2026-10-13.

CI after the release (#38): every action is on its Node.js 24 version, the
Slack failure notifications go through `slackapi/slack-github-action`, and
every Linux job runs on an explicit `ubuntu-26.04` (`ubuntu-26.04-arm` for
aarch64) instead of `ubuntu-latest`, which moves to Ubuntu 26 from
2026-10-19. Windows and macOS keep `windows-latest` and `macos-14`.

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

### 2.1.0 (released 2026-10-15): free-threaded Python

`cp314t` and `cp315t` wheels and a word cache that threads share without a
lock (PR #39); see "Status" above. Free-threaded CPython has no stable ABI,
so each new version needs a wheel of its own: for 3.16t, add `cp316t-*` to
`CIBW_BUILD` and `cp316-cp316t` to the expected set of the wheel check in
`wheels.yml`, and `3.16t` to the matrix in `python-package.yml`.

### Possible later step: one wheel for every non-CPython interpreter

Load `libbin` as a plain shared library through CFFI's ABI mode (`dlopen`)
and ship it as a `py3-none-<platform>` wheel. Such a wheel works on every PyPy
version, including future ABI bumps, and on GraalPy, with no rebuilds.
CPython keeps the faster API-mode `cp310-abi3` wheels, which installers prefer
over `py3-none` when both match.
