#!/usr/bin/env python
"""

    BinPackage

    Low-level access module for the compressed BÍN dictionary

    Copyright (C) 2021 Miðeind ehf.
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
    Set,
    Tuple,
    List,
    Optional,
    Union,
    cast,
)

import struct
import re
import functools
import mmap
import pkg_resources

# Import the CFFI wrapper for the bin.cpp C++ module (see also build_bin.py)
# pylint: disable=no-name-in-module
from ._bin import lib as lib_unknown, ffi as ffi_unknown  # type: ignore

# Go through shenanigans to satisfy Pylance/Mypy
bin_cffi = cast(Any, lib_unknown)
ffi = cast(Any, ffi_unknown)

from .basics import (
    BeygingFilter,
    MeaningTuple,
    Ksnid,
    ALL_GENDERS,
    ALL_BIN_GENDERS,
    ALL_BIN_CASES,
    ALL_BIN_NUMBERS,
    ALL_BIN_PERSONS,
    ALL_BIN_DEGREES,
    ALL_BIN_TENSES,
    ALL_BIN_MOODS,
    ALL_BIN_VOICES,
    BIN_COMPRESSOR_VERSION,
    BIN_COMPRESSED_FILE,
    LEMMA_MAX,
    MEANING_MAX,
    MEANING_BITS,
    SUBCAT_BITS,
    UINT32,
    COMMON_KIX_0,
    COMMON_KIX_1,
)


class BinCompressed:

    """ A wrapper for the compressed binary dictionary,
        allowing read-only lookups of word forms """

    # Note: the resource path below should NOT use os.path.join()
    _FNAME = pkg_resources.resource_filename(
        __name__, "resources/" + BIN_COMPRESSED_FILE
    )

    def __init__(self) -> None:
        """ We use a memory map, provided by the mmap module, to
            directly map the compressed file into memory without
            having to read it into a byte buffer. This also allows
            the same memory map to be shared between processes. """
        with open(self._FNAME, "rb") as stream:
            self._b = mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ)
        # Check that the file version matches what we expect
        assert (
            self._b[0:16] == BIN_COMPRESSOR_VERSION
        ), "Invalid signature in ord.compressed (git-lfs might be missing)"
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
        ) = struct.unpack("<IIIIIIIII", self._b[16:52])
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
        self._alphabet_bytes = bytes(
            self._b[alphabet_offset + 4 : alphabet_offset + 4 + alphabet_length]
        )
        self._alphabet: Set[str] = set()
        # Decode the subcategories ('fl') into a list of strings
        subcats_length = self._UINT(subcats_offset)
        subcats_bytes = bytes(
            self._b[subcats_offset + 4 : subcats_offset + 4 + subcats_length]
        )
        self._subcats = [s.decode("latin-1") for s in subcats_bytes.split()]
        # Create a CFFI buffer object pointing to the memory map
        self._mmap_buffer: bytes = ffi.from_buffer(self._b)
        self._mmap_ptr: int = ffi.cast("uint8_t*", self._mmap_buffer)

    def _UINT(self, offset: int) -> int:
        """ Return the 32-bit UINT at the indicated offset
            in the memory-mapped buffer """
        return self._partial_UINT(offset)[0]

    def close(self) -> None:
        """ Close the memory map """
        if self._b is not None:
            self._mappings = cast(bytes, None)
            self._lemmas = cast(bytes, None)
            self._meanings = cast(bytes, None)
            self._ksnid_strings = cast(bytes, None)
            self._templates = cast(bytes, None)
            self._alphabet = set()
            self._alphabet_bytes = bytes()
            self._mmap_buffer = cast(bytes, None)
            self._mmap_ptr = 0
            self._b.close()
            self._b = cast(mmap.mmap, None)

    @property
    def begin_greynir_utg(self):
        """ Return the lowest utg number of Greynir additions """
        return self._begin_greynir_utg

    def meaning(self, ix: int) -> Tuple[str, str]:
        """ Find and decode a meaning (ofl, beyging) tuple,
            given its index """
        (off,) = UINT32.unpack_from(self._meanings, ix * 4)
        assert self._b is not None
        b = bytes(self._b[off : off + 24])
        s = b.decode("latin-1").split(maxsplit=2)
        return s[0], s[1]  # ofl, beyging

    def ksnid_string(self, ix: int) -> str:
        """ Find and decode a KRISTINsnid string """
        (off,) = UINT32.unpack_from(self._ksnid_strings, ix * 4)
        assert self._b is not None
        lw = self._b[off]  # Length byte
        return self._b[off + 1 : off + 1 + lw].decode("latin-1")

    def lemma(self, ix: int) -> Tuple[str, int, str]:
        """ Find and decode a lemma (stofn, utg, subcat) tuple, given its index """
        (off,) = UINT32.unpack_from(self._lemmas, ix * 4)
        bits = self._UINT(off) & 0x7FFFFFFF
        utg = bits >> SUBCAT_BITS
        # Subcategory (fl) index
        cix = bits & (2 ** SUBCAT_BITS - 1)
        p = off + 4
        assert self._b is not None
        lw = self._b[p]  # Length byte
        p += 1
        b = bytes(self._b[p : p + lw])
        return b.decode("latin-1"), utg, self._subcats[cix]  # stofn, utg, fl

    def lemma_forms(self, lemma_ix: int) -> List[bytes]:
        """ Return all word forms having the given case, that are
            associated with the lemma whose index is in ix """

        def read_set(p: int, base: bytes) -> List[bytes]:
            """ Decompress a set of strings compressed by compress_set() """
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

        (off,) = UINT32.unpack_from(self._lemmas, lemma_ix * 4)
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
        """ Call the C++ mapping() function that has been wrapped using CFFI """
        try:
            if isinstance(word, str):
                word = word.encode("latin-1")
            assert isinstance(word, bytes)
            m: int = bin_cffi.mapping(self._mmap_ptr, word)
            return None if m == 0xFFFFFFFF else m
        except UnicodeEncodeError:
            # The word contains a non-latin-1 character:
            # it can't be in the trie
            return None

    def _raw_lookup(self, word: AnyStr) -> List[Tuple[int, int, int]]:
        """ Return a list of lemma/meaning/ksnid tuples for the word, or
            an empty list if it is not found in the trie """
        mapping = self._mapping_cffi(word)
        if mapping is None:
            # Word not found in trie: return an empty list of meanings
            return []
        # Found the word in the trie; return potentially multiple meanings
        # Fetch the mapping-to-lemma/meaning tuples
        result: List[Tuple[int, int, int]] = []
        lemma_mask = LEMMA_MAX - 1
        meaning_mask = MEANING_MAX - 1
        while True:
            (lemma_meaning,) = self._partial_mappings(mapping * 4)
            meaning_index = lemma_meaning & meaning_mask
            lemma_index = (lemma_meaning >> MEANING_BITS) & lemma_mask
            if lemma_meaning & 0x40000000:
                ksnid_index = COMMON_KIX_0
            elif lemma_meaning & 0x20000000:
                ksnid_index = COMMON_KIX_1
            else:
                mapping += 1
                (ksnid_index,) = self._partial_mappings(mapping * 4)
            result.append((lemma_index, meaning_index, ksnid_index))
            if lemma_meaning & 0x80000000:
                # Last mapping indicator: we're done
                break
            mapping += 1
        return result

    def contains(self, word: str) -> bool:
        """ Returns True if the trie contains the given word form"""
        return self._mapping_cffi(word) is not None

    __contains__ = contains

    def lookup(
        self,
        word: str,
        cat: Optional[str] = None,
        lemma: Optional[str] = None,
        utg: Optional[int] = None,
        beyging_filter: Optional[BeygingFilter] = None,
    ) -> List[MeaningTuple]:

        """ Returns a list of BÍN meanings for the given word form,
            eventually constrained to the requested word category,
            lemma, utg number and/or the given beyging_func filter function,
            which is called with the beyging field as a parameter. """

        # Category set
        if cat is None:
            cats = None
        elif cat == "no":
            # Allow a cat of "no" to mean a noun of any gender
            cats = ALL_GENDERS
        else:
            cats = frozenset([cat])
        result: List[MeaningTuple] = []
        for lemma_index, meaning_index, _ in self._raw_lookup(word):
            ofl, beyging = self.meaning(meaning_index)
            if cats is not None and ofl not in cats:
                # Fails the word category constraint
                continue
            stofn, wutg, fl = self.lemma(lemma_index)
            if lemma is not None and stofn != lemma:
                # Fails the lemma filter
                continue
            if utg is not None and wutg != utg:
                # Fails the utg filter
                continue
            if beyging_filter is not None and not beyging_filter(beyging):
                # Fails the beyging_func filter
                continue
            # stofn, utg, ofl, fl, ordmynd, beyging
            result.append((stofn, wutg, ofl, fl, word, beyging))
        return result

    def lookup_ksnid(
        self,
        word: str,
        cat: Optional[str] = None,
        lemma: Optional[str] = None,
        utg: Optional[int] = None,
        beyging_filter: Optional[BeygingFilter] = None,
    ) -> List[Ksnid]:

        """ Returns a list of BÍN meanings for the given word form,
            eventually constrained to the requested word category,
            lemma, utg number and/or the given beyging_func filter function,
            which is called with the beyging field as a parameter. """

        # Category set
        if cat is None:
            cats = None
        elif cat == "no":
            # Allow a cat of "no" to mean a noun of any gender
            cats = ALL_GENDERS
        else:
            cats = frozenset([cat])
        result: List[Ksnid] = []
        for lemma_index, meaning_index, ksnid_index in self._raw_lookup(word):
            ofl, beyging = self.meaning(meaning_index)
            if cats is not None and ofl not in cats:
                # Fails the word category constraint
                continue
            stofn, wutg, fl = self.lemma(lemma_index)
            if lemma is not None and stofn != lemma:
                # Fails the lemma filter
                continue
            if utg is not None and wutg != utg:
                # Fails the utg filter
                continue
            if beyging_filter is not None and not beyging_filter(beyging):
                # Fails the beyging_func filter
                continue
            ksnid_string = self.ksnid_string(ksnid_index)
            result.append(
                Ksnid.from_parameters(
                    stofn, wutg, ofl, fl, word, beyging, ksnid_string,
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
        beyging_filter: Optional[BeygingFilter] = None,
    ) -> Set[MeaningTuple]:

        """ Returns a set of meanings, in the requested case, derived
            from the lemmas of the given word form, optionally constrained
            by word category and by the other arguments given. The
            beyging_filter argument, if present, should be a function that
            filters on the beyging field of each candidate BÍN meaning.
            The word form is case-sensitive. """

        # Note that singular=True means that we force the result to be
        # singular even if the original word given is plural.
        # singular=False does not force the result to be plural; it
        # simply means that no forcing to singular occurs.
        # The same applies to indefinite=True and False, mutatis mutandis.
        # However, if all_forms=True, both singular and plural, as well as
        # definite and indefinite forms, are always returned.

        result: Set[MeaningTuple] = set()
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
            """ Removes case-related information from a beyging string """
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
            """ This function is passed to self.lookup() as a filter
                on the beyging field """
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
            if beyging_filter is not None and not beyging_filter(beyging):
                # The user-defined filter fails: return False
                return False
            # Apply our own filter, making sure we have effectively
            # the same beyging string as the word form we're coming
            # from, except for the case
            return simplify_beyging(beyging) == wanted_beyging

        for lemma_index, meaning_index, _ in self._raw_lookup(word):
            # Check the category filter, if present
            ofl, beyging = self.meaning(meaning_index)
            if cats is not None:
                if ofl not in cats:
                    # Not the category we're looking for
                    continue
            stofn, wutg, _ = self.lemma(lemma_index)
            if lemma is not None and lemma != stofn:
                # Not the lemma we're looking for
                continue
            if utg is not None and utg != wutg:
                # Not the utg we're looking for
                continue
            # Go through the variants of this
            # lemma, for the requested case
            wanted_beyging = simplify_beyging(beyging)
            for c_latin in self.lemma_forms(lemma_index):
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
                        c, cat=ofl, lemma=stofn, utg=wutg, beyging_filter=beyging_func,
                    )
                )
        return result

    def lookup_variants(
        self,
        word: str,
        cat: str,
        to_beyging: Union[str, Tuple[str, ...]],
        lemma: Optional[str] = None,
        utg: Optional[int] = None,
        beyging_filter: Optional[BeygingFilter] = None,
    ) -> Set[Ksnid]:

        """ Returns a list of BÍN meaning tuples for word forms
            where the beyging substring(s) given have been substituted for
            the original string(s) in the same grammatical feature(s).
            The list can be optionally constrained to a particular lemma and
            utg number. """

        if isinstance(to_beyging, str):
            to_beyging = (to_beyging,)

        def xform(t: str) -> str:
            """ Transform to_beyging strings to allow lower case and
                Greynir-style person variants """
            if t in {"gr", "nogr"}:
                # Don't uppercase the definite article variant
                return t
            if t in {"p1", "p2", "p3"}:
                # Allow Greynir-style person variants
                return t[1] + "P"
            return t.upper()

        to_beyging_list = [xform(t) for t in to_beyging]

        def make_target(b: str) -> str:
            """ Create a target beyging string by substituting the
                desired to_beyging in its proper place in the source """
            # Remove '2' or '3' at the end of the beyging string,
            # denoting alternative forms
            b = re.sub(r"(2|3)$", "", b)
            for t in to_beyging_list:
                if t in ALL_BIN_CASES:
                    b = re.sub(r"ÞGF|NF|ÞF|EF", t, b)
                elif t in ALL_BIN_NUMBERS:
                    b = re.sub(r"ET|FT", t, b)
                elif t == "gr":
                    # Add definite article indicator if not already present
                    if not b.endswith("gr"):
                        b += "gr"
                elif t == "nogr":
                    # Remove definite article indicator
                    b = b.replace("gr", "")
                elif t in ALL_BIN_GENDERS:
                    b = re.sub(r"KVK|KK|HK", t, b)
                elif t in ALL_BIN_PERSONS:
                    b = re.sub(r"1P|2P|3P", t, b)
                elif t in ALL_BIN_DEGREES:
                    b = re.sub(r"ESB|EVB|EST|FSB|FVB|FST|MST|VB|SB", t, b)
                elif t in ALL_BIN_TENSES:
                    b = re.sub(r"-ÞT|-NT", "-" + t, b)
                elif t in ALL_BIN_VOICES:
                    b = re.sub(r"GM|MM", t, b)
                elif t in ALL_BIN_MOODS:
                    if t == "LHNT":
                        # If the present participle is desired, there can be
                        # no other features present in the beyging string
                        return "LHNT"
                    if t == "BH":
                        # For the imperative mood, there is no tense
                        # and no person in the beyging string
                        b = re.sub(r"-NT|-ÞT|-1P|-2P|-3P", "", b)
                    # Note that we don't replace the LHÞT feature;
                    # it is too complex and different to be replaceable
                    # with anything else
                    b = re.sub(r"-NH|-FH|-VH|-BH", "-" + t, b)
                else:
                    raise ValueError(f"Unknown BÍN 'beyging' feature: '{t}'")
            return b

        # Category set
        cats: FrozenSet[str]
        if cat == "no":
            # Allow a cat of "no" to mean a noun of any gender
            cats = ALL_GENDERS
        else:
            cats = frozenset([cat])
        result: Set[Ksnid] = set()
        for lemma_index, meaning_index, _ in self._raw_lookup(word):
            ofl, beyging = self.meaning(meaning_index)
            if ofl not in cats:
                # Fails the word category constraint
                continue
            stofn, wutg, fl = self.lemma(lemma_index)
            if lemma is not None and stofn != lemma:
                # Fails the lemma filter
                continue
            if utg is not None and wutg != utg:
                # Fails the utg filter
                continue
            if beyging_filter is not None and not beyging_filter(beyging):
                # The user-defined filter fails
                continue
            target_beyging = make_target(beyging)
            if any(t not in target_beyging for t in to_beyging_list if t != "nogr"):
                # This target beyging string does not contain
                # our desired variants and is therefore not relevant
                continue
            for form_latin in self.lemma_forms(lemma_index):
                for lix, mix, kix in self._raw_lookup(form_latin):
                    if lix != lemma_index:
                        continue
                    # Found a word form of the same lemma
                    _, this_beyging = self.meaning(mix)
                    if this_beyging == target_beyging:
                        # Found a word form with the target beyging string
                        ksnid_string = self.ksnid_string(kix)
                        result.add(
                            Ksnid.from_parameters(
                                stofn,
                                wutg,
                                ofl,
                                fl,
                                form_latin.decode("latin-1"),
                                this_beyging,
                                ksnid_string,
                            )
                        )
        return result

    def raw_nominative(self, word: str) -> Set[MeaningTuple]:
        """ Returns a set of all nominative forms of the lemmas of the given word form.
            Note that the word form is case-sensitive. """
        result: Set[MeaningTuple] = set()
        for lemma_index, _, _ in self._raw_lookup(word):
            for c_latin in self.lemma_forms(lemma_index):
                c = c_latin.decode("latin-1")
                # Make sure we only include each result once
                result.update(m for m in self.lookup(c) if "NF" in m[5])
        return result

    def nominative(self, word: str, **options: Any) -> Set[MeaningTuple]:
        """ Returns a set of all nominative forms of the lemmas of the given word form,
            subject to the constraints in **options.
            Note that the word form is case-sensitive. """
        return self.lookup_case(word, "NF", **options)

    def accusative(self, word: str, **options: Any) -> Set[MeaningTuple]:
        """ Returns a set of all accusative forms of the lemmas of the given word form,
            subject to the given constraints on the beyging field.
            Note that the word form is case-sensitive. """
        return self.lookup_case(word, "ÞF", **options)

    def dative(self, word: str, **options: Any) -> Set[MeaningTuple]:
        """ Returns a set of all dative forms of the lemmas of the given word form,
            subject to the given constraints on the beyging field.
            Note that the word form is case-sensitive. """
        return self.lookup_case(word, "ÞGF", **options)

    def genitive(self, word: str, **options: Any) -> Set[MeaningTuple]:
        """ Returns a set of all genitive forms of the lemmas of the given word form,
            subject to the given constraints on the beyging field.
            Note that the word form is case-sensitive. """
        return self.lookup_case(word, "EF", **options)
