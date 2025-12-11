"""
    BinPackage

    Compound word analyzer

    Copyright © 2025 Miðeind ehf.

    This software is licensed under the MIT License:

        Permission is hereby granted, free of charge, to any person
        obtaining a copy of this software and associated documentation
        files (the "Software"), to deal in the Software without restriction,
        including without limitation the rights to use, copy, modify, merge,
        publish, distribute, sublicense, and/or sell copies of the Software,
        and to permit persons to whom the Software is furnished to do so,
        subject to the following conditions:

        The above copyright notice and this permission notice shall be
        included in all copies or substantial portions of the Software.

        THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
        EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
        MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
        IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
        CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
        TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
        SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

    The compound word analyzer takes a word not found in the
    BIN word database and attempts to resolve it into parts
    as a compound word.

    It uses a Directed Acyclic Word Graph (DAWG) internally
    to store a large set of words in an efficient structure in terms
    of storage and speed.

    The graph is pre-built and stored in a file that
    is loaded at run-time by DawgDictionary.

"""

from typing import List, Optional, IO, Any, cast
import os
import threading
import mmap
import json

import importlib.resources as importlib_resources

# CFFI bindings to the C++ implementation
from ._bin import lib as lib_unknown, ffi as ffi_unknown  # type: ignore


# Go through shenanigans to satisfy Pylance/Mypy
dawg_cffi = cast(Any, lib_unknown)
ffi = cast(Any, ffi_unknown)


_PATH = os.path.dirname(__file__) or "."


class Dawg:
    """A wrapper for the C++ DAWG implementation."""

    def __init__(self, fname: str) -> None:
        self._handle: Optional[object] = None
        self._mmap: Optional[mmap.mmap] = None
        self._stream: Optional[IO[bytes]] = None

        self._stream = open(fname, "rb")
        self._mmap = mmap.mmap(self._stream.fileno(), 0, access=mmap.ACCESS_READ)

        # Pass the memory map pointer to the C++ loader
        self._handle = dawg_cffi.dawg_load(ffi.from_buffer(self._mmap))
        if not self._handle:
            raise MemoryError(f"Unable to load DAWG file: {fname}")

    def __del__(self) -> None:
        if self._handle:
            dawg_cffi.dawg_unload(self._handle)
            self._handle = None
        if self._mmap:
            self._mmap.close()
            self._mmap = None
        if self._stream:
            self._stream.close()
            self._stream = None

    def __contains__(self, word: str) -> bool:
        if not self._handle:
            return False
        try:
            word_bytes = word.encode("latin-1")
        except UnicodeEncodeError:
            # Word contains characters outside Latin-1, so it can't be in the DAWG
            return False
        return dawg_cffi.dawg_contains(self._handle, word_bytes)

    def find_combinations(self, word: str) -> List[List[str]]:
        """Attempt to slice a word into valid parts using the DAWG."""
        if not self._handle:
            return []

        try:
            word_bytes = word.encode("latin-1")
        except UnicodeEncodeError:
            # Word contains characters outside Latin-1, so it can't be split
            return []
        result_ptr = dawg_cffi.dawg_find_combinations(self._handle, word_bytes)
        if not result_ptr:
            return []

        try:
            # C++ now returns UTF-8 bytes
            result_bytes = ffi.string(result_ptr)
            return json.loads(result_bytes)  # json.loads accepts UTF-8 bytes
        finally:
            dawg_cffi.dawg_free_string(result_ptr)


class Wordbase:
    """Container for singleton instances of the DAWG dictionaries."""

    _dawg_all: Optional[Dawg] = None
    _dawg_prefixes: Optional[Dawg] = None
    _dawg_suffixes: Optional[Dawg] = None

    _lock = threading.Lock()

    @staticmethod
    def _load_resource(resource: str) -> Dawg:
        """Load a Dawg from a file resource."""
        if __package__:
            ref = importlib_resources.files("islenska") / "resources" / f"{resource}.dawg.bin"
            with importlib_resources.as_file(ref) as path:
                pname = str(path)
        else:
            pname = os.path.abspath(
                os.path.join(_PATH, "resources", resource + ".dawg.bin")
            )
        return Dawg(pname)

    @classmethod
    def dawg(cls) -> Dawg:
        """Load the combined dictionary."""
        with cls._lock:
            if cls._dawg_all is None:
                cls._dawg_all = Wordbase._load_resource("ordalisti-all")
            assert cls._dawg_all is not None
            return cls._dawg_all

    @classmethod
    def dawg_prefixes(cls) -> Dawg:
        """Load the dictionary of words allowed as prefixes."""
        with cls._lock:
            if cls._dawg_prefixes is None:
                cls._dawg_prefixes = Wordbase._load_resource("ordalisti-prefixes")
            assert cls._dawg_prefixes is not None
            return cls._dawg_prefixes

    @classmethod
    def dawg_suffixes(cls) -> Dawg:
        """Load the dictionary of words allowed as suffixes."""
        with cls._lock:
            if cls._dawg_suffixes is None:
                cls._dawg_suffixes = Wordbase._load_resource("ordalisti-suffixes")
            assert cls._dawg_suffixes is not None
            return cls._dawg_suffixes

    @classmethod
    def slice_compound_word(cls, word: str) -> List[str]:
        """Get best combination of word parts if such a combination exists."""
        # We get back a list of lists, i.e. all possible compound word combinations
        # where each combination is a list of word parts.
        w = cls.dawg().find_combinations(word)
        if w:
            # Sort by (1) longest last part and (2) the lowest overall number of parts
            w.sort(key=lambda x: (len(x[-1]), -len(x)), reverse=True)
            prefixes = cls.dawg_prefixes()
            suffixes = cls.dawg_suffixes()
            # Loop over the sorted combinations until we find a legal one,
            # i.e. where the suffix is a legal suffix and all prefixes are
            # legal prefixes
            for combination in w:
                if (
                    combination[-1] in suffixes
                    and all(c in prefixes for c in combination[0:-1])
                ):
                    # Valid combination: return it
                    return combination
        # No legal combination found
        return []
