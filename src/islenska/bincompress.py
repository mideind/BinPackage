#!/usr/bin/env python
"""

    BinPackage

    Low-level access module for the compressed BÍN dictionary

    Copyright © 2025 Miðeind ehf.
    Original author: Vilhjálmur Þorsteinsson

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

    This module manages a compressed BÍN dictionary in memory, allowing
    various kinds of lookups. The dictionary is read into memory as
    a BLOB (via mmap). No auxiliary dictionaries or other data structures
    should be needed. The binary image is shared between running processes.

    The compression of the dictionary is performed in tools/binpack.py.

    This is a lower-level module used by the higher-level Bin class in
    bindb.py. Normally, clients should interact with the Bin class, which
    is likely to have a more stable interface than BinCompressed.

    ************************************************************************

    LICENSE NOTICE:

    BinPackage embeds the 'Database of Modern Icelandic Inflection' /
    'Beygingarlýsing íslensks nútímamáls' (see https://bin.arnastofnun.is),
    abbreviated BÍN.

    The BÍN source data are publicly available under the CC-BY-4.0 license, as further
    detailed here in English: https://bin.arnastofnun.is/DMII/LTdata/conditions/
    and here in Icelandic: https://bin.arnastofnun.is/gogn/mimisbrunnur/.

    In accordance with the BÍN license terms, credit is hereby given as follows:

        Beygingarlýsing íslensks nútímamáls.
        Stofnun Árna Magnússonar í íslenskum fræðum.
        Höfundur og ritstjóri Kristín Bjarnadóttir.

    See the comments in the tools/binpack.py file for further information.

"""

from typing import (
    Any,
    FrozenSet,
    Iterable,
    Set,
    Tuple,
    List,
    Optional,
    Union,
    cast,
)

import os
import struct
import functools
import mmap
import importlib.resources as importlib_resources

# Import the CFFI wrapper for the bin.cpp C++ module (see also build_bin.py)
# pylint: disable=no-name-in-module
from ._bin import lib as lib_unknown, ffi as ffi_unknown  # type: ignore

# Go through shenanigans to satisfy Pylance/Mypy
bin_cffi = cast(Any, lib_unknown)
ffi = cast(Any, ffi_unknown)

# ruff: noqa: E402
from .basics import (
    InflectionFilter,
    BinEntryTuple,
    Ksnid,
    ALL_GENDERS,
    mark_to_set,
    BIN_COMPRESSOR_VERSION,
    BIN_COMPRESSED_FILE,
    BIN_FILE_ENV,
    UINT32,
    SUBCAT_BITS,
)


