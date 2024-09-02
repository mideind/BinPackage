#!/usr/bin/env python
"""

    BinPackage

    BÍN packing/compression program

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

    This module compresses the BÍN dictionary from a ~400 MB uncompressed
    form into a compact binary representation. A radix trie data structure
    is used to store a mapping from word forms to integer indices.
    These indices are then used to look up lemmas, categories and meanings.

    The data format is a tradeoff between storage space and retrieval
    speed. The resulting binary image is designed to be read into memory as
    a BLOB (via mmap) and used directly to look up word forms. No auxiliary
    dictionaries or other data structures should be needed. The binary image
    is shared between running processes.

    binpack.py reads the files KRISTINsnid.csv (as fetched from BÍN), ord.auka.csv
    (additional vocabulary), ord.add.csv (generated from config/Vocab.conf
    by the program utils/vocab.py in the Greynir repository) and ord.suffixes.csv
    (containing inflection templates for word suffixes). Additionally,
    errata from the config/BinErrata.conf file are applied during
    the compression process. These additions and modifications are not a part of
    the original BÍN source data.

    The run-time counterpart of this module is bincompress.py.

    The compressed format is roughly as follows (see BinCompressor.write_binary()):

    The file starts with an identifying header and format version.

    It is followed by a list of 32-bit offsets of the various sections
    of the file.

    The sections are:

        mapping section: a mapping from word forms to meanings. Each word
        form has an index (cf. the forms section below), and this section maps
        from that index to a list of (lemma index, meaning index,
        ksnid string index) tuples.

        forms section: a compact radix trie that maps word forms from
        strings (compressed into a 127-bit alphabet) to indices
        into the mapping section.

        lemmas section: a mapping of lemma indices to
        (lemma string, bin_id number, category index) tuples. Also, if the lemma
        has grammatical variants (a list of suffixes that maps the lemma to
        each grammatical form), the index of the variant suffix template
        is stored here as well.

        variants section: a mapping of grammatical variant indexes to variant
        templates (specifications). A variant template describes
        how to obtain the grammatical variants of a given lemma string, i.e.
        a mapping of lemma -> { set of all word variants }

        alphabet section: a mapping of character indexes to characters.
        This is used to compress word form strings into 7 bits per character
        instead of 8 (using latin-1 encoding), keeping the high bit available
        to denote end-of-string.

        meanings section: a mapping of BÍN meaning indexes to BÍN mark
        strings (such as 'NFETgr').

        ksnid section: a mapping of ksnid string indices to ksnid strings.
        The ksnid strings contain additional data from the KRISTINsnid.csv
        file.

        subcats section: a mapping of domain (subcategory) indices to domain
        strings ('hluti' field in BÍN). Domains are strings such as
        'föð', 'móð', 'örn', etc.

    ************************************************************************

    LICENSE NOTICE:

    GreynirPackage embeds the 'Database of Modern Icelandic Inflection' /
    'Beygingarlýsing íslensks nútímamáls' (see https://bin.arnastofnun.is),
    abbreviated BÍN.

    The BÍN source data are publicly available under the CC-BY-4.0 license, as further
    detailed here in English: https://bin.arnastofnun.is/DMII/LTdata/conditions/
    and here in Icelandic: https://bin.arnastofnun.is/gogn/mimisbrunnur/.

    In accordance with the BÍN license terms, credit is hereby given as follows:

        Beygingarlýsing íslensks nútímamáls.
        Stofnun Árna Magnússonar í íslenskum fræðum.
        Höfundur og ritstjóri Kristín Bjarnadóttir.

    This module makes certain additions and modifications to the
    original BÍN source data during the generation of the compressed file,
    while attempting to mark such modifications so that full upwards compatibility
    with the original data is maintained. These additions and modifications are
    described in the comments above and in the code below.

"""

from typing import (
    Any,
    DefaultDict,
    Generic,
    Hashable,
    Set,
    Tuple,
    Dict,
    List,
    Optional,
    Iterable,
    IO,
    TypeVar,
)

import os
import io
import time
import struct
from collections import defaultdict

from islenska.basics import (
    Ksnid,
    BinEntryTuple,
    MarkOrder,
    BIN_COMPRESSOR_VERSION,
    BIN_COMPRESSED_FILE,
    UINT32,
    BIN_ID_BITS,
    BIN_ID_MAX,
    KSNID_BITS,
    KSNID_MAX,
    MEANING_MAX,
    SUBCAT_BITS,
    KSNID_COMMON_0,
    KSNID_COMMON_1,
    COMMON_KIX_0,
    COMMON_KIX_1,
)


MeaningTuple = Tuple[bytes, bytes]  # ordfl, beyging


# Bad word forms that have previously occurred in BÍN
BAD_BMYND = {
    "a",
    "num",
    "i",
    "ir",
    "in",
    "ina",
    "irnar",
    "irnir",
}

# We skip word forms that contain one or more of the following letters.
# These are mostly errors in BÍN, and/or foreign (Danish) words that
# are not relevant to Icelandic.
SUSPICIOUS_LETTERS = set("+@\\_åø")


_path, _ = os.path.split(os.path.realpath(__file__))
if _path.endswith(f"{os.sep}tools"):
    # Running from the tools directory (./tools)
    _path = os.path.join(_path, "..", "src", "islenska")
else:
    # Running from the base directory (.)
    _path = os.path.join(_path, "src", "islenska")

# If running under a CI environment (such as GitHub Actions),
# limit output to the essentials
quiet = os.environ.get("CI", "").strip() > ""


