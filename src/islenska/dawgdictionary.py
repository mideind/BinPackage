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

from typing import Iterator, List, Optional, Set, IO, Any, cast
import os
import re
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

# The Unicode SOFT HYPHEN (U+00AD): an invisible character that marks a
# permitted line-break position, rendered as a hyphen only if the break is
# actually taken by the typesetter. Spelled as an escape so it stays visible
# in editors.
SOFT_HYPHEN = "\u00ad"

# Tokens are hyphenated independently between these hard boundaries, which
# are preserved verbatim in the output.
_HARD_BOUNDARY_RE = re.compile(r"([ \-])")


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
    def _iter_legal_compound_splits(cls, word: str) -> Iterator[List[str]]:
        """Yield each legal compound-word split of ``word`` in
        heuristic-ranked order (longest last part, fewest total parts).
        A split is legal when its suffix appears in the suffix DAWG and
        all preceding parts appear in the prefix DAWG. Callers that only
        need the best split can consume a single item via next();
        callers that need to inspect several candidates can materialize
        the full list."""
        w = cls.dawg().find_combinations(word)
        if not w:
            return
        # Sort by (1) longest last part and (2) the lowest overall number of parts
        w.sort(key=lambda x: (len(x[-1]), -len(x)), reverse=True)
        prefixes = cls.dawg_prefixes()
        suffixes = cls.dawg_suffixes()
        for combination in w:
            if (
                combination[-1] in suffixes
                and all(c in prefixes for c in combination[0:-1])
            ):
                yield combination

    @classmethod
    def slice_compound_word_candidates(cls, word: str) -> List[List[str]]:
        """Get every legal compound-word split of ``word``, sorted by the
        ranking heuristic (longest last part, fewest total parts).
        Each candidate is a list of word parts whose suffix is a legal
        suffix and whose prefixes are all legal prefixes."""
        return list(cls._iter_legal_compound_splits(word))

    @classmethod
    def slice_compound_word(cls, word: str) -> List[str]:
        """Get best combination of word parts if such a combination exists."""
        for combination in cls._iter_legal_compound_splits(word):
            return combination
        return []

    @classmethod
    def _best_multipart_split(cls, s: str) -> Optional[List[str]]:
        """Return the heuristically preferred split of ``s`` into two or
        more parts, or None if ``s`` has no legal compound split. The
        single-part candidate (the whole word, which carries no internal
        boundary) is skipped; the candidates are already ranked so that the
        winner has the longest last part and the fewest parts."""
        return next(
            (c for c in cls.slice_compound_word_candidates(s) if len(c) > 1), None
        )

    @classmethod
    def _primary_seam_offsets(cls, s: str) -> Set[int]:
        """Return the boundary offsets of the single best multi-part split of
        ``s``, without descending into the parts, e.g. ``skólabókasafn`` ->
        {5} (``skóla|bókasafn``)."""
        best = cls._best_multipart_split(s)
        if best is None:
            return set()
        offsets: Set[int] = set()
        pos = 0
        for part in best[:-1]:
            pos += len(part)
            offsets.add(pos)
        return offsets

    @classmethod
    def _natural_seam_offsets(cls, s: str) -> Set[int]:
        """Return the boundaries of the natural compound decomposition of
        ``s``: take the preferred split (longest last part, fewest parts),
        keep the modifier part(s), and descend *only* into the head — the
        last part — repeating until the head no longer splits, e.g.
        ``skólabókasafn`` -> {5, 9} (``skóla|bóka|safn``).

        Only the head is re-sliced because the head is always a legal
        standalone suffix, so its sub-splits are genuine compound seams.
        Modifier parts are connecting/genitive forms whose standalone
        re-slicing manufactures spurious seams (``byggingar`` would split as
        ``bygg|ingar``), so they are left whole. The trade-off is that a
        compound *modifier* is not decomposed (``morgunverðarhlaðborð`` ->
        ``morgunverðar|hlað|borð``, missing ``morgun|verðar``) — we accept a
        missed break rather than risk a wrong one."""
        offsets: Set[int] = set()
        base = 0
        while True:
            best = cls._best_multipart_split(s)
            if best is None:
                break
            pos = base
            for part in best[:-1]:
                pos += len(part)
                offsets.add(pos)
            # Descend into the head (the last part) only
            base, s = pos, best[-1]
        return offsets

    @classmethod
    def _seam_offsets(cls, token: str, mode: str) -> Set[int]:
        """Compute compound-part boundary offsets within a single token,
        independent of case. The lowercase form is tried first, as it is by
        far the most productive in the DAWG (capitalized and all-uppercase
        common nouns do not match directly); we then fall back to the form as
        given and finally to a capitalized form, which lets proper nouns
        stored only in capitalized form — e.g. ``Hallgrímskirkja`` — still be
        split, whether they arrive capitalized or in all-uppercase. Icelandic
        case-folding is one-to-one and length-preserving within Latin-1, so
        the offsets apply unchanged to the original-case token."""
        if mode == "natural":
            finder = cls._natural_seam_offsets
        elif mode == "primary":
            finder = cls._primary_seam_offsets
        else:
            raise ValueError(
                f"Unknown soft-hyphenation mode {mode!r}; "
                "expected 'natural' or 'primary'"
            )
        tried: Set[str] = set()
        for variant in (token.lower(), token, token.capitalize()):
            if variant in tried:
                continue
            tried.add(variant)
            offsets = finder(variant)
            if offsets:
                return offsets
        return set()

    @classmethod
    def _hyphenate_token(
        cls,
        token: str,
        mode: str,
        min_left: int,
        min_right: int,
        min_word: int,
        hyphen: str,
    ) -> str:
        """Insert ``hyphen`` at the eligible compound boundaries of a single
        token (one with no internal spaces or hyphens)."""
        n = len(token)
        if n < min_word:
            return token
        # Keep only breaks that leave at least min_left characters before and
        # min_right characters after the break (lefthyphenmin/righthyphenmin)
        offsets = sorted(
            o for o in cls._seam_offsets(token, mode) if min_left <= o <= n - min_right
        )
        if not offsets:
            return token
        pieces: List[str] = []
        prev = 0
        for o in offsets:
            pieces.append(token[prev:o])
            prev = o
        pieces.append(token[prev:])
        return hyphen.join(pieces)

    @classmethod
    def insert_soft_hyphens(
        cls,
        word: str,
        *,
        mode: str = "natural",
        min_left: int = 2,
        min_right: int = 2,
        min_word: int = 8,
        hyphen: str = SOFT_HYPHEN,
    ) -> str:
        """Return ``word`` with soft hyphens (U+00AD by default) inserted at
        its internal compound-component boundaries, so a typesetter may break
        the word across lines at morphologically valid points.

        ``mode`` selects the boundary granularity:

        * ``"natural"`` (default): the natural decomposition — the preferred
          split (longest last part, fewest parts) with its head recursively
          decomposed, e.g. ``skólabókasafn`` -> ``skóla|bóka|safn``.
        * ``"primary"``: only the single most-preferred boundary, e.g.
          ``skólabókasafn`` -> ``skóla|bókasafn``.

        ``min_left`` / ``min_right`` enforce a minimum number of characters on
        either side of any break (the typographic ``lefthyphenmin`` /
        ``righthyphenmin``); ``min_word`` skips words shorter than this many
        characters. Real hyphens and spaces are treated as hard boundaries and
        preserved, with each token between them hyphenated independently.
        Pre-existing soft hyphens are stripped first, so the function is
        idempotent. Words with no legal compound split (and those containing
        characters outside the Latin-1 range) are returned unchanged.

        This is the pure-DAWG primitive; ``Bin.soft_hyphenate`` wraps it with
        an additional BÍN-backed guard against splitting function words."""
        if not word:
            return word
        # Strip any pre-existing soft hyphens so the result is idempotent.
        # We always remove the canonical U+00AD (not the ``hyphen`` argument),
        # so that overriding ``hyphen`` with a visible "-" cannot accidentally
        # delete real hyphens, which act as hard boundaries below.
        word = word.replace(SOFT_HYPHEN, "")
        out: List[str] = []
        for token in _HARD_BOUNDARY_RE.split(word):
            if token in (" ", "-", ""):
                out.append(token)
            else:
                out.append(
                    cls._hyphenate_token(
                        token, mode, min_left, min_right, min_word, hyphen
                    )
                )
        return "".join(out)
