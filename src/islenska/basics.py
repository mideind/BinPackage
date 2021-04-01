"""

    BinPackage

    Basic configuration data

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

    This module contains various common configuration data and utility
    routines.

"""

from typing import (
    Iterator,
    NamedTuple,
    Sequence,
    Type,
    TypeVar,
    Generic,
    Dict,
    Callable,
    Counter,
    Tuple,
    Optional,
)

import os
import struct
from heapq import nsmallest
from operator import itemgetter
from pkg_resources import resource_stream

import threading

INT32 = struct.Struct("<i")
UINT32 = struct.Struct("<I")

# BÍN compressed file format version (used in tools/binpack.py and bincompress.py)
BIN_COMPRESSOR_VERSION = b"Greynir 02.00.00"
assert len(BIN_COMPRESSOR_VERSION) == 16
BIN_COMPRESSED_FILE = "compressed.bin"

# The following are encoded with each word form
# Bits allocated for the lemma index (currently max 310787)
LEMMA_BITS = 19
LEMMA_MAX = 2 ** LEMMA_BITS
# Bits allocated for the meaning index (currently max 968)
MEANING_BITS = 10
MEANING_MAX = 2 ** MEANING_BITS
# Make sure that we have at least three high bits available for other
# purposes in a 32-bit word that already contains a lemma index and a meaning index
assert LEMMA_BITS + MEANING_BITS <= 29
# Bits allocated for the ksnid-string index (currently max 5826)
KSNID_BITS = 13
KSNID_MAX = 2 ** KSNID_BITS

# The following are encoded with each lemma
# Bits allocated for the bin_id number (currently max 513582)
UTG_BITS = 23
# Bits allocated for the subcategory index (hluti) (currently max 49)
SUBCAT_BITS = 8

# The two most common Ksnid strings
KSNID_COMMON_0 = "1;;;;V;1;;;"
KSNID_COMMON_1 = "1;;;;K;1;;;"

# Indices into the ksnid_strings dictionary for the most common Ksnid strings
COMMON_KIX_0 = 0
COMMON_KIX_1 = 1

# Special Ksnid string used for synthetic word forms, having 'birting'='G'
KSNID_GREYNIR = "1;;;;G;1;;;"

LFU_DEFAULT = 512

# Type variables for keys and values
_K = TypeVar("_K")
_V = TypeVar("_V")

ALL_CASES = frozenset(("nf", "þf", "þgf", "ef"))
ALL_GENDERS = frozenset(("kk", "kvk", "hk"))
ALL_NUMBERS = frozenset(("et", "ft"))

ALL_BIN_CASES = frozenset(("NF", "ÞF", "ÞGF", "EF"))
ALL_BIN_NUMBERS = frozenset(("ET", "FT"))
ALL_BIN_GENDERS = frozenset(("KK", "KVK", "HK"))
ALL_BIN_PERSONS = frozenset(("1P", "2P", "3P"))
ALL_BIN_DEGREES = frozenset(("ESB", "EVB", "FSB", "FVB", "MST", "VB", "SB"))
ALL_BIN_TENSES = frozenset(("ÞT", "NT"))
ALL_BIN_VOICES = frozenset(("GM", "MM"))
# We deliberately leave out "LHÞT" as it is quite a different beast than the others
ALL_BIN_MOODS = frozenset(("LHNT", "NH", "FH", "VH", "BH"))

CASES = ("NF", "ÞF", "ÞGF", "EF")
CASES_LATIN = tuple(case.encode("latin-1") for case in CASES)

BeygingFilter = Callable[[str], bool]

MeaningTuple = Tuple[str, int, str, str, str, str]

# Named tuple for the smaller "Sigrúnarsnið" (SHsnid) vocabulary format
BinMeaning = NamedTuple(
    "BinMeaning",
    [
        ("ord", str),
        ("bin_id", int),
        ("ofl", str),
        ("hluti", str),
        ("bmynd", str),
        ("mark", str),
    ],
)

# Compact string representation
_meaning_repr: Callable[[BinMeaning], str] = lambda self: (
    "(ord='{0}', {2}/{3}/{1}, bmynd='{4}', {5})".format(
        self.ord, self.bin_id, self.ofl, self.hluti, self.bmynd, self.mark
    )
)

setattr(BinMeaning, "__str__", _meaning_repr)
setattr(BinMeaning, "__repr__", _meaning_repr)


def make_bin_meaning(
    ord: str,
    bin_id: int,
    ofl: str,
    hluti: str,
    bmynd: str,
    mark: str,
    copy_from: Optional[BinMeaning] = None,
) -> BinMeaning:
    """ Constructor for BinMeaning instances """
    return BinMeaning(ord, bin_id, ofl, hluti, bmynd, mark)


