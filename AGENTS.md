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
   - Interfaces with C++ code via CFFI for fast lookups

2. **Main API** (`src/islenska/bindb.py`)
   - `Bin` class provides high-level interface for word lookups
   - Implements caching with LFU strategy
   - Handles compound word algorithm

3. **Compound Word Algorithm** (`src/islenska/dawgdictionary.py`)
   - Uses Directed Acyclic Word Graphs (DAWGs) for prefix/suffix matching
   - Finds optimal compound splits (fewest components, longest suffix)
   - Prefixes stored in `resources/prefixes.txt`, suffixes in `resources/suffixes.txt`

4. **C++ Extension** (`src/islenska/bin.cpp`, `bin.h`)
   - Provides fast binary search in compressed data
   - Built using CFFI (configured in `bin_build.py`)
   - Creates platform-specific `.so` files

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
- Binary data file (`compressed.bin`) is ~82MB, mapped to memory at runtime
- Compound word algorithm can be disabled via `Bin(add_compounds=False)`
