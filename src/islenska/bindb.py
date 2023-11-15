"""

    BinPackage

    BIN database access module

    Copyright © 2023 Miðeind ehf.

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

    This module encapsulates access to the BIN (Beygingarlýsing íslensks nútímamáls)
    database of word forms, including lookup of abbreviations and basic strategies
    for handling missing words.

    The database is assumed to be packed into a compressed binary file,
    which is wrapped inside the bincompress.py module.

    Word lookups are cached in Least Frequently Used (LFU) caches.

"""

from typing import (
    Any,
    Optional,
    Callable,
    List,
    Set,
    Tuple,
    Iterable,
    Dict,
    Union,
    cast,
    TypeVar,
)
from typing_extensions import Protocol

import re
from functools import lru_cache
from pathlib import Path

from .basics import (
    InflectionFilter,
    BinEntry,
    Ksnid,
    LFU_Cache,
    BinEntryTuple,
    make_bin_entry,
)
from .settings import (
    Settings,
    AdjectiveTemplate,
    StemPreferences,
    NounPreferences,
    BinErrata,
    BinDeletions,
)
from .dawgdictionary import Wordbase
from .bincompress import BinCompressed


# Type definitions

# Type variable allowing BinEntry and Ksnid for its value
_T = TypeVar("_T", BinEntry, Ksnid)

ResultTuple = Tuple[str, List[_T]]

# A constructor that constructs either BinEntry or Ksnid instances,
# optionally copying data from an existing instance
EntryCtor = Callable[[str, int, str, str, str, str, Optional[_T]], _T]

TupleLookupFunc = Callable[[str], ResultTuple[_T]]
EntryFilterFunc = Callable[[Iterable[_T]], List[_T]]

BinFilterFunc = EntryFilterFunc[BinEntry]
BinEntryList = List[BinEntry]
BinEntryIterable = Iterable[BinEntry]
KsnidList = List[Ksnid]
KsnidIterable = Iterable[Ksnid]


class LookupFunc(Protocol[_T]):
    def __call__(self, key: str, compound: bool = False) -> List[_T]:
        ...


# Annotate the case-casting function signature via a callback protocol
# See https://www.python.org/dev/peps/pep-0544/#callback-protocols
class CaseFunc(Protocol):
    def __call__(self, w: str, **options: Any) -> BinEntryList:
        ...


# Size of LRU/LFU caches for word lookups
CACHE_SIZE = 512
# Cache size for most common lookup function
# (entries matching a particular word form)
CACHE_SIZE_MEANINGS = 4096

# The set of word subcategories (hluti) for person names
# (i.e. first names or complete names)
PERSON_NAME_FL = frozenset(("ism", "nafn", "gæl", "erm"))

# Adjective endings
_ADJECTIVE_TEST = "leg"  # Check for adjective if word contains 'leg'

# Word categories that are allowed to appear capitalized in the middle of sentences,
# as a result of compound word construction
_NOUNS = frozenset(("kk", "kvk", "hk"))

_OPEN_CATS = frozenset(("so", "kk", "hk", "kvk", "lo"))  # Open word categories

# A dictionary of functions, one for each word category, that return
# True for declension (mark) strings of canonical/lemma forms
_LEMMA_FILTERS: Dict[str, InflectionFilter] = {
    # Nouns: Nominative, singular
    "kk": lambda b: b == "NFET",
    "kvk": lambda b: b == "NFET",
    "hk": lambda b: b == "NFET",
    # Pronouns: Masculine, nominative, singular
    "fn": lambda b: b == "KK-NFET" or b == "KK_NFET" or b == "fn_KK_NFET",
    # Personal pronouns: Nominative, singular
    "pfn": lambda b: b == "NFET",
    # Definite article: Masculine, nominative, singular
    "gr": lambda b: b == "KK-NFET" or b == "KK_NFET",
    # Verbs: infinitive
    "so": lambda b: b == "GM-NH",
    # Adjectives: Masculine, singular, first degree, strong declension
    "lo": lambda b: b == "FSB-KK-NFET" or b == "KK-NFET",
    # Number words: Masculine, nominative case; or no inflection
    "to": lambda b: b.startswith("KK_NF") or b == "OBEYGJANLEGT",
}

# Word meanings that are marked in BÍN as obsolete, rare, errors or old;
# these are sorted last in the lookup functions
_LOW_PRIORITY_FORMS = frozenset(("URE", "SJALD", "VILLA", "GAM"))