# Type variable for the Ksnid class
_Ksnid = TypeVar("_Ksnid", bound="Ksnid")


class Ksnid:

    """ A class corresponding to the BÍN KRISTINsnid format """

    def __init__(self) -> None:
        self.ord: str = ""
        self.bin_id: int = 0
        self.ofl: str = ""
        self.hluti: str = ""
        self.einkunn: int = 0
        self.malsnid: str = ""
        self.malfraedi: str = ""
        self.millivisun: int = 0
        self.birting: str = ""
        self.bmynd: str = ""
        self.mark: str = ""
        self.beinkunn: int = 0
        self.bmalsnid: str = ""
        self.bgildi: str = ""
        self.aukafletta: str = ""

    def __str__(self) -> str:
        return (
            f"<Ksnid: bmynd='{self.bmynd}', "
            f"ord/ofl/hluti/bin_id='{self.ord}'/{self.ofl}/{self.hluti}/{self.bin_id}, "
            f"mark={self.mark}, "
            f"ksnid='{self.ksnid_string}'>"
        )

    @property
    def ksnid_string(self) -> str:
        """ Return a concatenation of all Ksnid-specific attributes """
        millivisun = "" if self.millivisun == 0 else str(self.millivisun)
        return (
            f"{self.einkunn};{self.malsnid};{self.malfraedi};"
            f"{millivisun};{self.birting};{self.beinkunn};"
            f"{self.bmalsnid};{self.bgildi};{self.aukafletta}"
        )

    @classmethod
    def from_string(cls: Type[_Ksnid], s: str) -> _Ksnid:
        """ Create a Ksnid instance from a CSV-format string,
            separated by semicolons """
        t = s.split(";")
        return cls.from_tuple(t)

    @classmethod
    def from_tuple(cls: Type[_Ksnid], t: Sequence[str]) -> _Ksnid:
        """ Create a Ksnid instance from a tuple of strings """
        m = cls()
        (
            m.ord,
            bin_id,
            m.ofl,
            m.hluti,
            einkunn,
            m.malsnid,
            m.malfraedi,
            millivisun,
            m.birting,
            m.bmynd,
            m.mark,
            beinkunn,
            m.bmalsnid,
            m.bgildi,
            m.aukafletta,
        ) = t
        m.bin_id = int(bin_id or "0")
        m.einkunn = int(einkunn)
        m.millivisun = int(millivisun or "0")
        m.beinkunn = int(beinkunn)
        return m

    def __hash__(self) -> int:
        """ Make Ksnid instances hashable, using their 'primary key' attributes """
        return (self.ord, self.bin_id, self.ofl, self.bmynd).__hash__()

    @classmethod
    def from_parameters(
        cls: Type[_Ksnid],
        ord: str,
        bin_id: int,
        ofl: str,
        hluti: str,
        form: str,
        mark: str,
        ksnid: str = KSNID_GREYNIR,
    ) -> _Ksnid:
        """ Create a Ksnid instance from the given parameters """
        m = cls()
        m.ord = ord
        m.bin_id = bin_id
        m.ofl = ofl
        m.hluti = hluti
        m.bmynd = form
        m.mark = mark
        einkunn: str
        millivisun: str
        beinkunn: str
        t: Sequence[str] = ksnid.split(";")
        (
            einkunn,
            m.malsnid,
            m.malfraedi,
            millivisun,
            m.birting,
            beinkunn,
            m.bmalsnid,
            m.bgildi,
            m.aukafletta,
        ) = t
        m.einkunn = int(einkunn)
        m.millivisun = int(millivisun or "0")
        m.beinkunn = int(beinkunn)
        return m

    @classmethod
    def make(
        cls: Type[_Ksnid],
        ord: str,
        bin_id: int,
        ofl: str,
        hluti: str,
        form: str,
        mark: str,
        copy_from: Optional["_Ksnid"] = None,
    ) -> _Ksnid:
        """ Create a Ksnid instance from the given parameters """
        m = cls.from_parameters(ord, bin_id, ofl, hluti, form, mark)
        if copy_from is not None:
            m.einkunn = copy_from.einkunn
            m.malsnid = copy_from.malsnid
            m.malfraedi = copy_from.malfraedi
            m.millivisun = copy_from.millivisun
            m.birting = copy_from.birting
            m.beinkunn = copy_from.beinkunn
            m.bmalsnid = copy_from.bmalsnid
            m.bgildi = copy_from.bgildi
            m.aukafletta = copy_from.aukafletta
        return m

    def to_bin_meaning(self) -> BinMeaning:
        """ Copy this instance to a BinMeaning instance """
        return BinMeaning(
            self.ord, self.bin_id, self.ofl, self.hluti, self.bmynd, self.mark
        )