class _Node:

    """A Node within a Trie"""

    def __init__(self, fragment: bytes, value: Any) -> None:
        # The key fragment that leads into this node (and value)
        self.fragment = fragment
        self.value = value
        # List of outgoing nodes
        self.children: Optional[List[_Node]] = None

    def add(self, fragment: bytes, value: Any) -> Any:
        """Add the given remaining key fragment to this node"""
        if len(fragment) == 0:
            if self.value is not None:
                # This key already exists: return its value
                return self.value
            # This was previously an internal node without value;
            # turn it into a proper value node
            self.value = value
            return None

        if self.children is None:
            # Trivial case: add an only child
            self.children = [_Node(fragment, value)]
            return None

        # Check whether we need to take existing child nodes into account
        lo = mid = 0
        hi = len(self.children)
        ch = fragment[0]
        while hi > lo:
            mid = (lo + hi) // 2
            mid_ch = self.children[mid].fragment[0]
            if mid_ch < ch:
                lo = mid + 1
            elif mid_ch > ch:
                hi = mid
            else:
                break

        if hi == lo:
            # No common prefix with any child:
            # simply insert a new child into the sorted list
            # if lo > 0:
            #     assert self._children[lo - 1]._fragment[0] < fragment[0]
            # if lo < len(self._children):
            #     assert self._children[lo]._fragment[0] > fragment[0]
            self.children.insert(lo, _Node(fragment, value))
            return None

        assert hi > lo
        # Found a child with at least one common prefix character
        # noinspection PyUnboundLocalVariable
        child = self.children[mid]
        child_fragment = child.fragment
        # assert child_fragment[0] == ch
        # Count the number of common prefix characters
        common = 1
        len_fragment = len(fragment)
        len_child_fragment = len(child_fragment)
        while (
            common < len_fragment
            and common < len_child_fragment
            and fragment[common] == child_fragment[common]
        ):
            common += 1
        if common == len_child_fragment:
            # We have 'abcd' but the child is 'ab':
            # Recursively add the remaining 'cd' fragment to the child
            return child.add(fragment[common:], value)
        # Here we can have two cases:
        # either the fragment is a proper prefix of the child,
        # or the two diverge after #common characters
        # assert common < len_child_fragment
        # assert common <= len_fragment
        # We have 'ab' but the child is 'abcd',
        # or we have 'abd' but the child is 'acd'
        child.fragment = child_fragment[common:]  # 'cd'
        if common == len_fragment:
            # The fragment is a proper prefix of the child,
            # i.e. it is 'ab' while the child is 'abcd':
            # Break the child up into two nodes, 'ab' and 'cd'
            node = _Node(fragment, value)  # New parent 'ab'
            node.children = [child]  # Make 'cd' a child of 'ab'
        else:
            # The fragment and the child diverge,
            # i.e. we have 'abd' but the child is 'acd'
            new_fragment = fragment[common:]  # 'bd'
            # Make an internal node without a value
            node = _Node(fragment[0:common], None)  # 'a'
            # assert new_fragment[0] != child._fragment[0]
            if new_fragment[0] < child.fragment[0]:
                # Children: 'bd', 'cd'
                node.children = [_Node(new_fragment, value), child]
            else:
                node.children = [child, _Node(new_fragment, value)]
        # Replace 'abcd' in the original children list
        self.children[mid] = node
        return None

    def lookup(self, fragment: bytes) -> Any:
        """Lookup the given key fragment in this node and its children
        as necessary"""
        if not fragment:
            # We've arrived at our destination: return the value
            return self.value
        if self.children is None:
            # Nowhere to go: the key was not found
            return None
        # Note: The following could be a faster binary search,
        # but this lookup is not used in time critical code,
        # so the optimization is probably not worth it.
        for child in self.children:
            if fragment.startswith(child.fragment):
                # This is a continuation route: take it
                return child.lookup(fragment[len(child.fragment) :])
        # No route matches: the key was not found
        return None

    def __str__(self) -> str:
        s = "Fragment: '{0!r}', value '{1}'\n".format(self.fragment, self.value)
        c: List[str] = (
            ["   {0}".format(child) for child in self.children] if self.children else []
        )
        return s + "\n".join(c)


class Trie:

    """Wrapper class for a radix (compact) trie data structure.
    Each node in the trie contains a prefix string, leading
    to its children."""

    def __init__(self, root_fragment: bytes = b"") -> None:
        self._cnt = 0
        self._root = _Node(root_fragment, None)

    @property
    def root(self) -> _Node:
        return self._root

    def add(self, key: bytes, value: Any = None) -> Any:
        """Add the given (key, value) pair to the trie.
        Duplicates are not allowed and not added to the trie.
        If the value is None, it is set to the number of entries
        already in the trie, thereby making it function as
        an automatic generator of list indices."""
        assert key
        if value is None:
            value = self._cnt
        prev_value = self._root.add(key, value)
        if prev_value is not None:
            # The key was already found in the trie: return the
            # corresponding value
            return prev_value
        # Not already in the trie: add to the count and return the new value
        self._cnt += 1
        return value

    def get(self, key: bytes, default: Any = None) -> Any:
        """Lookup the given key and return the associated value,
        or the default if the key is not found."""
        value = self._root.lookup(key)
        return default if value is None else value

    def __getitem__(self, key: bytes) -> Any:
        """Lookup in square bracket notation"""
        value = self._root.lookup(key)
        if value is None:
            raise KeyError(key)
        return value

    def __len__(self) -> int:
        """Return the number of unique keys within the trie"""
        return self._cnt


_V = TypeVar("_V", bound=Hashable)