class Bin:

    """Encapsulates the BÍN database of word forms"""

    # Singleton instance of the compressed, memory-mapped BÍN
    _bc: Optional[BinCompressed] = None

    # Singleton LFU cache for word lookup
    _ksnid_cache: LFU_Cache[str, KsnidList] = LFU_Cache(maxsize=CACHE_SIZE_MEANINGS)

    def __init__(self, **options: bool) -> None:
        """Initialize BIN database wrapper instance"""
        if self._bc is None:
            self.__class__._bc = BinCompressed()
        Settings.read(str(Path("config", "BinPackage.conf")))
        # Set option flags
        self._add_negation = options.pop("add_negation", True)
        self._add_legur = options.pop("add_legur", True)
        self._add_compounds = options.pop("add_compounds", True)
        self._replace_z = options.pop("replace_z", True)
        if options.pop("only_bin", False):
            # If only_bin is set, disable all additions/modifications
            self._add_negation = False
            self._add_legur = False
            self._add_compounds = False
            self._replace_z = False
        if options:
            raise ValueError(
                "Option(s) not understood: {0}".format(" ,".join(options.keys()))
            )

    @classmethod
    def cleanup(cls) -> None:
        """Close singleton instance, if any"""
        if cls._bc is not None:
            cls._bc.close()
            cls._bc = None

    @staticmethod
    def _prefix_meanings(
        mlist: Iterable[_T],
        prefix: str,
        ctor: EntryCtor[_T],
        *,
        insert_hyphen: bool = True,
        uppercase_suffix: bool = False
    ) -> List[_T]:
        """Return a meaning list with a prefix added to the
        ord and bmynd attributes of each entry in the list.
        If insert_hyphen is True, we insert a hyphen between
        the prefix and the suffix, both in the ord and in
        the bmynd fields. If uppercase is additionally True,
        we uppercase the suffix."""
        if not prefix:
            # No prefix: nothing to do
            return list(mlist)
        concat: Callable[[str], str]
        if insert_hyphen:
            if uppercase_suffix:
                concat = lambda w: prefix + "-" + w.capitalize()
            else:
                concat = lambda w: prefix + "-" + w
        else:
            concat = lambda w: prefix + w
        # Note that the compound words created have 'bin_id' set to 0, but they
        # retain other information from the the suffix (base) word.
        # This includes the additional ksnid fields, and notably 'birting',
        # which is not set to 'G' as for synthetic word forms
        return [
            ctor(concat(r.ord), 0, r.ofl, r.hluti, concat(r.bmynd), r.mark, r)
            for r in mlist
        ]

    def _filter_meanings(self, mtlist: Iterable[BinEntryTuple]) -> BinEntryList:
        """Default mapping function to make BinEntry instances
        from EntryTuples coming from BinCompressed"""
        assert self._bc is not None
        max_utg = self._bc.begin_greynir_utg
        return [
            BinEntry._make(mt)
            for mt in mtlist
            # Only return entries with bin_id numbers below the Greynir-specific mark,
            # i.e. skip entries that are Greynir-specific
            if mt[1] < max_utg
        ]

    def _filter_ksnid(self, klist: Iterable[Ksnid]) -> KsnidList:
        """Default mapping function to make Ksnid instances
        from EntryTuples coming from BinCompressed"""
        assert self._bc is not None
        max_utg = self._bc.begin_greynir_utg
        m = [
            k
            for k in klist
            # Only return entries with bin_id numbers below the Greynir-specific mark,
            # and that don't have 'birting' set to 'G',
            # i.e. skip entries that are Greynir-specific.
            # 'birting' equal to 'S' means a suffix (coming from ord.suffix.csv).
            if (k.bin_id < max_utg and k.birting != "G") or k.birting == "S"
        ]
        # Sort the result so that words with a non-normal correctness grade
        # (i.e. not 1) are returned after those with a normal grade
        m.sort(key=lambda k: int(k.einkunn != 1) + int(k.beinkunn != 1))
        return m

    def _ksnid_lookup(self, w: str) -> KsnidList:
        """Low-level fetch of the BIN entries that match a given word.
        The output of this function is cached."""
        # Route the lookup request to the compressed binary file
        assert self._bc is not None
        mtlist = self._bc.lookup_ksnid(w)
        # If the lookup doesn't yield any results, [] is returned.
        # Otherwise, map the query results to a BinEntry tuple
        return self._filter_ksnid(mtlist) if mtlist else []

    def _ksnid_cache_lookup(self, key: str, compound: bool = False) -> KsnidList:
        """Attempt to lookup a word in the cache, calling
        self.ksnid_lookup() on a cache miss"""
        klist = self._ksnid_cache.lookup(key, self._ksnid_lookup)
        # If we're looking for compound suffixes (compound=True), we
        # allow items where birting == 'S' (coming from ord.suffix.csv)
        return [k for k in klist if compound or k.birting != "S"]

    def _ksnid_lookup_id(self, bin_id: int) -> KsnidList:
        """Low-level fetch of the BIN entries that have the given bin_id"""
        # Route the lookup request to the compressed binary file
        assert self._bc is not None
        mtlist = self._bc.lookup_id(bin_id)
        # If the lookup doesn't yield any results, [] is returned.
        # Otherwise, map the query results to a Ksnid tuple
        return self._filter_ksnid(mtlist) if mtlist else []

    def _meanings_cache_lookup(self, key: str, compound: bool = False) -> BinEntryList:
        """Attempt to lookup a word in the cache,
        returning a list of BinEntry instances"""
        klist = self._ksnid_cache_lookup(key, compound=compound)
        # Convert the cached ksnid list to a list of BinEntry (SHsnid) tuples
        return [k.to_bin_entry() for k in klist]

    def _compound_meanings(
        self,
        w: str,
        lower_w: str,
        at_sentence_start: bool,
        lookup_func: LookupFunc[_T],
        ctor: EntryCtor[_T],
    ) -> ResultTuple[_T]:
        """Return a list of matching entries for this word,
        when interpreted as a compound word"""
        m: List[_T]
        if " " in w:
            # The word is a multi-word compound, such as
            # 'félags- og barnamálaráðherra': Look at the last part only
            prefix, suffix = w.rsplit(" ", maxsplit=1)
            w_suffix, m = self._compound_meanings(
                suffix, suffix.lower(), False, lookup_func, ctor
            )
            if not m:
                return w, m
            uppercase_suffix = suffix[0].isupper() and suffix[1:].islower()
            w = prefix + " " + w_suffix
            m = self._prefix_meanings(
                m,
                prefix + " ",
                ctor,
                insert_hyphen=False,
                uppercase_suffix=uppercase_suffix,
            )
            return w, m
        if "-" in w and not w.endswith("-"):
            # The word already contains a hyphen: respect that split and
            # look at the suffix only
            prefix, suffix = w.rsplit("-", maxsplit=1)
            _, m = self._compound_meanings(
                suffix, suffix.lower(), False, lookup_func, ctor
            )
            if not m:
                return w, m
            # For words such as 'Ytri-Hnaus', retain the uppercasing of the suffix
            uppercase_suffix = suffix[0].isupper() and suffix[1:].islower()
            w = prefix + "-" + suffix
            m = self._prefix_meanings(
                m, prefix, ctor, uppercase_suffix=uppercase_suffix
            )
            return w, m
        return_w = w
        cw = Wordbase.slice_compound_word(w)
        if len(cw) < 2 and lower_w != w:
            # If not able to slice in original case, try lower case
            cw = Wordbase.slice_compound_word(lower_w)
            if len(cw) >= 2:
                # Success
                return_w = lower_w
        if not cw:
            # No way to find a compound meaning: give up
            return w, []
        # This looks like a compound word:
        # use the meaning of its last part
        prefix = "-".join(cw[0:-1])
        # Lookup the entries that match the last part, setting
        # the compound flag if we actually have a compound word
        m = lookup_func(cw[-1], compound=bool(prefix))
        if not m:
            return return_w, []
        if lower_w != w and not at_sentence_start:
            # If this is an uppercase word in the middle of a
            # sentence, allow only nouns as possible interpretations
            # (it wouldn't be correct to capitalize verbs, adjectives, etc.)
            m = self.nouns(m)
        else:
            # Only allows entries from open word categories
            # (nouns, verbs, adjectives, adverbs)
            m = self.open_cats(m)
        # Add the prefix to the remaining word lemmas
        return return_w, self._prefix_meanings(m, prefix, ctor)

    def _lookup(
        self,
        w: str,
        at_sentence_start: bool,
        auto_uppercase: bool,
        lookup_func: LookupFunc[_T],
        ctor: EntryCtor[_T],
    ) -> ResultTuple[_T]:
        """Lookup a simple or compound word in the database and
        return its meaning(s). This function checks for abbreviations,
        upper/lower case variations, etc."""

        # Start with a straightforward, cached lookup of the word as-is
        lower_w = w
        m: List[_T] = lookup_func(w)

        if auto_uppercase and w.islower():
            # Lowercase word:
            # If auto_uppercase is True, we attempt to find an
            # uppercase variant of it
            if len(w) == 1 and not m:
                # Special case for single letter words that are not found in BÍN:
                # treat them as uppercase abbreviations
                # (probably middle names)
                w = w.upper() + "."
            else:
                # Check whether this word has an uppercase form in the database
                # capitalize() converts "ABC" and "abc" to "Abc"
                w_upper = w.capitalize()
                m_upper = lookup_func(w_upper)
                if m_upper:
                    # Uppercase form(s) found
                    w = w_upper
                    if m:
                        # ...in addition to lowercase ones
                        # Note that the uppercase forms are put in front of the
                        # resulting list. This is intentional, inter alia so that
                        # person names are recognized as such in bintokenizer.py
                        # in GreynirPackage.
                        m = m_upper + m
                    else:
                        # No lowercase forms: use the uppercase form and entries
                        m = m_upper
                    at_sentence_start = False  # No need for special case here

        if at_sentence_start or not m:
            # No matching entries found in the database, or we're at sentence start
            # Try a lowercase version of the word, if different
            lower_w = w.lower()
            if lower_w != w:
                # Do another lookup, this time for lowercase only
                if not m:
                    # This is a word that contains uppercase letters
                    # and was not found in BÍN in its original form:
                    # try the all-lowercase version
                    m = lookup_func(lower_w)
                    if m:
                        # Only lower case entries, so we modify w
                        w = lower_w
                else:
                    # Be careful to make a new list here, not extend m
                    # in place, as it may be a cached value from the LFU
                    # cache and we don't want to mess the original up
                    # Note: the lowercase lookup result is intentionally put
                    # in front of the uppercase one, as we want go give
                    # 'regular' lowercase entries priority when matching
                    # tokens to terminals. For example, 'Maður' and 'maður'
                    # are both in BÍN, the former as a place name ('örn'),
                    # but we want to give the regular, common lower case form
                    # priority.
                    m = lookup_func(lower_w) + m
        if m:
            # Most common path out of this function
            return w, m

        if not m and self._add_legur and _ADJECTIVE_TEST in lower_w:
            # Not found: Check whether this might be an adjective
            # ending in 'legur'/'leg'/'legt'/'legir'/'legar' etc.
            llw = len(lower_w)
            m = []
            for aend, mark in AdjectiveTemplate.ENDINGS:
                if lower_w.endswith(aend) and llw > len(aend):
                    prefix = lower_w[0 : llw - len(aend)]
                    # Construct an adjective descriptor
                    m.append(
                        ctor(prefix + "legur", 0, "lo", "alm", lower_w, mark, None)
                    )
            if lower_w.endswith("lega") and llw > 4:
                # For words ending with "lega", add a possible adverb meaning
                m.append(ctor(lower_w, 0, "ao", "alm", lower_w, "OBEYGJANLEGT", None))

        if not m and self._add_compounds:
            # Still nothing: check compound words
            w, m = self._compound_meanings(
                w, lower_w, at_sentence_start, lookup_func, ctor
            )

        if not m and self._add_negation and lower_w.startswith("ó"):
            # Check whether an adjective without the 'ó' prefix is found in BÍN
            # (i.e. create 'óhefðbundinn' from 'hefðbundinn')
            suffix = lower_w[1:]
            if suffix:
                om = lookup_func(suffix)
                if om:
                    m = [
                        ctor(
                            "ó" + r.ord,
                            r.bin_id,
                            r.ofl,
                            r.hluti,
                            "ó" + r.bmynd,
                            r.mark,
                            r,
                        )
                        for r in om
                        if r.ofl == "lo"
                    ]

        if not m and self._replace_z and "z" in w:
            # Special case: the word contains a 'z' and may be using
            # older Icelandic spelling ('lízt', 'íslenzk'). Try to assign
            # a meaning by substituting an 's' instead, or 'st' instead of
            # 'tzt'. Call ourselves recursively to do this.
            # Note: We don't do this for uppercase 'Z' because those are
            # much more likely to indicate a person or entity name
            normal_w, m = self._lookup(
                w.replace("tzt", "st").replace("z", "s"),
                at_sentence_start,
                auto_uppercase,
                lookup_func,
                ctor,
            )
            if m:
                # Return the word form that was actually found
                w = normal_w

        if auto_uppercase and not m and w.islower():
            # If still no meaning found and we're auto-uppercasing,
            # convert this to upper case (probably an entity name)
            w = w.capitalize()

        return w, m

    @staticmethod
    def _cast_to_case(
        w: str,
        lookup_func: TupleLookupFunc[BinEntry],
        case_func: CaseFunc,
        filter_func: Optional[BinFilterFunc],
    ) -> str:
        """Return a word after casting it from nominative to another case,
        as returned by the case_func"""

        def score(m: BinEntry) -> int:
            """Return a score for a noun word form, based on the
            [noun_preferences] section in Prefs.conf"""
            sc = NounPreferences.DICT.get(m.bmynd.split("-")[-1])
            return 0 if sc is None else sc.get(m.ofl, 0)

        mm: BinEntryList

        # Begin by looking up the word form
        _, mm = lookup_func(w)
        if not mm:
            # Unknown word form: leave it as-is
            return w
        # Check whether this is (or might be) an adjective
        m_word = next((m for m in mm if m.ofl == "lo" and "NF" in m.mark), None)
        if m_word is not None:
            # This is an adjective: find its forms
            # in the requested case ("Gul gata", "Stjáni blái")
            mm = case_func(m_word.bmynd, cat="lo", lemma=m_word.ord)
            if "VB" in m_word.mark:
                mm = [m for m in mm if "VB" in m.mark]
            elif "SB" in m_word.mark:
                mm = [m for m in mm if "SB" in m.mark]
        else:
            # Sort the matching entries in reverse order by score
            mm = sorted(mm, key=score, reverse=True)
            m_word = next(
                (
                    m
                    for m in mm
                    if m.ofl in {"kk", "kvk", "hk", "fn", "pfn", "to", "gr"}
                    and "NF" in m.mark
                ),
                None,
            )
            if m_word is None:
                # Not a case-inflectable word that we are interested in: leave it
                return w
            if "-" in m_word.bmynd and "-" not in w:
                # Composite word (and not something like 'Vestur-Þýskaland', which
                # is in BÍN including the hyphen): use the meaning of its last part
                cw = m_word.bmynd.split("-")
                prefix = "".join(cw[0:-1])
                # No need to think about upper or lower case here,
                # since the last part of a compound word is always in BÍN as-is
                mm = case_func(cw[-1], cat=m_word.ofl, lemma=m_word.ord.split("-")[-1])
                # Add the prefix to the remaining word lemmas
                mm = Bin._prefix_meanings(
                    mm, prefix, make_bin_entry, insert_hyphen=False
                )
            else:
                mm = case_func(w, cat=m_word.ofl, lemma=m_word.ord)
                if not mm and w[0].isupper() and not w.isupper():
                    # Did not find an uppercase version: try a lowercase one
                    mm = case_func(w.lower(), cat=m_word.ofl, lemma=m_word.ord)
        if mm:
            # Likely successful: return the word after casting it
            if "ET" in m_word.mark:
                # Restrict to singular
                mm = [m for m in mm if "ET" in m.mark]
            elif "FT" in m_word.mark:
                # Restrict to plural
                mm = [m for m in mm if "FT" in m.mark]
            # Apply further filtering, if desired
            if filter_func is not None:
                mm = filter_func(mm)
            if mm:
                o = mm[0].bmynd
                # Imitate the case of the original word
                if w.isupper():
                    o = o.upper()
                elif w[0].isupper() and not o[0].isupper():
                    o = o[0].upper() + o[1:]
                return o

        # No case casting could be done: return the original word
        return w

    def __contains__(self, w: str) -> bool:
        """Returns True if the given word form is found in BÍN"""
        # Note that this does not fall back to the word compounder
        assert self._bc is not None
        return self._bc.contains(w)

    def contains(self, w: str) -> bool:
        """Returns True if the given word form is found in BÍN"""
        # Note that this does not fall back to the word compounder
        assert self._bc is not None
        return self._bc.contains(w)

    @staticmethod
    def open_cats(mlist: Iterable[_T]) -> List[_T]:
        """Return a list of entries filtered down to
        open (extensible) word categories"""
        return [mm for mm in mlist if mm.ofl in _OPEN_CATS]

    @staticmethod
    def nouns(mlist: Iterable[_T]) -> List[_T]:
        """Return a list of entries filtered down to noun categories (kk, kvk, hk)"""
        return [mm for mm in mlist if mm.ofl in _NOUNS]

    def lookup(
        self, w: str, at_sentence_start: bool = False, auto_uppercase: bool = False
    ) -> ResultTuple[BinEntry]:
        """Given a word form, look up all matching entries.
        This is the main query function of the Bin class."""
        return self._lookup(
            w,
            at_sentence_start,
            auto_uppercase,
            self._meanings_cache_lookup,
            make_bin_entry,
        )

    def lookup_ksnid(
        self, w: str, at_sentence_start: bool = False, auto_uppercase: bool = False
    ) -> ResultTuple[Ksnid]:
        """Given a word form, look up all matching entries in Ksnid form."""
        return self._lookup(
            w,
            at_sentence_start,
            auto_uppercase,
            self._ksnid_cache_lookup,
            Ksnid.make,
        )

    def lookup_id(self, bin_id: int) -> KsnidList:
        """Given a BÍN id, return all entries having that id in Ksnid form."""
        return self._ksnid_lookup_id(bin_id)

    def lookup_cats(self, w: str, at_sentence_start: bool = False) -> Set[str]:
        """Given a word form, look up all its possible categories
        ('kk', 'kvk', 'hk', 'so', 'lo', ...)."""
        _, m = self._lookup(
            w,
            at_sentence_start,
            False,
            self._ksnid_cache_lookup,
            Ksnid.make,
        )
        return set(mm.ofl for mm in m)

    def lookup_lemmas_and_cats(
        self, w: str, at_sentence_start: bool = False
    ) -> Set[Tuple[str, str]]:
        """Given a word form, look up all its possible lemmas and categories"""
        _, m = self._lookup(
            w,
            at_sentence_start,
            False,
            self._ksnid_cache_lookup,
            Ksnid.make,
        )
        return set((mm.ord, mm.ofl) for mm in m)

    def lookup_forms(self, lemma: str, cat: str, case: str) -> BinEntryList:
        """Lookup all word forms in the indicated case, of the given lemma.
        This is mainly used to retrieve inflection forms of nouns, where
        we want to retrieve singular and plural, definite and indefinite
        forms in particular cases. Note that lookup_variants() below is
        a more flexible alternative to this function."""
        assert self._bc is not None
        mset = self._bc.lookup_case(
            lemma,
            case.upper().replace("GR", "gr"),
            lemma=lemma,
            cat=cat,
            all_forms=True,
        )
        return self._filter_meanings(mset)

    def lookup_variants(
        self,
        w: str,
        cat: str,
        to_inflection: Union[str, Iterable[str]],
        *,
        lemma: Optional[str] = None,
        bin_id: Optional[int] = None,
        inflection_filter: Optional[InflectionFilter] = None
    ) -> KsnidList:
        """Lookup grammatical variants of the given word with the
        indicated category, converting PoS tags to the one(s) given
        in the to_inflection parameter."""

        assert self._bc is not None
        bc: BinCompressed = self._bc

        def variant_lookup(key: str, compound: bool = False) -> KsnidList:
            """Create a closure function to send into _lookup(),
            obtaining the requested inflection variants correctly,
            also for composite words"""
            mlist = bc.lookup_variants(
                key,
                cat,
                to_inflection,
                lemma,
                None if compound else bin_id,
                inflection_filter,
            )
            klist = self._filter_ksnid(mlist)
            return [k for k in klist if compound or k.birting != "S"]

        _, m = self._lookup(w, False, False, variant_lookup, Ksnid.make)
        return m

    def lookup_lemmas(self, lemma: str) -> ResultTuple[BinEntry]:
        """Given a string, look up all entries matching it as a lemma"""
        # Note: we consider middle voice infinitive verbs to be lemmas,
        # i.e. 'eignast' is recognized as a lemma as well as 'eigna'.
        # This is done for consistency, as some middle voice verbs have
        # their own separate lemmas in BÍN, such as 'ábyrgjast'.
        final_w, entries = self.lookup(lemma)

        def match(m: BinEntry) -> bool:
            """Return True for entries that are canonical as lemmas"""
            if m.ofl == "so" and m.mark == "MM-NH":
                # This is a middle voice verb infinitive form
                # ('eignast', 'komast'): accept it as a lemma
                return True
            if m.ord.replace("-", "") != final_w:
                # This lemma does not agree with the passed-in word
                return False
            # Do a check of the canonical lemma inflection forms
            return _LEMMA_FILTERS.get(m.ofl, lambda _: True)(m.mark)

        return final_w, [m for m in entries if match(m)]

    # Backwards compatibility only
    lemma_meanings = lookup_lemmas

    @lru_cache(maxsize=CACHE_SIZE)
    def lookup_raw_nominative(self, w: str) -> BinEntryList:
        """Return a set of BinEntry tuples for all word forms in nominative case.
        The set is unfiltered except for the presence of 'NF' in the mark
        field. For new code, lookup_nominative() is likely to be a
        more efficient choice."""
        assert self._bc is not None
        return self._filter_meanings(self._bc.raw_nominative(w))

    def lookup_nominative(self, w: str, **options: Any) -> BinEntryList:
        """Return BinEntry tuples for all word forms in nominative
        case for all { kk, kvk, hk, lo } category lemmas of the given word"""
        assert self._bc is not None
        return self._filter_meanings(self._bc.nominative(w, **options))

    def lookup_accusative(self, w: str, **options: Any) -> BinEntryList:
        """Return BinEntry tuples for all word forms in accusative
        case for all { kk, kvk, hk, lo } category lemmas of the given word"""
        assert self._bc is not None
        return self._filter_meanings(self._bc.accusative(w, **options))

    def lookup_dative(self, w: str, **options: Any) -> BinEntryList:
        """Return BinEntry tuples for all word forms in dative
        case for all { kk, kvk, hk, lo } category lemmas of the given word"""
        assert self._bc is not None
        return self._filter_meanings(self._bc.dative(w, **options))

    def lookup_genitive(self, w: str, **options: Any) -> BinEntryList:
        """Return BinEntry tuples for all word forms in genitive
        case for all { kk, kvk, hk, lo } category lemmas of the given word"""
        assert self._bc is not None
        return self._filter_meanings(self._bc.genitive(w, **options))

    def cast_to_accusative(
        self, w: str, *, filter_func: Optional[BinFilterFunc] = None
    ) -> str:
        """Cast a word from nominative to accusative case, or return it
        unchanged if it is not inflectable by case."""
        # Note that since this function has no context, the conversion is
        # by necessity simplistic; for instance it does not know whether
        # an adjective is being used with an indefinite or definite noun,
        # or whether a word such as 'við' is actually a preposition.
        return self._cast_to_case(
            w,
            self.lookup,
            self.lookup_accusative,
            filter_func=filter_func,
        )

    def cast_to_dative(
        self, w: str, *, filter_func: Optional[BinFilterFunc] = None
    ) -> str:
        """Cast a word from nominative to dative case, or return it
        unchanged if it is not inflectable by case."""
        # Note that since this function has no context, the conversion is
        # by necessity simplistic; for instance it does not know whether
        # an adjective is being used with an indefinite or definite noun,
        # or whether a word such as 'við' is actually a preposition.
        return self._cast_to_case(
            w,
            self.lookup,
            self.lookup_dative,
            filter_func=filter_func,
        )

    def cast_to_genitive(
        self, w: str, *, filter_func: Optional[BinFilterFunc] = None
    ) -> str:
        """Cast a word from nominative to genitive case, or return it
        unchanged if it is not inflectable by case."""
        # Note that since this function has no context, the conversion is
        # by necessity simplistic; for instance it does not know whether
        # an adjective is being used with an indefinite or definite noun,
        # or whether a word such as 'við' is actually a preposition.
        return self._cast_to_case(
            w,
            self.lookup,
            self.lookup_genitive,
            filter_func=filter_func,
        )

    def get_compound(
        self, w: str, at_sentence_start: bool = False
    ) -> ResultTuple[BinEntry]:
        """Lookup a word in the database and return its meaning(s),
        prioritizing returning its compound structure."""

        w, m = self._compound_meanings(
            w, w.lower(), at_sentence_start, self._meanings_cache_lookup, make_bin_entry
        )

        return w, m