class LFU_Cache(Generic[_K, _V]):

    """ Least-frequently-used (LFU) cache for word lookups.
        Based on a pattern by Raymond Hettinger
    """

    def __init__(self, maxsize: int = LFU_DEFAULT) -> None:
        # Mapping of keys to results
        self.cache: Dict[_K, _V] = {}
        # Times each key has been accessed
        self.use_count: Counter[_K] = Counter()
        self.maxsize = maxsize
        self.hits = self.misses = 0
        # The cache may be accessed in parallel by multiple threads
        self.lock = threading.Lock()

    def lookup(self, key: _K, func: Callable[[_K], _V]) -> _V:
        """ Lookup a key in the cache, calling func(key)
            to obtain the data if not already there """
        with self.lock:
            self.use_count[key] += 1
            # Get cache entry or compute if not found
            try:
                result = self.cache[key]
                self.hits += 1
            except KeyError:
                result = func(key)
                self.cache[key] = result
                self.misses += 1
                # Purge the 10% least frequently used cache entries
                if len(self.cache) > self.maxsize:
                    for key, _ in nsmallest(
                        self.maxsize // 10, self.use_count.items(), key=itemgetter(1)
                    ):
                        del self.cache[key], self.use_count[key]
            return result


class ConfigError(Exception):

    """ Exception class for configuration errors """

    def __init__(self, s: str) -> None:
        super().__init__(s)
        self.fname: Optional[str] = None
        self.line = 0

    def set_pos(self, fname: str, line: int) -> None:
        """ Set file name and line information, if not already set """
        if not self.fname:
            self.fname = fname
            self.line = line

    def __str__(self) -> str:
        """ Return a string representation of this exception """
        s = Exception.__str__(self)
        if not self.fname:
            return s
        return "File {0}, line {1}: {2}".format(self.fname, self.line, s)


class LineReader:

    """ Read lines from a text file, recognizing $include directives """

    def __init__(
        self,
        fname: str,
        *,
        package_name: Optional[str] = None,
        outer_fname: Optional[str] = None,
        outer_line: int = 0,
    ) -> None:
        self._fname = fname
        self._package_name = package_name
        self._line = 0
        self._inner_rdr: Optional[LineReader] = None
        self._outer_fname = outer_fname
        self._outer_line = outer_line

    def fname(self) -> str:
        """ The name of the file being read """
        return self._fname if self._inner_rdr is None else self._inner_rdr.fname()

    def line(self) -> int:
        """ The number of the current line within the file """
        return self._line if self._inner_rdr is None else self._inner_rdr.line()

    def lines(self) -> Iterator[str]:
        """ Generator yielding lines from a text file """
        self._line = 0
        try:
            if self._package_name:
                stream = resource_stream(self._package_name, self._fname)
            else:
                stream = open(self._fname, "rb")
            with stream as inp:
                # Read config file line-by-line from the package resources
                accumulator = ""
                for b in inp:
                    # We get byte strings; convert from utf-8 to Python strings
                    s = b.decode("utf-8")
                    self._line += 1
                    if s.rstrip().endswith("\\"):
                        # Backslash at end of line: continuation in next line
                        accumulator += s.strip()[:-1]
                        continue
                    if accumulator:
                        # Add accumulated text from preceding
                        # backslash-terminated lines, but drop leading whitespace
                        s = accumulator + s.lstrip()
                        accumulator = ""
                    # Check for include directive: $include filename.txt
                    if s.startswith("$") and s.lower().startswith("$include "):
                        iname = s.split(maxsplit=1)[1].strip()
                        # Do some path magic to allow the included path
                        # to be relative to the current file path, or a
                        # fresh (absolute) path by itself
                        head, _ = os.path.split(self._fname)
                        iname = os.path.join(head, iname)
                        rdr = self._inner_rdr = LineReader(
                            iname,
                            package_name=self._package_name,
                            outer_fname=self._fname,
                            outer_line=self._line,
                        )
                        yield from rdr.lines()
                        self._inner_rdr = None
                    else:
                        yield s
                if accumulator:
                    # Catch corner case where last line of file ends with a backslash
                    yield accumulator
        except (IOError, OSError):
            if self._outer_fname:
                # This is an include file within an outer config file
                c = ConfigError(
                    "Error while opening or reading include file '{0}'".format(
                        self._fname
                    )
                )
                c.set_pos(self._outer_fname, self._outer_line)
            else:
                # This is an outermost config file
                c = ConfigError(
                    "Error while opening or reading config file '{0}'".format(
                        self._fname
                    )
                )
            raise c
