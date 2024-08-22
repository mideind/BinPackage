#!/usr/bin/env python
"""

    BinPackage

    Low-level access module for the compressed BÍN dictionary

    Copyright © 2023 Miðeind ehf.
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
    AnyStr,
    FrozenSet,
    Iterable,
    Set,
    Tuple,
    List,
    Optional,
    Union,
    cast,
)

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

from .basics import (
    BIN_ID_BITS,
    BIN_ID_MASK,
    COMMON_KIX_0,
    COMMON_KIX_1,
    InflectionFilter,
    BinEntryTuple,
    Ksnid,
    ALL_GENDERS,
    mark_to_set,
    BIN_COMPRESSOR_VERSION,
    BIN_COMPRESSED_FILE,
    UINT32,
    SUBCAT_BITS,
    KSNID_BITS,
    KSNID_MASK,
    MEANING_MASK,
)


class BinCompressed:
    """A wrapper for the compressed binary dictionary,
    allowing read-only lookups of word forms"""

    # Note: the resource path below should NOT use os.path.join()
    ref = importlib_resources.files("islenska") / "resources" / BIN_COMPRESSED_FILE
    with importlib_resources.as_file(ref) as path:
        _FNAME = str(path)

    def __init__(self) -> None:
        """We use a memory map, provided by the mmap module, to
        directly map the compressed file into memory without
        having to read it into a byte buffer. This also allows
        the same memory map to be shared between processes."""
        with open(self._FNAME, "rb") as stream:
            self._b = mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ)
        # Check that the file version matches what we expect
        assert not self._b.closed, "Could not open ord.compressed; file missing?"
        assert (
            self._b[0:16] == BIN_COMPRESSOR_VERSION
        ), "Invalid signature in ord.compressed; file missing or version mismatch?"
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
        ) = struct.unpack("<IIIIIIIIII", self._b[16:56])
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

    def lemma_forms(self, bin_id: int) -> List[bytes]:
        """Return all word forms that are associated with the lemma
        whose bin_id is given"""

        def read_set(p: int, base: bytes) -> List[bytes]:
            """Decompress a set of strings compressed by compress_set()"""
            b = self._templates
            c: List[bytes] = []
            last_w = base
            lw = len(last_w)
            while True:
                # How many letters should we cut off the end of the
                # last word before appending the divergent part?
                cut = b[p]
                p += 1
                if cut == 0x00:
                    # Done
                    break
                if cut & 0x80:
                    # Long form: the cut is in the lower 7 bits and the
                    # length is in the following byte
                    cut &= 0x7F
                    lw_new = b[p]
                    p += 1
                else:
                    # The cut is in the upper 4 bits, and (len - cut) in the lower 3
                    diff = (cut & 0x03) - (cut & 0x04)
                    cut >>= 3
                    lw_new = cut + diff
                # Calculate the number of common characters between
                # this word and the last one
                common = lw - cut
                lw = lw_new
                # Assemble this word and append it to our result
                w = last_w[0:common] + b[p : p + lw]
                p += lw
                c.append(w)
                last_w = w
                lw += common
            # Return the set as a list of byte strings
            return c

        # Sanity check on the BÍN id
        if not 0 <= bin_id <= self._max_bin_id:
            return []
        off: int
        (off,) = UINT32.unpack_from(self._lemmas, bin_id * 4)
        if off == 0:
            # No entry with this BÍN id
            return []
        bits = self._UINT(off)
        # Skip past the lemma itself
        assert self._b is not None
        p = off + 4
        lw = self._b[p]  # Length byte
        lemma = bytes(self._b[p + 1 : p + 1 + lw])
        if bits & 0x80000000 == 0:
            # No templates associated with this lemma
            return [lemma]
        lw += 1
        if lw & 3:
            lw += 4 - (lw & 3)
        p += lw
        # Return all inflection forms as well as the lemma itself
        result = read_set(self._UINT(p), base=lemma)
        result.append(lemma)
        return result

    def _mapping_cffi(self, word: Union[str, bytes]) -> Optional[int]:
        """Call the C++ mapping() function that has been wrapped using CFFI"""
        try:
            if isinstance(word, str):
                word = word.encode("latin-1")
            m: int = bin_cffi.mapping(self._mmap_ptr, word)
            return None if m == 0xFFFFFFFF else m
        except UnicodeEncodeError:
            # The word contains a non-latin-1 character:
            # it can't be in the trie
            return None

    def _raw_lookup(self, word: AnyStr) -> List[Tuple[int, int, int]]:
        """Return a list of lemma/meaning/ksnid tuples for the word, or
        an empty list if it is not found in the trie"""
        mapping = self._mapping_cffi(word)
        if mapping is None:
            # Word not found in trie: return an empty list of entries
            return []
        # Found the word in the trie; return potentially multiple entries
        # Fetch the mapping-to-lemma/meaning tuples
        result: List[Tuple[int, int, int]] = []
        bin_id = -1
        while True:
            (w0,) = self._partial_mappings(mapping * 4)
            mapping += 1
            if w0 & 0x60000000 == 0x60000000:
                # This is a single 32-bit packed entry
                meaning_index = (w0 >> BIN_ID_BITS) & 0xFF  # 8 bits for freq_ix
                bin_id = w0 & BIN_ID_MASK
                meaning_index -= 1
                ksnid_index = COMMON_KIX_1 if w0 & 0x10000000 else COMMON_KIX_0
            elif w0 & 0x60000000 == 0x40000000:
                # This is a single 32-bit entry with the same bin_id as the previous one
                assert bin_id != -1
                meaning_index = (w0 >> KSNID_BITS) & MEANING_MASK
                ksnid_index = w0 & KSNID_MASK
            else:
                # This meaning is stored in two 32-bit words
                assert w0 & 0x60000000 == 0
                bin_id = w0 & BIN_ID_MASK
                (w1,) = self._partial_mappings(mapping * 4)
                mapping += 1
                meaning_index = (w1 >> KSNID_BITS) & MEANING_MASK
                ksnid_index = w1 & KSNID_MASK
            result.append((bin_id, meaning_index, ksnid_index))
            if w0 & 0x80000000:
                # Last mapping indicator: we're done
                break
        return result

    def contains(self, word: str) -> bool:
        """Returns True if the trie contains the given word form"""
        return self._mapping_cffi(word) is not None

    __contains__ = contains

    def lookup(
        self,
        word: str,
        cat: Optional[str] = None,
        lemma: Optional[str] = None,
        utg: Optional[int] = None,
        inflection_filter: Optional[InflectionFilter] = None,
    ) -> List[BinEntryTuple]:
        """Returns a list of BÍN entries for the given word form,
        eventually constrained to the requested word category,
        lemma, utg number and/or the given beyging_func filter function,
        which is called with the beyging field as a parameter."""

        # Category set
        if cat is None:
            cats = None
        elif cat == "no":
            # Allow a cat of "no" to mean a noun of any gender
            cats = ALL_GENDERS
        else:
            cats = frozenset([cat])
        result: List[BinEntryTuple] = []
        for bin_id, meaning_index, _ in self._raw_lookup(word):
            if utg is not None and bin_id != utg:
                # Fails the utg filter
                continue
            ofl, beyging = self.meaning(meaning_index)
            if cats is not None and ofl not in cats:
                # Fails the word category constraint
                continue
            stofn, fl = self.lemma(bin_id)
            if lemma is not None and stofn != lemma:
                # Fails the lemma filter
                continue
            if inflection_filter is not None and not inflection_filter(beyging):
                # Fails the beyging_func filter
                continue
            # stofn, utg, ofl, fl, ordmynd, beyging
            result.append((stofn, bin_id, ofl, fl, word, beyging))
        return result

    def lookup_ksnid(
        self,
        word: str,
        cat: Optional[str] = None,
        lemma: Optional[str] = None,
        utg: Optional[int] = None,
        inflection_filter: Optional[InflectionFilter] = None,
    ) -> List[Ksnid]:
        """Returns a list of BÍN entries for the given word form,
        eventually constrained to the requested word category,
        lemma, utg number and/or the given beyging_func filter function,
        which is called with the beyging field as a parameter."""

        # Category set
        if cat is None:
            cats = None
        elif cat == "no":
            # Allow a cat of "no" to mean a noun of any gender
            cats = ALL_GENDERS
        else:
            cats = frozenset([cat])
        result: List[Ksnid] = []
        for bin_id, meaning_index, ksnid_index in self._raw_lookup(word):
            if utg is not None and bin_id != utg:
                # Fails the utg filter
                continue
            ofl, beyging = self.meaning(meaning_index)
            if cats is not None and ofl not in cats:
                # Fails the word category constraint
                continue
            stofn, fl = self.lemma(bin_id)
            if lemma is not None and stofn != lemma:
                # Fails the lemma filter
                continue
            if inflection_filter is not None and not inflection_filter(beyging):
                # Fails the beyging_func filter
                continue
            ksnid_string = self.ksnid_string(ksnid_index)
            result.append(
                Ksnid.from_parameters(
                    stofn,
                    bin_id,
                    ofl,
                    fl,
                    word,
                    beyging,
                    ksnid_string,
                )
            )
        return result

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
            for c_latin in self.lemma_forms(bin_id):
                # TODO: Encoding and decoding back and forth is not terribly efficient
                c = c_latin.decode("latin-1")
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

    def lookup_id(self, bin_id: int) -> List[Ksnid]:
        """Given a BÍN id number, return a set of matching Ksnid entries"""
        result: Set[Ksnid] = set()
        forms = self.lemma_forms(bin_id)
        if forms:
            stofn, fl = self.lemma(bin_id)
            for form_latin in forms:
                for form_id, mix, kix in self._raw_lookup(form_latin):
                    if form_id != bin_id:
                        continue
                    # Found a word form of the same lemma
                    ofl, beyging = self.meaning(mix)
                    ksnid_string = self.ksnid_string(kix)
                    result.add(
                        Ksnid.from_parameters(
                            stofn,
                            bin_id,
                            ofl,
                            fl,
                            form_latin.decode("latin-1"),
                            beyging,
                            ksnid_string,
                        )
                    )
        return list(result)

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
            for form_latin in self.lemma_forms(bin_id):
                for form_id, mix, kix in self._raw_lookup(form_latin):
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
                            form_latin.decode("latin-1"),
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
            for c_latin in self.lemma_forms(lemma_index):
                c = c_latin.decode("latin-1")
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