class GreynirBin(Bin):

    """Overridden class for use by GreynirPackage, including
    a compatibility layer that converts a couple of data
    features to be compliant with an earlier BÍN scheme"""

    # Maintain a separate cache from the Bin class,
    # in case both classes are used concurrently
    _ksnid_cache: LFU_Cache[str, KsnidList] = LFU_Cache(maxsize=CACHE_SIZE_MEANINGS)

    # A dictionary of BÍN errata, loaded from BinErrata.conf
    bin_errata: Optional[Dict[Tuple[str, str], str]] = None
    # A set of BÍN deletions, loaded from BinErrata.conf
    bin_deletions: Set[Tuple[str, str, str]] = set()

    def __init__(self) -> None:
        super().__init__()
        if GreynirBin.bin_errata is None:
            config_file = str(Path("config", "BinErrata.conf"))
            Settings.read(config_file, force=True)
            GreynirBin.bin_deletions = BinDeletions.SET
            GreynirBin.bin_errata = BinErrata.DICT

    def _filter_meanings(self, mtlist: Iterable[BinEntryTuple]) -> BinEntryList:
        """Override the default straight-through translation of
        a BinEntryTuple from BinCompressed over to a BinEntry
        returned from Bin/GreynirBin"""
        result: BinEntryList = []
        for mt in mtlist:
            if (mt[0], mt[2], mt[3]) in self.bin_deletions:
                # The (ord, ofl, hluti) combination is marked
                # for deletion in BinErrata.conf:
                # This meaning is not visible to Greynir
                continue
            m: List[Union[str, int]] = list(mt)
            # ml: [0]=ord, [1]=bin_id, [2]=ofl, [3]=hluti, [4]=bmynd, [5]=mark
            # Convert uninflectable indicator to "-" for compatibility
            if mt[5] == "OBEYGJANLEGT":
                m[5] = "-"
                if mt[2] == "to":
                    # Convert uninflectable number words to "töl" for compatibility
                    m[2] = "töl"
            # Convert "afn" (reflexive pronoun) to "abfn" for compatibility
            if mt[2] == "afn":
                m[2] = "abfn"
            # Convert "rt" (ordinal number) to "lo" (adjective)
            # for compatibility
            elif mt[2] == "rt":
                m[2] = "lo"
            # Apply a fix if we have one for this particular (lemma, ofl) combination
            assert self.bin_errata is not None
            m[3] = self.bin_errata.get((mt[0], cast(str, m[2])), mt[3])
            result.append(BinEntry._make(m))
        return result

    def _filter_ksnid(self, klist: Iterable[Ksnid]) -> KsnidList:
        """Overridden mapping function to adapt Ksnid instances
        for compatibility with previous versions of BÍN, as used in Greynir"""
        result: KsnidList = []
        for k in klist:
            if (k.ord, k.ofl, k.hluti) in self.bin_deletions:
                # The (ord, ofl, hluti) combination is marked
                # for deletion in BinErrata.conf:
                # This meaning is not visible to Greynir
                continue
            # Convert uninflectable indicator to "-" for compatibility
            if k.mark == "OBEYGJANLEGT":
                k.mark = "-"
                if k.ofl == "to":
                    # Convert uninflectable number words to "töl" for compatibility
                    k.ofl = "töl"
            # Convert "afn" (reflexive pronoun) to "abfn" for compatibility
            if k.ofl == "afn":
                k.ofl = "abfn"
            # Convert "rt" (ordinal number) to "lo" (adjective)
            # for compatibility
            elif k.ofl == "rt":
                k.ofl = "lo"
            # Apply a fix if we have one for this particular (lemma, ofl) combination
            assert self.bin_errata is not None
            k.hluti = self.bin_errata.get((k.ord, k.ofl), k.hluti)
            result.append(k)
        return result

    @staticmethod
    def _priority(m: Ksnid) -> int:
        """Return a relative priority for the word meaning tuple
        in m. A lower number means more priority, a higher number
        means less priority. The final list of meanings is sorted
        so that higher-priority meanings occur before lower-priority ones."""
        prio = (
            # +1 if bin_id is 0 (constructed word form, not originally in BÍN)
            # +1 if einkunn (grammatical correctness grade) is not 1 (normal)
            # +1 if malsnid (lemma semantic category) is a low priority category
            # +1 if bmalsnid (word semantic category) is a low priority category
            int(m.bin_id == 0)
            + int(m.einkunn != 1)
            + int(m.malsnid in _LOW_PRIORITY_FORMS)
            + int(m.bmalsnid in _LOW_PRIORITY_FORMS)
        )
        if m.ofl != "so":
            # Not a verb: Prioritize forms by general acceptability only
            return prio
        # Verb priorities
        # Order "VH" verbs (viðtengingarháttur) after other forms
        # Also order past tense ("ÞT") after present tense
        # plural after singular and 2p after 3p
        prio += 4 if "VH" in m.mark else 0
        prio += 2 if "ÞT" in m.mark else 0
        prio += 1 if "FT" in m.mark else 0
        prio += 1 if "2P" in m.mark else 0
        return prio

    def _ksnid_lookup(self, w: str) -> KsnidList:
        """Override the Bin _ksnid_lookup() function to order the
        returned entries by priority. The output of this
        function is cached."""
        m = super()._ksnid_lookup(w)
        if not m:
            return []
        stem_prefs = StemPreferences.DICT.get(w)
        if stem_prefs is not None:
            # We have a preferred lemma for this word form:
            # cut off entries based on other lemmas
            worse, _ = stem_prefs
            m = [mm for mm in m if mm.ord not in worse]

        # Order the returned entries by priority, so that the most
        # common/likely ones are first in the list and thus
        # matched more readily than the less common ones
        m.sort(key=self._priority)
        return m