class BinCompressedPure:
    """Base class for the compressed binary dictionary.

    This class provides the Python infrastructure and methods that haven't
    been migrated to C++. The BinCompressed class inherits from this and
    overrides key methods with optimized C++ implementations.

    Note: Do not instantiate this class directly. Use BinCompressed instead.
    """

    # Note: the resource path below should NOT use os.path.join()
    ref = importlib_resources.files("islenska") / "resources" / BIN_COMPRESSED_FILE
    with importlib_resources.as_file(ref) as path:
        _FNAME = str(path)

    def __init__(self, fname: Optional[str] = None) -> None:
        """We use a memory map, provided by the mmap module, to
        directly map the compressed file into memory without
        having to read it into a byte buffer. This also allows
        the same memory map to be shared between processes.
        The file is the one packaged with islenska unless a path
        is given here or in the ISLENSKA_BIN_FILE environment variable."""
        if fname is None:
            fname = os.environ.get(BIN_FILE_ENV) or self._FNAME
        self._fname = fname
        with open(fname, "rb") as stream:
            self._b = mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ)
        # Check that the file version matches what we expect
        assert not self._b.closed, f"Could not open {fname}; file missing?"
        assert (
            self._b[0:16] == BIN_COMPRESSOR_VERSION
        ), f"Invalid signature in {fname}; file missing or version mismatch?"
        self._begin_greynir_utg = 0
        self._max_bin_id = 0
        (
            mappings_offset,
            forms_offset,
            lemmas_offset,
            templates_offset,
            meanings_offset,
            alphabet_offset,
            subcats_offset,
            ksnid_offset,
            self._begin_greynir_utg,
            self._max_bin_id,
            compact_offset,
        ) = struct.unpack("<IIIIIIIIIII", self._b[16:60])
        # A compact build (tools/binpack.py --compact) has a nonzero
        # compact section offset; its lookups need the compounder DAWGs
        self._compact_offset: int = compact_offset
        self._forms_offset: int = forms_offset
        self._mappings: bytes = self._b[mappings_offset:]
        self._lemmas: bytes = self._b[lemmas_offset:]
        self._templates: bytes = self._b[templates_offset:]
        self._meanings: bytes = self._b[meanings_offset:]
        self._ksnid_strings: bytes = self._b[ksnid_offset:]
        # Create partial unpacking functions for speed
        self._partial_UINT = functools.partial(UINT32.unpack_from, self._b)
        self._partial_mappings = functools.partial(UINT32.unpack_from, self._mappings)
        # Cache the trie root header
        self._forms_root_hdr = self._UINT(forms_offset)
        # The alphabet header occupies the next 16 bytes
        # Read the alphabet length
        alphabet_length = self._UINT(alphabet_offset)
        self._alphabet_bytes = bytes(self._b[alphabet_offset + 4 : alphabet_offset + 4 + alphabet_length])
        # Decode the subcategories ('fl') into a list of strings
        subcats_length = self._UINT(subcats_offset)
        subcats_bytes = bytes(self._b[subcats_offset + 4 : subcats_offset + 4 + subcats_length])
        self._subcats = [s.decode("latin-1") for s in subcats_bytes.split()]
        # Create a CFFI buffer object pointing to the memory map
        self._mmap_buffer: bytes = ffi.from_buffer(self._b)
        self._mmap_ptr: int = ffi.cast("uint8_t*", self._mmap_buffer)

    def _UINT(self, offset: int) -> int:
        """Return the 32-bit UINT at the indicated offset
        in the memory-mapped buffer"""
        return self._partial_UINT(offset)[0]

    def close(self) -> None:
        """Close the memory map"""
        if cast(Union[mmap.mmap, None], self._b) is None:
            # Already closed
            return
        self._mappings = cast(bytes, None)
        self._lemmas = cast(bytes, None)
        self._meanings = cast(bytes, None)
        self._ksnid_strings = cast(bytes, None)
        self._templates = cast(bytes, None)
        self._alphabet_bytes = bytes()
        self._mmap_buffer = cast(bytes, None)
        self._mmap_ptr = 0
        if not self._b.closed:
            self._b.close()
        self._b = cast(mmap.mmap, None)

    @property
    def begin_greynir_utg(self):
        """Return the lowest utg number of Greynir additions"""
        return self._begin_greynir_utg

    @property
    def is_compact(self) -> bool:
        """True if this is a compact build, i.e. one that leaves the word
        forms of regenerable compounds to the compounder"""
        return self._compact_offset != 0

    @property
    def fname(self) -> str:
        """The path of the compressed file in use"""
        return self._fname

    def meaning(self, ix: int) -> Tuple[str, str]:
        """Find and decode a meaning (ofl, beyging) tuple,
        given its index"""
        (off,) = UINT32.unpack_from(self._meanings, ix * 4)
        assert self._b is not None
        b = bytes(self._b[off : off + 24])
        s = b.decode("latin-1").split(maxsplit=2)
        return s[0], s[1]  # ofl, beyging

    def ksnid_string(self, ix: int) -> str:
        """Find and decode a KRISTINsnid string"""
        off: int
        (off,) = UINT32.unpack_from(self._ksnid_strings, ix * 4)
        assert self._b is not None
        lw = self._b[off]  # Length byte
        return self._b[off + 1 : off + 1 + lw].decode("latin-1")

    def lemma(self, bin_id: int) -> Tuple[str, str]:
        """Find and decode a lemma (stofn, subcat) tuple, given its bin_id"""
        off: int
        (off,) = UINT32.unpack_from(self._lemmas, bin_id * 4)
        assert off != 0  # Unknown BÍN id
        bits = self._UINT(off) & 0x7FFFFFFF
        # Subcategory (fl) index
        cix = bits & (2**SUBCAT_BITS - 1)
        p = off + 4
        assert self._b is not None
        lw = self._b[p]  # Length byte
        p += 1
        b = bytes(self._b[p : p + lw])
        return b.decode("latin-1"), self._subcats[cix]  # stofn, fl

    # Abstract methods that must be overridden in BinCompressed
    # These are called by methods in this base class but implemented in C++

    def contains(self, word: str) -> bool:
        """Check if word exists in dictionary - must be implemented in subclass"""
        raise NotImplementedError(
            "BinCompressedPure.contains() must be overridden in BinCompressed"
        )

    __contains__ = contains

    def lookup(
        self,
        word: str,
        cat: Optional[str] = None,
        lemma: Optional[str] = None,
        utg: Optional[int] = None,
        inflection_filter: Optional[InflectionFilter] = None,
    ) -> List[BinEntryTuple]:
        """Lookup word in dictionary - must be implemented in subclass"""
        raise NotImplementedError(
            "BinCompressedPure.lookup() must be overridden in BinCompressed"
        )

    def lookup_ksnid(
        self,
        word: str,
        cat: Optional[str] = None,
        lemma: Optional[str] = None,
        utg: Optional[int] = None,
        inflection_filter: Optional[InflectionFilter] = None,
    ) -> List[Ksnid]:
        """Lookup word and return Ksnid entries - must be implemented in subclass"""
        raise NotImplementedError(
            "BinCompressedPure.lookup_ksnid() must be overridden in BinCompressed"
        )

    def lemma_forms(self, bin_id: int) -> List[str]:
        """Get all word forms for a lemma - must be implemented in subclass"""
        raise NotImplementedError(
            "BinCompressedPure.lemma_forms() must be overridden in BinCompressed"
        )

    def lookup_id(self, bin_id: int) -> List[Ksnid]:
        """Get all Ksnid entries for a BÍN ID - must be implemented in subclass"""
        raise NotImplementedError(
            "BinCompressedPure.lookup_id() must be overridden in BinCompressed"
        )

    def _raw_lookup(self, word: str) -> List[Tuple[int, int, int]]:
        """Return a list of lemma/meaning/ksnid tuples for the word, or
        an empty list if it is not found - must be implemented in subclass"""
        raise NotImplementedError(
            "BinCompressedPure._raw_lookup() must be overridden in BinCompressed"
        )

    def lookup_case(
        self,
        word: str,
        case: str,
        *,
        singular: bool = False,
        indefinite: bool = False,
        all_forms: bool = False,
        cat: Optional[str] = None,
        lemma: Optional[str] = None,
        utg: Optional[int] = None,
        inflection_filter: Optional[InflectionFilter] = None,
    ) -> Set[BinEntryTuple]:
        """Returns a set of entries, in the requested case, derived
        from the lemmas of the given word form, optionally constrained
        by word category and by the other arguments given. The
        inflection_filter argument, if present, should be a function that
        filters on the beyging field of each candidate BÍN entry.
        The word form is case-sensitive."""

        # Note that singular=True means that we force the result to be
        # singular even if the original word given is plural.
        # singular=False does not force the result to be plural; it
        # simply means that no forcing to singular occurs.
        # The same applies to indefinite=True and False, mutatis mutandis.
        # However, if all_forms=True, both singular and plural, as well as
        # definite and indefinite forms, are always returned.

        result: Set[BinEntryTuple] = set()
        # Category set
        if cat is None:
            cats = None
        elif cat == "no":
            # Allow a cat of "no" to mean a noun of any gender
            cats = ALL_GENDERS
        else:
            cats = frozenset([cat])
        wanted_beyging = ""

        def simplify_beyging(beyging: str) -> str:
            """Removes case-related information from a beyging string"""
            # Note that we also remove '2' and '3' in cases like
            # 'ÞGF2' and 'EF2', where alternate declination forms are
            # being specified.
            for s in ("NF", "ÞF", "ÞGF", "EF", "2", "3"):
                beyging = beyging.replace(s, "")
            if singular or all_forms:
                for s in ("ET", "FT"):
                    beyging = beyging.replace(s, "")
            if indefinite or all_forms:
                beyging = beyging.replace("gr", "")
                # For adjectives, we neutralize weak and strong
                # declension ('VB', 'SB'), but keep the degree (F, M, E)
                beyging = beyging.replace("EVB", "ESB").replace("FVB", "FSB")
            return beyging

        def beyging_func(beyging: str) -> bool:
            """This function is passed to self.lookup() as a filter
            on the beyging field"""
            if case not in beyging:
                # We get all BIN entries having the word form we ask
                # for from self.lookup(), so we need to be careful to
                # filter again on the case
                return False
            if not all_forms:
                if singular and ("ET" not in beyging):
                    # Only return singular forms
                    return False
                if indefinite and any(b in beyging for b in ("gr", "FVB", "EVB")):
                    # For indefinite forms, we don't want the attached definite
                    # article ('gr') or weak declensions of adjectives
                    return False
            if inflection_filter is not None and not inflection_filter(beyging):
                # The user-defined filter fails: return False
                return False
            # Apply our own filter, making sure we have effectively
            # the same beyging string as the word form we're coming
            # from, except for the case
            return simplify_beyging(beyging) == wanted_beyging

        for bin_id, meaning_index, _ in self._raw_lookup(word):
            if utg is not None and utg != bin_id:
                # Not the utg we're looking for
                continue
            # Check the category filter, if present
            ofl, beyging = self.meaning(meaning_index)
            if cats is not None:
                if ofl not in cats:
                    # Not the category we're looking for
                    continue
            stofn, _ = self.lemma(bin_id)
            if lemma is not None and lemma != stofn:
                # Not the lemma we're looking for
                continue
            # Go through the variants of this
            # lemma, for the requested case
            wanted_beyging = simplify_beyging(beyging)
            for c in self.lemma_forms(bin_id):
                # Make sure we only include each result once.
                # Also note that we need to check again for the word
                # category constraint because different inflection
                # forms may be identical to forms of other lemmas
                # and categories.
                result.update(
                    m
                    for m in self.lookup(
                        c,
                        cat=ofl,
                        lemma=stofn,
                        utg=bin_id,
                        inflection_filter=beyging_func,
                    )
                )
        return result

    def lookup_variants(
        self,
        word: str,
        cat: str,
        to_inflection: Union[str, Iterable[str]],
        lemma: Optional[str] = None,
        utg: Optional[int] = None,
        inflection_filter: Optional[InflectionFilter] = None,
    ) -> List[Ksnid]:
        """Returns a list of BÍN Ksnid instances for word forms
        where the beyging substring(s) given have been substituted for
        the original string(s) in the same grammatical feature(s).
        The list can be optionally constrained to a particular lemma and
        utg number."""

        cat = cat.casefold()
        to_inflection = mark_to_set(to_inflection)
        not_definite = "nogr" in to_inflection
        if not_definite:
            to_inflection.remove("nogr")

        # Category set
        cats: FrozenSet[str]
        if cat == "no":
            # Allow a cat of "no" to mean a noun of any gender
            cats = ALL_GENDERS
        else:
            cats = frozenset([cat])
        # Keep track of Ksnid instances we find,
        # along with their inflection description
        # (for sorting at the end)
        results: List[Tuple[Ksnid, Set[str]]] = []
        # Inflection specifiers for input
        b_set: Set[str] = set()
        for bin_id, meaning_index, _ in self._raw_lookup(word):
            if utg is not None and bin_id != utg:
                # Fails the utg filter
                continue
            ofl, beyging = self.meaning(meaning_index)
            if ofl not in cats:
                # Fails the word category constraint
                continue
            stofn, fl = self.lemma(bin_id)
            if lemma is not None and stofn != lemma:
                # Fails the lemma filter
                continue
            if inflection_filter is not None and not inflection_filter(beyging):
                # The user-defined filter fails
                continue
            b_set.update(mark_to_set(beyging))
            for form in self.lemma_forms(bin_id):
                for form_id, mix, kix in self._raw_lookup(form):
                    if form_id != bin_id:
                        continue
                    # Found a word form of the same lemma
                    _, this_beyging = self.meaning(mix)
                    if inflection_filter is not None and not inflection_filter(this_beyging):
                        # The user-defined filter fails
                        continue
                    tb_set = mark_to_set(this_beyging)
                    if not_definite and "gr" in tb_set:
                        # Asked for no definite form but this form is definite
                        continue
                    if tb_set.issuperset(to_inflection):
                        # Found a word form with the target inflections
                        ksnid_string = self.ksnid_string(kix)
                        ks = Ksnid.from_parameters(
                            stofn,
                            bin_id,
                            ofl,
                            fl,
                            form,
                            this_beyging,
                            ksnid_string,
                        )
                        if all(ks != t[0] for t in results):
                            # This is a new inflection,
                            # add it to our results
                            results.append((ks, tb_set))

        # Inflections with the least difference
        # from the input inflection closer to the front
        results.sort(key=lambda t: len(t[1].symmetric_difference(b_set)))

        # Return Ksnid entries
        return [t[0] for t in results]

    def raw_nominative(self, word: str) -> Set[BinEntryTuple]:
        """Returns a set of all nominative forms of the lemmas of the given word form.
        Note that the word form is case-sensitive."""
        result: Set[BinEntryTuple] = set()
        for lemma_index, _, _ in self._raw_lookup(word):
            for c in self.lemma_forms(lemma_index):
                # Make sure we only include each result once
                result.update(m for m in self.lookup(c) if "NF" in m[5])
        return result

    def nominative(self, word: str, **options: Any) -> Set[BinEntryTuple]:
        """Returns a set of all nominative forms of the lemmas of the given word form,
        subject to the constraints in **options.
        Note that the word form is case-sensitive."""
        return self.lookup_case(word, "NF", **options)

    def accusative(self, word: str, **options: Any) -> Set[BinEntryTuple]:
        """Returns a set of all accusative forms of the lemmas of the given word form,
        subject to the given constraints on the beyging field.
        Note that the word form is case-sensitive."""
        return self.lookup_case(word, "ÞF", **options)

    def dative(self, word: str, **options: Any) -> Set[BinEntryTuple]:
        """Returns a set of all dative forms of the lemmas of the given word form,
        subject to the given constraints on the beyging field.
        Note that the word form is case-sensitive."""
        return self.lookup_case(word, "ÞGF", **options)

    def genitive(self, word: str, **options: Any) -> Set[BinEntryTuple]:
        """Returns a set of all genitive forms of the lemmas of the given word form,
        subject to the given constraints on the beyging field.
        Note that the word form is case-sensitive."""
        return self.lookup_case(word, "EF", **options)


