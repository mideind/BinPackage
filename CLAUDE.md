# CLAUDE.md

Guidance for Claude Code in this repository. `AGENTS.md` holds the full project
overview and architecture notes; the day-to-day essentials are below.

## Status (2026-10-13): where to pick up

**islenska 2.0.0 is merged on `main` and ready to release; nothing is
published yet.** The next step is the release itself (checklist below). The
1.6.0 plan became 2.0.0 because of the data split and the new result order.

On `main` (PRs #30-#35, all merged 2026-10-13 with green PR CI):

- #30 canonical order of a form's readings: by bin_id, then paradigm order
  (`mark_order.csv`), then source order, in binpack and in libbin's compound
  restoration.
- #31 `compressed.bin` is always a compact build; the full build and
  `tools/parity.py` are gone.
- #32 the `islenska-data` package (`islenska-data/`) and its release
  workflow `data-release.yml`.
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

Verified: a wheel dry run (tag `2.0.0-test2`, since deleted) built all 20
wheels plus the sdist, 4.9 MB in all. Every wheel passed the smoke test. A
from-scratch `binpack.py` run is byte-identical to the 2026-10-02 build
(163,349 lemmas dropped).

### Release checklist (next session starts here)

The `pypi` environment has no protection rules: a tag publishes as soon as
its build passes, and PyPI uploads cannot be undone. Confirm with the user
before pushing the real tags.

1. Check that the `tests` run on `main` for the merge of #35 is green. It
   also saves the islenska-data wheel to the Actions cache, so tag runs
   reuse it: `gh run list --branch main -L 3`.
2. islenska-data:
   `git tag -a data-5.0.0 -m "islenska-data 5.0.0" && git push origin data-5.0.0`.
   `data-release.yml` checks the tag against `islenska-data/pyproject.toml`,
   tests and publishes. The first upload creates the PyPI project through
   the pending Trusted Publisher (`mideind/BinPackage`, workflow
   `data-release.yml`, environment `pypi`), under the account of whoever
   added that publisher; move it to the Miðeind organization if needed.
   Check https://pypi.org/project/islenska-data/.
3. islenska, once islenska-data is on PyPI:
   `git tag -a 2.0.0 -m "Release version 2.0.0" && git push origin 2.0.0`.
   `wheels.yml` publishes 20 wheels and the sdist. Then
   `pip install islenska==2.0.0` in a fresh venv and run one lookup.
4. `gh release create 2.0.0` with notes covering:
   - The data now come in the separate `islenska-data` package (~30 MB,
     installed automatically, downloaded again only when the data change);
     islenska wheels are 0.1-0.8 MB.
   - The canonical order (#30) changes some first-match results relative to
     1.5.0, mostly for the better (singular before plural): e.g.
     `cast_to_dative("kvótakerfi")` now gives *kvótakerfi*, not *kvótakerfum*.
   - Compact data (#31): about half the size; compounds are restored on
     lookup, a little slower uncached (see "Roadmap" below).
   - New wheels: PyPy 8.0 and PyPy 3.12, and Linux aarch64 (CPython and
     PyPy); PyPy 7.3 wheels kept.
   - ~90 MB less private memory per process (#34, thanks to sverrirs).
   - Also new since 1.5.0: `lookup_variants` accepts the adverb degree
     marks FST/EST (#33).
5. Afterwards:
   - Update the GreynirKbd repo: move its BinPackage submodule past 1.4.0
     and rebuild its `data/grammar`. Its notes still mention `binpack.py
     --compact` (now a no-op) and a full-vs-compact parity check (there is
     no full build any more).
   - Delete the merged remote branches (`canonical-entry-order`,
     `compact-only`, `data-package`, `release-2.0`) if GitHub kept them.

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

### 2.0.0 (merged 2026-10-13, to be released): data package, new wheels

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