class Orð:

    """Encapsulates an Icelandic word along with its matching vocabulary entries,
    allowing easy generation of inflectional variants via a __format__() method"""

    _b: Optional[GreynirBin] = None

    def __init__(
        self,
        word: str,
        category: Union[None, str, Iterable[str]] = None,
        at_sentence_start: bool = False,
    ):
        if self._b is None:
            Orð._b = GreynirBin()
        assert self._b is not None
        self._word = word
        self._key, self._m = self._b.lookup_ksnid(word, at_sentence_start)
        if category is not None:
            if category == "no":
                # Any noun
                cat_set = frozenset(("kk", "kvk", "hk"))
            else:
                cat_set = frozenset(
                    [category] if isinstance(category, str) else category
                )
            self._m = [mm for mm in self._m if mm.ofl in cat_set]
        self._ksnid: Optional[Ksnid] = self._m[0] if self._m else None

    @classmethod
    def from_ksnid(cls, ksnid: Ksnid) -> "Orð":
        """Hacky constructor to create an Orð instance from a Ksnid instance"""
        o = cls(ksnid.bmynd, ksnid.ofl)
        o._m = [ksnid]
        o._ksnid = ksnid
        return o

    @property
    def word(self) -> str:
        """Returns the original word that was passed to the constructor"""
        return self._word

    @property
    def key(self) -> str:
        """Returns the BÍN lookup key"""
        return self._key

    @property
    def entries(self) -> KsnidList:
        """Return a list of matching entries, according to BÍN"""
        return self._m

    @property
    def ord(self) -> str:
        """Returns the headword/lemma"""
        return self._ksnid.ord if self._ksnid else self._key

    @property
    def hluti(self) -> str:
        """Return the genre/register"""
        return self._ksnid.hluti if self._ksnid else "alm"

    @property
    def bmynd(self) -> str:
        """Return the inflectional form"""
        return self._ksnid.bmynd if self._ksnid else self._word

    @property
    def mark(self) -> str:
        """Return the inflectional tag. An empty string means that
        the word was not found in BÍN."""
        return self._ksnid.mark if self._ksnid else ""

    @property
    def ofl(self) -> str:
        """Return the word class/category"""
        return self._ksnid.ofl if self._ksnid else "hk"

    @property
    def bin_id(self) -> int:
        """Return the BÍN identifier, or zero if not present in BÍN"""
        return self._ksnid.bin_id if self._ksnid else 0

    def __format__(self, format_spec: str) -> str:
        """Return a requested inflectional variant of the word"""
        if self._ksnid is None or not format_spec:
            # Not found in BÍN or no format specification: can't inflect
            return self.word
        # We allow both hyphen and underscore as variant separators
        to_inflection = tuple(f.strip() for f in re.split(r"[-_]", format_spec))
        bin_id = self.bin_id
        assert self._b is not None
        # Look up the inflectional variant(s)
        v = self._b.lookup_variants(self.word, self.ofl, to_inflection, bin_id=bin_id)
        if not v:
            # No such variants: return the original word
            return self.word
        # Found the requested variant: emulate the case of the original word
        w = v[0].bmynd
        if bin_id == 0:
            # Probably a word created by the compounder: delete the inserted hyphens
            w = w.replace("-", "")
        if self.word.isupper():
            return w.upper()
        if self.word[0].isupper():
            return w[0].upper() + w[1:]
        return w.lower()