class Indexer(Generic[_V]):

    """A thin dict wrapper that maps unique values to indices and vice versa.
    The values must be hashable."""

    def __init__(self) -> None:
        self._d: Dict[_V, int] = dict()
        self._inv_d: Dict[int, _V] = dict()

    def add(self, s: _V) -> int:
        """Add a value to the indexer, if not already present. In any case,
        return the integer index of the value."""
        try:
            return self._d[s]
        except KeyError:
            ix = len(self._d)
            self._d[s] = ix
            self._inv_d[ix] = s
            return ix

    def items(self) -> Iterable[Tuple[int, _V]]:
        return self._inv_d.items()

    def __len__(self) -> int:
        return len(self._d)

    def __getitem__(self, key: int) -> _V:
        return self._inv_d[key]

    def get(self, key: int, default: Optional[_V] = None) -> Optional[_V]:
        return self._inv_d.get(key, default)

    def __str__(self) -> str:
        return str(self._d)


class MeaningsIndexer(Indexer[MeaningTuple]):

    """Maintain an index of integer keys to meaning tuples,
    where each meaning tuple is (ordfl, beyging)"""

    def __init__(self) -> None:
        super().__init__()
        # Add an occurrence counter
        self._count: DefaultDict[int, int] = defaultdict(int)
        # Add a map from original indices to frequency-ordered indices, and back
        self._freq_map: Dict[int, int] = dict()
        self._inv_freq_map: Dict[int, int] = dict()

    def add(self, s: MeaningTuple) -> int:
        """Add a value and count distinct occurrences"""
        ix = super().add(s)
        self._count[ix] += 1
        return ix

    def freq_index(self, key: int) -> int:
        """Cast a meaning index to a frequency-ordered index, so that the
        most common meaning is at index 0, etc."""
        if not self._freq_map:
            # The ground truth source: a list of (original index, count) tuples
            sorted_items = sorted(
                self._count.items(), key=lambda item: item[1], reverse=True
            )
            self._freq_map = {
                # Map original index to new
                item[0]: new_ix
                for new_ix, item in enumerate(sorted_items)
            }
            # Create the inverse map
            self._inv_freq_map = {
                # Map new index to original
                new_ix: item[0]
                for new_ix, item in enumerate(sorted_items)
            }
        return self._freq_map[key]

    def by_freq_index(self, freq_index: int) -> MeaningTuple:
        """Return a meaning tuple from a frequency index"""
        return self._inv_d[self._inv_freq_map[freq_index]]


class KsnidIndexer(Indexer[bytes]):
    pass


class SubcatIndexer(Indexer[bytes]):
    pass


