# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.

## Project Overview

BinPackage is a Python package that encapsulates the Database of Icelandic Morphology (BÍN)
into an efficient binary format. It provides fast word form lookups, grammatical variant
generation, and compound word handling for the Icelandic language.

## Key Commands

This project is managed with [uv](https://docs.astral.sh/uv/): dependencies are
declared in `pyproject.toml` and pinned in `uv.lock`. Run dev tools through
`uv run` so they use the locked project environment.

### Development Setup
```bash
# Sync the environment, including dev dependencies (pytest, pyright)
uv sync --extra dev

# Build the compressed binary data, a compact build (see "Compact build" below;
# requires KRISTINsnid.csv.zip, unzipped, in src/islenska/resources/; ~3 min)
uv run python tools/binpack.py

# Build DAWG structures for compound word handling
uv run python tools/dawgbuilder.py

# Stage the built data into the islenska-data package and build its wheel
# (see "Data package" below; not published yet)
uv run python tools/data_package.py
uv build --wheel islenska-data -o dist-data
```

### Rebuilding C++ Extensions

**Always use `uv pip install -e .` to rebuild C++ extensions** (not `bin_build.py` directly):

```bash
uv pip install -e . --no-build-isolation
```

Running `bin_build.py` directly creates `.so` files in the wrong location (`islenska/` instead of `src/islenska/`) because it doesn't respect the `src/` layout from `pyproject.toml`.

### Testing
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest test/test_bin.py
uv run pytest test/test_ord.py

# Run tests with verbose output
uv run pytest -v
```

### Linting and Type Checking
```bash
# Type-check with pyright
# (honors pyrightconfig.json: strict mode, target Python 3.10, checks src/test/tools)
uv run pyright

# Lint with ruff (ruff is not a project dependency; install it separately,
# as CI does)
ruff check src/islenska
```

## Architecture

### Core Components

1. **Binary Compression System** (`src/islenska/bincompress.py`)
   - Handles the compressed binary format that stores BÍN data
   - Uses memory-mapped files for efficient access
   - Interfaces with the C++ library (libbin) via CFFI for fast lookups
   - `BinCompressed(fname)` opens a specific file; the `ISLENSKA_BIN_FILE`
     environment variable overrides the packaged one

2. **Main API** (`src/islenska/bindb.py`)
   - `Bin` class provides high-level interface for word lookups
   - Implements caching with LFU strategy
   - Handles compound word algorithm

3. **Compound Word Algorithm** (`src/islenska/dawgdictionary.py`)
   - Uses Directed Acyclic Word Graphs (DAWGs) for prefix/suffix matching
   - Finds optimal compound splits (fewest components, longest suffix)
   - Prefixes stored in `resources/prefixes.txt`, suffixes in `resources/suffixes.txt`

4. **C++ Library** (`libbin/`, see `libbin/README.md`)
   - `include/libbin/bin.h`: the C API; CFFI reads the declarations between
     the `CFFI-BEGIN`/`CFFI-END` markers, so that section must stay plain C
   - `src/trie.cpp`: the packed word-form trie; `src/dawg.cpp`: the DAWG
     reader and compound-split enumerator; `src/dict.cpp`: the dictionary,
     compound candidates and compact restoration; `src/api.cpp`: the C API
   - Built into the `_bin` extension by CFFI (`src/islenska/bin_build.py`),
     and standalone with CMake (`libbin/CMakeLists.txt`, target `libbin::bin`)
   - Handles are immutable and thread-safe; all strings are Latin-1

### Data Flow

1. Raw BÍN data (CSV) → `tools/binpack.py` → `resources/compressed.bin`
2. Prefix/suffix lists → `tools/dawgbuilder.py` → DAWG binary files
3. Runtime: User query → `Bin` class → Binary search (C++) → Results with compound handling

### Key Classes

- `BinEntry`: Basic format tuple (6 attributes)
- `Ksnid`: Augmented format class (15 attributes)
- `Bin`: Main API class for all lookups
- `BinCompressed`: Low-level binary data interface
- `Wordbase`: DAWG-based compound word handler

## Important Notes

- The package name is `islenska` on PyPI, not `BinPackage`
- BÍN data is under CC BY-SA 4.0 license from Stofnun Árna Magnússonar
- Supports Python 3.10+ on CPython and PyPy
- Binary data file (`compressed.bin`, format `Greynir 05.00.00`) is ~55MB,
  mapped to memory at runtime; it is always a compact build
- Compound word algorithm can be disabled via `Bin(add_compounds=False)`

## Compact build

`tools/binpack.py` writes a `compressed.bin` without the word forms of
compounds whose paradigm is exactly prefix + the paradigm of their last
component, as decided by `tools/compact.py` (rules in its docstring), about
half the size of a file with every form. Each dropped lemma keeps a record
(subcategory, ksnid string, head lemmas) and `libbin/src/dict.cpp` restores
its entries on lookup by slicing the word with the compounder, so the public
API returns the BÍN entries, bin_ids included. There is no full
(non-compact) build any more; libbin still reads a file without a compact
section, in which nothing is dropped. `test/test_compact.py` checks known
dropped compounds against their BÍN rows.

Lookups return the readings of a word form in a canonical order: by bin_id,
then by the position of the inflection in its category's paradigm
(`resources/mark_order.csv`), then in source order. `tools/binpack.py`
stores them in that order (`canonical_entries()`), a restored compound copies
the order of its head's readings, and `test/test_canonical_order.py` checks
it. Keep both sides in step when changing either. The CI job `libbin`
builds the C++ library standalone and runs its smoke test on the data.

## Data package

The data files (`compressed.bin` and the three DAWGs, `basics.DATA_FILES`)
can come from a separate pure-Python package, `islenska-data` (import name
`islenska_data`, in `islenska-data/` at the root of the repository), so that
the code wheels stay small. `basics.data_dir()` picks the directory:
`islenska_data`'s if it is installed, holds `compressed.bin` and declares the
data format that this islenska reads (`islenska_data.FORMAT`), otherwise
islenska's own `resources/`; `ISLENSKA_BIN_FILE` still overrides
`compressed.bin`. Its version is `<format major>.<format minor>.<data
release>` (5.0.x for `Greynir 05.00.00`). `tools/data_package.py` checks the
built files and copies them into the package; the CI job `data-package`
builds an islenska wheel without data and the islenska-data wheel, installs
both into a fresh environment and runs the test suite. As of 2026-10-02 this
is tentative: islenska wheels still embed the data, islenska does not depend
on islenska-data, and nothing publishes it.
