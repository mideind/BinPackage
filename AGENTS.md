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

# Build the compressed binary data (requires KRISTINsnid.csv.zip in src/islenska/resources/)
uv run python tools/binpack.py

# Build a compact variant (see "Compact build" below) and check it against the full file
uv run python tools/binpack.py --compact -o src/islenska/resources/compressed-compact.bin
uv run python tools/parity.py src/islenska/resources/compressed.bin src/islenska/resources/compressed-compact.bin --sample 200000

# Build DAWG structures for compound word handling
uv run python tools/dawgbuilder.py
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
# (honors pyrightconfig.json: strict mode, target Python 3.9, checks src/test/tools)
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
- Supports Python 3.9+ on CPython and PyPy
- Binary data file (`compressed.bin`, format `Greynir 05.00.00`) is ~95MB,
  mapped to memory at runtime; a compact build is ~48MB
- Compound word algorithm can be disabled via `Bin(add_compounds=False)`

## Compact build

`tools/binpack.py --compact` writes a `compressed.bin` without the word forms
of compounds whose paradigm is exactly prefix + the paradigm of their last
component, as decided by `tools/compact.py` (rules in its docstring). Each
dropped lemma keeps a record (subcategory, ksnid string, head lemmas) and
`libbin/src/dict.cpp` restores its entries on lookup by slicing the word with
the compounder, so the public API returns identical results, bin_ids
included. `tools/parity.py FULL COMPACT` proves that; run it after any change
to the selection rules or to the restoration code. The CI job `compact`
builds both files, runs the test suite against the compact one and a
sampled parity check. The test suite runs against a compact file with
`ISLENSKA_BIN_FILE=path/to/compressed-compact.bin uv run pytest`.