class BinCompressor:

    """This class generates a compressed binary file from plain-text
    dictionary data. The input plain-text file is assumed to be coded
    in UTF-8 and have either six (SHsnid) or fifteen (Ksnid) columns,
    delimited by semicolons (';'), i.e. (for SHsnid):

    (Icelandic) ord;bin_id;ofl;hluti;bmynd;mark
    (English)   lemma;issue;class;domain;form;inflection

    The compression is not particularly intensive, as there is a
    tradeoff between the compression level and lookup speed. The
    resulting binary file is assumed to be read completely into
    memory as a BLOB and usable directly for lookup without further
    unpacking into higher-level data structures. See the BinCompressed
    class for the lookup code.

    Note that text strings and characters in the binary BLOB are
    processed in Latin-1 encoding, and Latin-1 ordinal numbers are
    used directly as sort keys.

    To help the packing of common Trie nodes (single-character ones),
    a mapping of the source alphabet to 7-bit indices is used.
    This means that the source alphabet can contain no more than
    127 characters (ordinal 0 is reserved).

    The current set of possible subcategories is as follows:

        heö, alm, ism, föð, móð, fyr, bibl, gæl, lönd, gras, efna, tölv, lækn,
        örn, tón, natt, göt, lög, íþr, málfr, tími, við, fjár, bíl, ffl, mat,
        bygg, tung, erl, hetja, bær, þor, mvirk, brag, jard, stærð, hug, erm,
        mæl, titl, gjald, stja, dýr, hann, ætt, ob, entity, spurn

    """

    def __init__(self) -> None:
        self._forms = Trie()  # bmynd
        self._lemmas: Dict[
            int, Tuple[bytes, int]
        ] = dict()  # bin_id -> (lemma, category index)
        self._meanings = MeaningsIndexer()  # mark
        self._ksnid_strings = KsnidIndexer()  # ksnid additional fields
        self._subcats = SubcatIndexer()  # hluti
        self._alphabet: Set[int] = set()
        self._alphabet_bytes = bytes()
        # map form index -> { (bin_id, meaning_ix, ksnid_ix) }
        self._lookup_form: Dict[int, Set[Tuple[int, int, int]]] = defaultdict(set)
        # map bin_id -> set of all associated word forms
        self._lemma_forms: Dict[int, Set[bytes]] = defaultdict(set)
        # Count of lemma word categories
        self._lemma_cat_count: Dict[str, int] = defaultdict(int)
        # Word form templates
        self._templates: Dict[bytes, int] = dict()
        # Running bin_id index counter
        self._utg = 0
        # The starting bin_id index of Greynir additions
        self._begin_greynir_utg = 0
        # Highest bin_id
        self._max_bin_id = 0
        # The indices of the most common ksnid_strings
        common_kix_0 = self._ksnid_strings.add(KSNID_COMMON_0.encode("latin-1"))
        assert COMMON_KIX_0 == common_kix_0
        common_kix_1 = self._ksnid_strings.add(KSNID_COMMON_1.encode("latin-1"))
        assert COMMON_KIX_1 == common_kix_1

    @staticmethod
    def fix_bugs(m: Ksnid) -> bool:
        """Fix known bugs in BÍN. Return False if the record should
        be skipped entirely; otherwise True."""
        if (
            not m.ord
            or not m.bmynd
            or m.bmynd in BAD_BMYND
        ):
            return False
        elif m.ord == "sem að" and m.bin_id == 495372:
            # Fix BÍN bug
            m.ord = "sem"
            m.bmynd = "sem"
        elif m.ord == "hvort að" and m.bin_id == 495365:
            # Fix BÍN bug
            m.ord = "hvort"
            m.bmynd = "hvort"
        elif m.ord == "árekstrarvörn" and m.bin_id == 540745:
            return m.bmynd.startswith("árekstrar")
        elif m.ord == "dínamítsprenging" and m.bin_id == 508550:
            m.bmynd = m.bmynd.replace("dýnamít", "dínamít")
        elif m.ord == "fullleiksviðslegur" and m.bin_id == 509413:
            if not m.bmynd.startswith("full"):
                m.bmynd = "full" + m.bmynd
        elif m.ord == "fullmenntaskólalegur" and m.bin_id == 509414:
            if not m.bmynd.startswith("full"):
                m.bmynd = "full" + m.bmynd
        elif m.ord == "fulltæfulegur" and m.bin_id == 509415:
            if not m.bmynd.startswith("full"):
                m.bmynd = "full" + m.bmynd
        elif m.ord == "fullviðkvæmnislegur" and m.bin_id == 509416:
            if not m.bmynd.startswith("full"):
                m.bmynd = "full" + m.bmynd
        elif m.ord == "illinnheimtanlegur" and m.bin_id == 509831:
            if not m.bmynd.startswith("ill"):
                m.bmynd = "ill" + m.bmynd
        elif m.ord == "Norður-Landeyjar" and m.bin_id == 488593:
            if m.bmynd.startswith("Norð-Vestur"):
                m.bmynd = m.bmynd.replace("Norð-Vestur", "Norður")
            elif m.bmynd.startswith("Norð-vestur"):
                m.bmynd = m.bmynd.replace("Norð-vestur", "Norður")
        # Skip this if the lemma is capitalized differently
        # than the word form (which is a bug in BÍN)
        if m.ord[0].isupper() != m.bmynd[0].isupper():
            return False
        # Skip this if the word form is a single letter but the stem is not;
        # except for the words "eiga", "ýr" and "ær"
        if len(m.bmynd) == 1 and len(m.ord) > 1 and m.ord not in {"ýr", "ær", "eiga"}:
            return False
        # 'snættt' is a bug in BÍN
        if m.bmynd.endswith("ttt"):
            return False
        return True

    def read(self, fnames: Iterable[str]) -> None:
        """Read the given .csv text files in turn and add them to the
        compressed data structures"""
        cnt = 0
        max_wix = 0
        start_time = time.time()
        last_stofn = ""
        for fname in fnames:
            print("Reading file '{0}'...".format(fname))
            fn: str = fname.split("/")[-1]
            with open(fname, "r", encoding="utf-8") as f:
                for line in f:
                    cnt += 1
                    line = line.strip()
                    if not line or line[0] == "#":
                        # Empty line or comment: skip
                        continue
                    t = line.split(";")
                    m = Ksnid()
                    if len(t) == 6:
                        # Older (SHsnid) format file, containing Greynir additions
                        m.ord, bin_id, m.ofl, m.hluti, m.bmynd, m.mark = t
                        m.bin_id = int(bin_id)
                        if m.bin_id <= 0:
                            # No bin_id number: allocate a new one
                            if self._begin_greynir_utg == 0:
                                # First Greynir number: round up to a nice
                                # number divisible by 1000, leaving a headroom of
                                # at least 1000 numbers for BÍN
                                self._utg = ((self._utg + 1999) // 1000) * 1000
                                self._begin_greynir_utg = self._utg
                                last_stofn = m.ord
                            elif m.ord != last_stofn:
                                # New lemma: increment the bin_id number
                                self._utg += 1
                                last_stofn = m.ord
                            if m.bin_id == -1:
                                # This is a suffix only, coming from
                                # ord.suffix.csv: mark it with birting='S'
                                m.birting = "S"
                            # Assign a Greynir bin_id number
                            m.bin_id = self._utg
                        else:
                            # This is a Greynir addition to an existing
                            # BÍN entry (probably a plural form):
                            # mark it with birting='G'
                            m.birting = "G"
                    else:
                        # Newer (KRISTINsnid) format file
                        m = Ksnid.from_tuple(t)
                        if m.bin_id > self._utg:
                            # Keep track of the highest bin_id number from BÍN
                            self._utg = m.bin_id
                    # Avoid bugs in BÍN
                    if not self.fix_bugs(m):
                        print(
                            f"Skipping invalid data (lemma '{m.ord}', bin_id {m.bin_id}, "
                            f"bmynd '{m.bmynd}'), line {cnt} in {fn}"
                        )
                        continue
                    # Ensure mark makes sense
                    if not MarkOrder.valid_mark(m.ofl, m.mark):
                        print(
                            f"Skipping due to invalid mark (lemma '{m.ord}', bin_id {m.bin_id}, "
                            f"bmynd '{m.bmynd}', ofl '{m.ofl}', mark '{m.mark}'), line {cnt} in {fn}"
                        )
                        continue
                    try:
                        lemma = m.ord.encode("latin-1")
                        ofl = m.ofl.encode("latin-1")
                        hluti = m.hluti.encode("latin-1")
                        form = m.bmynd.encode("latin-1")
                        meaning = m.mark.encode("latin-1")
                        ksnid = m.ksnid_string.encode("latin-1")
                    except UnicodeEncodeError:
                        try:
                            print(
                                f"Latin-1 encoding error for (lemma '{m.ord}', bin_id {m.bin_id}, "
                                f"bmynd '{m.bmynd}'), line {cnt} in {fn}"
                            )
                        except:
                            # Hack to fix issues with printing utf-8 characters to the Windows shell
                            print(
                                f"Latin-1 encoding error ${m.bin_id}, line {cnt} in {fn}"
                            )
                        continue
                    suspicious_letters = set(m.bmynd) & SUSPICIOUS_LETTERS
                    # If any suspicious letters are found in the form, print a warning
                    if suspicious_letters:
                        print(
                            f"Suspicious letters {suspicious_letters} "
                            f"in form '{m.bmynd}' of lemma '{m.ord}', bin_id {m.bin_id}, line {cnt} in {fn}"
                        )
                        continue
                    self._alphabet |= set(form)
                    # Subcategory (hluti) index
                    cix = self._subcats.add(hluti)
                    # BIN id number (unique lemma id)
                    wix = m.bin_id
                    if wix > max_wix:
                        max_wix = wix
                    if wix in self._lemmas:
                        # We have seen this bin_id number before: make some sanity checks
                        p_lemma, p_cix = self._lemmas[wix]
                        if p_lemma != lemma:
                            print(
                                f"Warning: bin_id {wix} refers to different lemmas, "
                                f"i.e. {lemma.decode('latin-1')}/{cix} and "
                                f"{p_lemma.decode('latin-1')}/{p_cix}"
                            )
                            print("Skipping this record")
                            continue
                        if cix != p_cix:
                            # Different subcategory index: replace it to conform
                            # with the previously seen one
                            cix = p_cix
                    else:
                        # New lemma, not seen before: count its category (ofl)
                        self._lemma_cat_count[m.ofl] += 1
                    # Add a (lemma index, subcat index) tuple
                    self._lemmas[wix] = (lemma, cix)
                    # Form index
                    fix = self._forms.add(form)
                    # Combined (ofl, meaning) index
                    mix = self._meanings.add((ofl, meaning))
                    # Ksnid string index
                    kix = self._ksnid_strings.add(ksnid)
                    self._lookup_form[fix].add((wix, mix, kix))
                    # Add this word form to the set of word forms
                    # of its lemma, if it is different from the lemma
                    if lemma != form:
                        self._lemma_forms[wix].add(form)
                    # Progress indicator
                    if not quiet:
                        if cnt % 10000 == 0:
                            print(cnt, end="\r")
        self._max_bin_id = max_wix
        print("{0} done\n".format(cnt))
        print("Time: {0:.1f} seconds".format(time.time() - start_time))
        if not quiet:
            print("Highest bin_id (wix) is {0}".format(max_wix))
        # Convert alphabet set to contiguous byte array, sorted by ordinal
        alphabet: Set[int] = self._alphabet  # Line added to pacify Pylance
        self._alphabet_bytes = bytes(sorted(alphabet))

    def print_stats(self) -> None:
        """Print a few key statistics about the dictionary"""
        print("Forms are {0}".format(len(self._forms)))
        print("Lemmas are {0}".format(len(self._lemmas)))
        if not quiet:
            print("They are distributed as follows:")
            for key, val in self._lemma_cat_count.items():
                print("   {0:6s} {1:8d}".format(key, val))
        print("Subcategories are {0}".format(len(self._subcats)))
        print("Meanings are {0}".format(len(self._meanings)))
        print("Ksnid-strings are {0}".format(len(self._ksnid_strings)))
        # Uncomment the following to view the Ksnid-strings
        # klist = [f"{v.decode('latin-1')}: {k}" for k, v in self._ksnid_strings.items()]
        # print("\n".join(sorted(klist)))
        if not quiet:
            print("The alphabet is '{0!r}'".format(self._alphabet_bytes))
            print(f"In UTF-8: '{self._alphabet_bytes.decode('latin-1')}'")
            print("It contains {0} characters".format(len(self._alphabet_bytes)))

    def lookup(self, form: str) -> List[BinEntryTuple]:
        """Test lookup of SHsnid tuples from uncompressed data"""
        form_latin = form.encode("latin-1")
        try:
            values = self._lookup_form[self._forms[form_latin]]
            # Obtain the lemma and meaning tuples corresponding to the word form
            result = [
                (bin_id, self._lemmas[bin_id], self._meanings[mix])
                for bin_id, mix, _ in values
            ]
            # Convert to Unicode and return a 5-tuple
            # (ord, bin_id, ofl, hluti, bmynd, mark)
            return [
                (
                    s[0].decode("latin-1"),  # ord
                    bin_id,
                    m[0].decode("latin-1"),  # ofl
                    self._subcats[s[1]].decode("latin-1"),  # hluti
                    form,  # bmynd
                    m[1].decode("latin-1"),  # mark
                )
                for bin_id, s, m in result
            ]
        except KeyError:
            return []

    def lookup_ksnid(self, form: str) -> List[Ksnid]:
        """Test lookup of KRISTINsnid tuples from uncompressed data"""
        form_latin = form.encode("latin-1")
        try:
            result: List[Ksnid] = []
            values = self._lookup_form[self._forms[form_latin]]
            # Obtain the lemma and meaning tuples corresponding to the word form
            for bin_id, mix, kix in values:
                word, fl_ix = self._lemmas[bin_id]
                ofl, mark = self._meanings[mix]
                ksnid = self._ksnid_strings[kix]
                result.append(
                    Ksnid.from_parameters(
                        word.decode("latin-1"),
                        bin_id,
                        ofl.decode("latin-1"),
                        self._subcats[fl_ix].decode("latin-1"),  # hluti
                        form,  # bmynd
                        mark.decode("latin-1"),
                        ksnid.decode("latin-1"),
                    )
                )
            return result
        except KeyError:
            return []

    def lookup_forms(self, form: str, case: str = "NF") -> List[Tuple[str, str]]:
        """Test lookup of all forms having the same lemma as the given form"""
        form_latin = form.encode("latin-1")
        case_latin = case.encode("latin-1")
        try:
            values = self._lookup_form[self._forms[form_latin]]
            # Obtain the lemma and meaning tuples corresponding to the word form
            v: Set[Tuple[bytes, bytes]] = set()
            # Go through the distinct lemmas found for this word form
            for bin_id in set(vv[0] for vv in values):
                # Look at all word forms of this lemma
                lemma = self._lemmas[bin_id][0]
                for canonical in [lemma] + list(self._lemma_forms.get(bin_id, set())):
                    for s, m, _ in self._lookup_form[self._forms[canonical]]:
                        if s == bin_id:
                            b = self._meanings[m][1]
                            if case_latin in b:
                                # The 'mark' string contains the requested case
                                v.add((b, canonical))
            return [(m.decode("latin-1"), f.decode("latin-1")) for m, f in v]
        except KeyError:
            return []

    def write_forms(self, f: IO[bytes], alphabet: bytes, lookup_map: List[int]) -> None:
        """Write the forms trie contents to a packed binary stream"""
        # We assume that the alphabet can be represented in 7 bits
        assert len(alphabet) + 1 < 2**7
        todo: List[Tuple[_Node, int]] = []
        node_cnt = 0
        single_char_node_count = 0
        multi_char_node_count = 0
        no_child_node_count = 0

        def write_node(node: _Node, parent_loc: int) -> None:
            """Write a single node to the packed binary stream,
            and fix up the parent's pointer to the location
            of this node"""
            loc = f.tell()
            ix: Optional[int] = node.value
            val = 0x007FFFFF if ix is None else lookup_map[ix]
            assert val < 2**23
            nonlocal node_cnt, single_char_node_count, multi_char_node_count
            nonlocal no_child_node_count
            node_cnt += 1
            childless_bit = 0 if node.children else 0x40000000
            if len(node.fragment) <= 1:
                # Single-character fragment:
                # Pack it into 32 bits, with the high bit
                # being 1, the childless bit following it,
                # the fragment occupying the next 7 bits,
                # and the value occupying the remaining 23 bits
                if len(node.fragment) == 0:
                    chix = 0
                else:
                    chix = alphabet.index(node.fragment[0]) + 1
                assert chix < 2**7
                f.write(
                    UINT32.pack(
                        0x80000000 | childless_bit | (chix << 23) | (val & 0x007FFFFF)
                    )
                )
                single_char_node_count += 1
                b = None
            else:
                # Multi-character fragment:
                # Store the value first, in 32 bits, and then
                # the fragment bytes with a trailing zero, padded to 32 bits
                f.write(UINT32.pack(childless_bit | (val & 0x007FFFFF)))
                b = node.fragment
                multi_char_node_count += 1
            # Write the child nodes, if any
            if node.children:
                f.write(UINT32.pack(len(node.children)))
                for child in node.children:
                    todo.append((child, f.tell()))
                    # Write a placeholder - will be overwritten
                    f.write(UINT32.pack(0xFFFFFFFF))
            else:
                no_child_node_count += 1
            if b is not None:
                f.write(struct.pack("{0}s0I".format(len(b) + 1), b))
            if parent_loc > 0:
                # Fix up the parent
                end = f.tell()
                f.seek(parent_loc)
                f.write(UINT32.pack(loc))
                f.seek(end)

        write_node(self._forms.root, 0)
        while todo:
            write_node(*todo.pop())

        print(
            "Written {0} nodes, thereof {1} single-char nodes and {2} multi-char.".format(
                node_cnt, single_char_node_count, multi_char_node_count
            )
        )
        print("Childless nodes are {0}.".format(no_child_node_count))

    def write_binary(self, fname: str) -> None:
        """Write the compressed structure to a packed binary file"""
        print("Writing file '{0}'...".format(fname))
        # Create a byte buffer stream
        f: IO[bytes] = io.BytesIO()

        # Version header
        f.write(BIN_COMPRESSOR_VERSION)

        # Placeholders for pointers to the major sections of the file
        mapping_offset = f.tell()
        f.write(UINT32.pack(0))
        forms_offset = f.tell()
        f.write(UINT32.pack(0))
        lemmas_offset = f.tell()
        f.write(UINT32.pack(0))
        templates_offset = f.tell()
        f.write(UINT32.pack(0))
        meanings_offset = f.tell()
        f.write(UINT32.pack(0))
        alphabet_offset = f.tell()
        f.write(UINT32.pack(0))
        subcats_offset = f.tell()
        f.write(UINT32.pack(0))
        ksnid_offset = f.tell()
        f.write(UINT32.pack(0))

        # Store the lowest Greynir-specific bin_id number
        f.write(UINT32.pack(self._begin_greynir_utg))

        # Store the highest allowed BÍN id
        f.write(UINT32.pack(self._max_bin_id))

        def write_padded(b: bytes, n: int) -> None:
            assert len(b) <= n
            f.write(b + b"\x00" * (n - len(b)))

        def write_aligned(s: bytes) -> None:
            """Write a string in the latin-1 charset, zero-terminated,
            padded to align on a DWORD (32-bit) boundary"""
            f.write(struct.pack("{0}s0I".format(len(s) + 1), s))

        def write_spaced(s: bytes) -> None:
            """Write a string in the latin-1 charset, zero-terminated,
            padded to align on a DWORD (32-bit) boundary"""
            pad = 4 - (len(s) & 0x03)  # Always add at least one space
            f.write(s + b" " * pad)

        def write_string(s: bytes) -> None:
            """Write a string preceded by a length byte, aligned to a
            DWORD (32-bit) boundary"""
            f.write(struct.pack("B{0}s0I".format(len(s)), len(s), s))

        def compress_set(s: Set[bytes], base: Optional[bytes] = None) -> bytearray:
            """Write a set of strings as a single compressed string."""

            # Each string is written as a variation of the previous
            # string, or the given base string, or the lexicographically
            # smallest string if no base is given. A variation consists
            # of a leading byte indicating the number of characters to be
            # cut off the end of the previous string, before appending the
            # following characters (prefixed by a length byte). The
            # set "hestur", "hest", "hesti", "hests" is thus encoded
            # like so, assuming "hestur" is the base (lemma):
            # 1) The set is sorted to become the list
            #    "hest", "hesti", "hests", "hestur"
            # 2) "hest" is written as 2, 0, ""
            # 3) "hesti" is written as 0, 1, "i"
            # 4) "hests" is written as 1, 1, "s"
            # 5) "hestur" is written as 1, 2, "ur"
            # Note that a variation string such as this one, with four components,
            # is stored only once and then referred to by index. This saves
            # a lot of space since declension variants are identical
            # for many different lemmas.

            # Sort the set for maximum compression
            ss = sorted(s)
            b: bytearray = bytearray()
            if base is None:
                # Use the first word in the set as a base
                last_w = ss[0]
                llast = len(last_w)
                b.append(len(last_w))
                b += last_w
                it = ss[1:]
            else:
                # Use the given base
                last_w = base
                llast = len(last_w)
                it = ss
            for w in it:
                lw = len(w)
                # Find number of common characters in front
                i = 0
                while i < llast and i < lw and last_w[i] == w[i]:
                    i += 1
                # Write the number of characters to cut off from the end
                cut = llast - i
                # Remember the last word
                last_w = w
                # Cut the common chars off
                w = w[i:]
                # Write the divergent part
                # We use 4 bits for the cut and 3 bits for the difference between
                # the cut and the length. If this doesn't fit, we set the high bit
                # and store the cut and the length in two bytes.
                diff = len(w) - cut
                if cut <= 15 and (-4 <= diff <= 3):
                    b.append(cut << 3 | (diff & 0x07))
                else:
                    assert cut <= 127
                    b.append(cut | 0x80)
                    b.append(len(w))
                b += w
                llast = lw
            # End of list marker
            b.append(0x00)
            return b

        def fixup(ptr: int) -> None:
            """Go back and fix up a previous pointer to point at the
            current offset in the stream"""
            loc = f.tell()
            f.seek(ptr)
            f.write(UINT32.pack(loc))
            f.seek(loc)

        # Write the alphabet
        write_padded(b"[alphabet]", 16)
        fixup(alphabet_offset)
        f.write(UINT32.pack(len(self._alphabet_bytes)))
        write_aligned(self._alphabet_bytes)

        # Write the form to meaning mapping
        write_padded(b"[mapping]", 16)
        fixup(mapping_offset)
        lookup_map: List[int] = []
        # Count of the meaning entries
        cnt_entries = 0
        # Count of the 32-bit words written
        cnt_32 = 0
        cnt_identical_bin = 0
        # Loop through word forms
        for fix in range(len(self._forms)):
            lookup_map.append(cnt_32)
            # Each word form may have multiple meanings:
            # loop through them
            num_meanings = len(self._lookup_form[fix])
            assert num_meanings > 0
            # Bucket the meanings by BÍN id
            lookup_lemmas: DefaultDict[int, List[Tuple[int, int]]] = defaultdict(list)
            for bin_id, mix, kix in self._lookup_form[fix]:
                lookup_lemmas[bin_id].append((mix, kix))
            # Index of the meaning being written
            ix = 0
            for bin_id, mlist in lookup_lemmas.items():
                # Allocate bits for the lemma index
                assert bin_id < BIN_ID_MAX
                last_bin_id: Optional[int] = None
                for mix, kix in mlist:
                    assert mix < MEANING_MAX
                    assert kix < KSNID_MAX
                    # Map the meaning index to a frequency-ordered index
                    freq_ix = self._meanings.freq_index(mix)
                    assert freq_ix < MEANING_MAX
                    # Mark the last meaning with the high bit
                    w = 0x80000000 if ix == num_meanings - 1 else 0
                    if (kix == COMMON_KIX_0 or kix == COMMON_KIX_1) and freq_ix < 255:
                        # We can pack this into a single 32-bit entry:
                        # kix is 1 bit
                        # meaning index (freq_ix) is 8 bits
                        # bin_id is 20 bits
                        # Layout:
                        # L11KMMMM|MMMMBBBB|BBBBBBBB|BBBBBBBB
                        # MMMMMMM > 0
                        w |= 0x60000000  # Indicates a single 32-bit packed entry
                        if kix == COMMON_KIX_1:
                            w |= 0x10000000  # kix bit, 0 or 1 for COMMON_KIX_0 or COMMON_KIX_1
                        w |= (freq_ix + 1) << BIN_ID_BITS
                        # Low 20 contain the BÍN id
                        w |= bin_id
                        f.write(UINT32.pack(w))
                        cnt_32 += 1
                        last_bin_id = bin_id
                    elif bin_id == last_bin_id:
                        # The BÍN id is the same as the last one: Use that fact to
                        # squeeze the meaning and the ksnid index into a single word
                        # meaning index (freq_ix) is 10 bits
                        # Layout:
                        # L1000000|MMMMMMMM|MMKKKKKK|KKKKKKKK
                        cnt_identical_bin += 1
                        w |= 0x40000000  # Indicates a single 32-bit entry
                        w |= (freq_ix << KSNID_BITS) | kix
                        f.write(UINT32.pack(w))
                        cnt_32 += 1
                    else:
                        # We need two 32-bit entries
                        last_bin_id = bin_id
                        # First, write the BÍN id and the last meaning bit
                        # Note that in this case, the 7 bits for the meaning
                        # index are 0, which cannot happen in the single-word case
                        # Layout:
                        # L0000000|0000BBBB|BBBBBBBB|BBBBBBBB
                        w |= bin_id
                        f.write(UINT32.pack(w))
                        cnt_32 += 1
                        # Then, write the meaning index (frequency-ordered) and the
                        # ksnid index. The meaning index can be up to 10 bits
                        # and the ksnid up to 14 bits.
                        w = (freq_ix << KSNID_BITS) | kix
                        # Layout:
                        # 00000000|MMMMMMMM|MMKKKKKK|KKKKKKKK
                        f.write(UINT32.pack(w))
                        cnt_32 += 1
                    ix += 1
                    cnt_entries += 1

        cnt_double = cnt_32 - cnt_entries
        cnt_single = cnt_entries - cnt_double
        assert cnt_32 == cnt_single + cnt_double * 2
        assert cnt_entries == cnt_single + cnt_double
        print(f"Word meaning entries are {cnt_entries}, stored in {cnt_32} 32-bit words")
        print(
            f"32-bit entries are {cnt_single}, "
            f"64-bit entries are {cnt_double}"
        )
        print(
            f"32-bit entries having identical BÍN ids "
            f"to previous ones are {cnt_identical_bin}"
        )
        # Write the the compact radix trie structure that
        # holds the word forms themselves, mapping them
        # to indices
        fixup(forms_offset)
        self.write_forms(f, self._alphabet_bytes, lookup_map)

        # Write the lemmas
        write_padded(b"[lemmas]", 16)
        lookup_map = []
        # Keep track of the number of bytes that have been written
        # to the template buffer
        template_bytes = 0
        for bin_id in range(self._max_bin_id + 1):
            if bin_id not in self._lemmas:
                # We have no lemma with this bin_id: store a null pointer (offset)
                lookup_map.append(0)
                continue
            lemma, cix = self._lemmas[bin_id]
            lookup_map.append(f.tell())
            # Squeeze the subcategory index into the lower 31 bits.
            # The uppermost bit flags whether a canonical forms list is present.
            assert 0 <= cix < 2**SUBCAT_BITS
            bits = cix
            has_template = False
            if bin_id in self._lemma_forms:
                # We have a set of word forms for this lemma
                # (that differ from the lemma itself)
                bits |= 0x80000000
                has_template = True
            f.write(UINT32.pack(bits))
            # Write the lemma
            write_string(lemma)
            # Write the inflection template, compressed, if the lemma
            # has multiple associated word forms
            if has_template:
                b = bytes(compress_set(self._lemma_forms[bin_id], base=lemma))
                # Have we seen this inflection template before?
                template_offset = self._templates.get(b)
                if template_offset is None:
                    # No: put it in the template buffer, at the current offset
                    template_offset = template_bytes
                    template_bytes += len(b)
                    self._templates[b] = template_offset
                f.write(UINT32.pack(template_offset))

        print("Distinct inflection templates are {0}".format(len(self._templates)))
        print("Bytes used for templates are {0}".format(template_bytes))

        # Write the bin_id-to-offset mapping table for lemmas
        fixup(lemmas_offset)
        for offset in lookup_map:
            f.write(UINT32.pack(offset))

        # Write the inflection templates
        write_padded(b"[templates]", 16)
        fixup(templates_offset)
        # Sort the case variants array by increasing offset
        # (actually, this should not be needed if the dict is enumerated
        # in insertion order, but just in case)
        check = 0
        for b, offset in self._templates.items():
            assert offset == check
            f.write(b)
            check += len(b)
        # Align to a 16-byte boundary
        align = check % 16
        if align:
            f.write(b"\x00" * (16 - align))

        # Write the meanings, i.e. the distinct BÍN 'mark' strings
        write_padded(b"[meanings]", 16)
        lookup_map = []
        num_meanings = len(self._meanings)
        f.write(UINT32.pack(num_meanings))
        for ix in range(num_meanings):
            lookup_map.append(f.tell())
            write_spaced(b" ".join(self._meanings.by_freq_index(ix)))  # ofl, mark
        f.write(b" " * 24)

        # Write the index-to-offset mapping table for meanings
        fixup(meanings_offset)
        for offset in lookup_map:
            f.write(UINT32.pack(offset))

        # Write the ksnid strings
        write_padded(b"[ksnid]", 16)
        lookup_map = []
        num_meanings = len(self._ksnid_strings)
        f.write(UINT32.pack(num_meanings))
        for ix in range(num_meanings):
            lookup_map.append(f.tell())
            write_string(self._ksnid_strings[ix])

        # Write the index-to-offset mapping table for ksnid strings
        fixup(ksnid_offset)
        for offset in lookup_map:
            f.write(UINT32.pack(offset))

        # Write the subcategories, space-separated
        fixup(subcats_offset)
        b = b" ".join(self._subcats[ix] for ix in range(len(self._subcats)))
        f.write(UINT32.pack(len(b)))
        write_aligned(b)

        # Write the entire byte buffer stream to the compressed file
        with open(fname, "wb") as stream:
            stream.write(f.getvalue())


print("Welcome to the BinPackage compressed vocabulary file generator")

b = BinCompressor()
b.read(
    [
        # Note: KRISTINsnid.csv must be the first file in the list
        os.path.join(_path, "resources", "KRISTINsnid.csv"),
        os.path.join(_path, "resources", "ord.add.csv"),
        os.path.join(_path, "resources", "ord.auka.csv"),
        os.path.join(_path, "resources", "systematic_additions.csv"),
        os.path.join(_path, "resources", "ord.suffixes.csv"),
    ]
)
b.print_stats()

filename = os.path.join(_path, "resources", BIN_COMPRESSED_FILE)
b.write_binary(filename)

print("Done; the compressed vocabulary was written to {0}".format(filename))