class BinCompressed(BinCompressedPure):
    """Hybrid Python/C++ wrapper for the compressed binary dictionary.

    Inherits from BinCompressedPure and overrides methods with C++ implementations
    (libbin) for improved performance. Methods not yet migrated to C++ are
    inherited from the base class.

    The base class creates the memory-mapped file, which is shared with the C++
    implementation to avoid duplication. A compact build additionally needs the
    compounder DAWGs, which are loaded via Wordbase and handed to libbin.
    """

    def __init__(self, fname: Optional[str] = None) -> None:
        """Initialize base class and add C++ handle for optimized methods."""
        # Initialize base class (creates mmap, sets up all Python infrastructure)
        super().__init__(fname)
        self._cpp_handle: Any = None
        # Avoid a circular import at module load time
        from .dawgdictionary import Wordbase

        # The DAWGs are needed for compact builds; loading them is cheap
        # (memory maps), so always provide them
        self._dawgs = (Wordbase.dawg(), Wordbase.dawg_prefixes(), Wordbase.dawg_suffixes())
        errbuf = ffi.new("char[256]")
        self._cpp_handle = bin_cffi.bin_open(
            self._mmap_ptr,
            len(self._b),
            self._dawgs[0].handle,
            self._dawgs[1].handle,
            self._dawgs[2].handle,
            errbuf,
            256,
        )
        if not self._cpp_handle:
            raise RuntimeError(
                "Failed to open compressed dictionary: "
                + ffi.string(errbuf).decode("latin-1")
            )

    def __del__(self) -> None:
        """Clean up C++ resources."""
        if self._cpp_handle:
            bin_cffi.bin_close(self._cpp_handle)
            self._cpp_handle = None

    def close(self) -> None:
        """Close the C++ handle and the memory map"""
        if self._cpp_handle:
            bin_cffi.bin_close(self._cpp_handle)
            self._cpp_handle = None
        super().close()

    @staticmethod
    def _latin1(word: str) -> Optional[bytes]:
        """Encode a word as Latin-1, or return None if that isn't possible
        (in which case the word cannot be in the dictionary)"""
        try:
            return word.encode("latin-1")
        except UnicodeEncodeError:
            return None

    @staticmethod
    def _entries(result: Any) -> List[Tuple[str, int, str, str, str, str, str]]:
        """Convert a BinResult* to a list of 7-tuples, freeing the result"""
        try:
            entries: List[Tuple[str, int, str, str, str, str, str]] = []
            for i in range(result.count):
                e = result.entries[i]
                entries.append(
                    (
                        ffi.string(e.ord).decode("latin-1"),
                        e.bin_id,
                        ffi.string(e.ofl).decode("latin-1"),
                        ffi.string(e.hluti).decode("latin-1"),
                        ffi.string(e.bmynd).decode("latin-1"),
                        ffi.string(e.mark).decode("latin-1"),
                        ffi.string(e.ksnid).decode("latin-1"),
                    )
                )
            return entries
        finally:
            bin_cffi.bin_result_free(result)

    # Override methods with C++ implementations
    def contains(self, word: str) -> bool:
        """Check if word exists in dictionary (C++ implementation).
        In a compact build, this includes the dropped compounds that
        the compounder restores."""
        word_bytes = self._latin1(word)
        if word_bytes is None:
            return False
        return bool(bin_cffi.bin_contains(self._cpp_handle, word_bytes))

    __contains__ = contains

    def _raw_lookup(self, word: str) -> List[Tuple[int, int, int]]:
        """Return a list of lemma/meaning/ksnid tuples for the word, or
        an empty list if it is not found (C++ implementation, including
        compact restoration)"""
        word_bytes = self._latin1(word)
        if word_bytes is None:
            return []
        raw = bin_cffi.bin_lookup_raw(self._cpp_handle, word_bytes)
        if not raw:
            return []
        try:
            return [
                (raw.entries[i].bin_id, raw.entries[i].meaning_index, raw.entries[i].ksnid_index)
                for i in range(raw.count)
            ]
        finally:
            bin_cffi.bin_raw_result_free(raw)

    def _lookup_entries(
        self,
        word: str,
        cat: Optional[str],
        lemma: Optional[str],
        utg: Optional[int],
    ) -> List[Tuple[str, int, str, str, str, str, str]]:
        """Common implementation of lookup() and lookup_ksnid()"""
        word_bytes = self._latin1(word)
        if word_bytes is None:
            return []
        cat_bytes = cat.encode("latin-1") if cat else ffi.NULL
        lemma_bytes = self._latin1(lemma) if lemma else ffi.NULL
        if lemma_bytes is None:
            # A lemma filter that is not Latin-1 cannot match anything
            return []
        result = bin_cffi.bin_lookup(
            self._cpp_handle, word_bytes, cat_bytes, lemma_bytes, utg or 0
        )
        if not result:
            return []
        return self._entries(result)

    def lookup(
        self,
        word: str,
        cat: Optional[str] = None,
        lemma: Optional[str] = None,
        utg: Optional[int] = None,
        inflection_filter: Optional[InflectionFilter] = None,
    ) -> List[BinEntryTuple]:
        """Lookup word in dictionary (C++ implementation).
        The C++ implementation handles the cat, lemma, and utg filters;
        the inflection_filter, if any, is applied here."""
        return [
            (ord_, bin_id, ofl, hluti, bmynd, mark)
            for ord_, bin_id, ofl, hluti, bmynd, mark, _ in self._lookup_entries(
                word, cat, lemma, utg
            )
            if inflection_filter is None or inflection_filter(mark)
        ]

    def lookup_ksnid(
        self,
        word: str,
        cat: Optional[str] = None,
        lemma: Optional[str] = None,
        utg: Optional[int] = None,
        inflection_filter: Optional[InflectionFilter] = None,
    ) -> List[Ksnid]:
        """Lookup word and return Ksnid entries (C++ implementation).
        The C++ implementation handles the cat, lemma, and utg filters;
        the inflection_filter, if any, is applied here."""
        return [
            Ksnid.from_parameters(ord_, bin_id, ofl, hluti, bmynd, mark, ksnid)
            for ord_, bin_id, ofl, hluti, bmynd, mark, ksnid in self._lookup_entries(
                word, cat, lemma, utg
            )
            if inflection_filter is None or inflection_filter(mark)
        ]

    def lemma_forms(self, bin_id: int) -> List[str]:
        """Get all word forms for a lemma (C++ implementation).
        Returns all inflected forms of the lemma identified by bin_id,
        decompressed from the templates section, the lemma itself last."""
        if bin_id < 0:
            return []
        strings = bin_cffi.bin_lemma_forms(self._cpp_handle, bin_id)
        if not strings:
            return []
        try:
            return [
                ffi.string(strings.items[i]).decode("latin-1")
                for i in range(strings.count)
            ]
        finally:
            bin_cffi.bin_strings_free(strings)

    def lookup_id(self, bin_id: int) -> List[Ksnid]:
        """Get all Ksnid entries for a given BÍN ID (C++ implementation).
        Returns all word forms of the lemma with their full Ksnid information."""
        if bin_id < 0:
            return []
        result = bin_cffi.bin_lookup_id(self._cpp_handle, bin_id)
        if not result:
            return []
        return [
            Ksnid.from_parameters(ord_, bin_id_, ofl, hluti, bmynd, mark, ksnid)
            for ord_, bin_id_, ofl, hluti, bmynd, mark, ksnid in self._entries(result)
        ]

    def compound_candidates(self, word: str) -> List[List[str]]:
        """The legal compound splits of the word, in the ranking order of
        the compounder (longest last part first, then fewest parts),
        including the single-part split if the whole word is a legal suffix"""
        word_bytes = self._latin1(word)
        if word_bytes is None:
            return []
        splits = bin_cffi.bin_compound_candidates(self._cpp_handle, word_bytes)
        if not splits:
            return []
        try:
            from .dawgdictionary import splits_to_list

            return splits_to_list(splits)
        finally:
            bin_cffi.bin_splits_free(splits)

    def compound_split(self, word: str) -> List[str]:
        """The split that the compounder settles on for the word: the
        first legal candidate (longest last part, fewest parts) whose last
        part is not a defective noun, or the first candidate if all are.
        Empty if the word does not split."""
        word_bytes = self._latin1(word)
        if word_bytes is None:
            return []
        splits = bin_cffi.bin_compound_split(self._cpp_handle, word_bytes)
        if not splits:
            return []
        try:
            from .dawgdictionary import splits_to_list

            return splits_to_list(splits)[0]
        finally:
            bin_cffi.bin_splits_free(splits)

    # Other methods (lookup_variants, lookup_case,
    # raw_nominative, nominative, accusative, dative, genitive, etc.)
    # are inherited from BinCompressedPure and will be gradually migrated to C++
    # by adding overrides here as implementations become available.
