"""

    BinPackage

    BIN database access module

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

    This module encapsulates access to the BIN (Beygingarlýsing íslensks nútímamáls)
    database of word forms, including lookup of abbreviations and basic strategies
    for handling missing words.

    The database is assumed to be packed into a compressed binary file,
    which is wrapped inside the bincompress.py module.

    Word lookups are cached in Least Frequently Used (LFU) caches.

"""

from typing import (
    Mapping,
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
from .dawgdictionary import Wordbase, SOFT_HYPHEN
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
    def __call__(
        self,
        w: str,
        *,
        cat: Optional[str] = None,
        lemma: Optional[str] = None,
        bin_id: Optional[int] = None,
        singular: bool = False,
        indefinite: bool = False,
        all_forms: bool = False,
        inflection_filter: Optional[InflectionFilter] = None,
    ) -> BinEntryList:
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
_LEMMA_FILTERS: Mapping[str, InflectionFilter] = {
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
        # When True (the default), the compounding algorithm marks the
        # component boundaries it discovers with a hyphen in the 'ord' and
        # 'bmynd' fields ('síamskattar-kjóll'). Set to False to get the bare,
        # concatenated form ('síamskattarkjóll'). This only affects the
        # synthetic boundaries found by the algorithm; hyphens that are part
        # of the queried word, or that occur in BÍN itself (e.g.
        # 'Vestur-Þýskaland'), are always preserved.
        self._add_compound_hyphens = options.pop("add_compound_hyphens", True)
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

    def _last_part_is_defective(
        self,
        surface: str,
        lookup_func: LookupFunc[_T],
    ) -> bool:
        """True iff every noun interpretation of ``surface`` is a defective
        paradigm — plurale-tantum (only ``FT`` marks) or singulare-tantum
        (only ``ET`` marks). Used to demote compound-split candidates
        whose head lacks one number. If ``surface`` has no noun
        interpretation we return False so the existing heuristic governs
        the choice — only nouns exhibit the tantum pathology this is
        guarding against."""
        if self._bc is None:
            return False
        entries = lookup_func(surface, compound=True)
        # First pass: if the surface-form entries themselves already cover
        # both ET and FT for some lemma, that lemma's paradigm is complete
        # and we can skip the per-lemma lookup entirely.
        noun_ids: Set[int] = set()
        sg_ids: Set[int] = set()
        pl_ids: Set[int] = set()
        for e in entries:
            if e.ofl not in _NOUNS or not e.bin_id:
                continue
            noun_ids.add(e.bin_id)
            if "ET" in e.mark:
                sg_ids.add(e.bin_id)
            if "FT" in e.mark:
                pl_ids.add(e.bin_id)
        if not noun_ids:
            return False
        if sg_ids & pl_ids:
            # Fast path: some lemma's surface entries already span both
            # numbers, e.g. the bare form `mál` matches NFET, ÞFET, NFFT
            # and ÞFFT all at once. That lemma is provably bi-numerical
            # without a second lookup.
            return False
        # Slow path: the surface form is number-unambiguous (matches
        # only ET-marked or only FT-marked entries for each lemma), so
        # the surface entries alone can't tell us whether the lemma is
        # bi-numerical. We have to consult the rest of the paradigm.
        #
        # Concrete example: when the compound splitter hands us the
        # definite-singular surface `málið` (from `gauksstaðamálið`),
        # the surface entries only match NFETgr and ÞFETgr of the
        # `mál` lemma, putting `mál` in sg_ids but not pl_ids. The
        # lemma is in fact full-paradigm (NFFT `mál`, ÞGFFT `málum`,
        # etc.) — we only see that by inspecting lookup_id(bin_id).
        # Without this loop we'd misclassify `mál` as singulare-tantum
        # and pick the wrong split.
        #
        # We pre-seed has_sg / has_pl from the surface-entry sets so
        # the inner loop can exit as soon as the missing number turns
        # up in the paradigm.
        for bin_id in noun_ids:
            has_sg = bin_id in sg_ids
            has_pl = bin_id in pl_ids
            for k in self._bc.lookup_id(bin_id):
                has_sg = has_sg or "ET" in k.mark
                has_pl = has_pl or "FT" in k.mark
                if has_sg and has_pl:
                    return False
        return True

    def _select_compound_candidate(
        self,
        candidates: List[List[str]],
        lookup_func: LookupFunc[_T],
    ) -> List[str]:
        """Pick the best compound-split candidate. Candidates arrive in
        the existing heuristic order (longest last part, fewest parts).
        Prefer the first candidate whose head is not a defective-paradigm
        noun; fall back to the heuristic winner if every head is
        defective."""
        for cand in candidates:
            if not self._last_part_is_defective(cand[-1], lookup_func):
                return cand
        return candidates[0]

    def _compound_meanings(
        self,
        w: str,
        lower_w: str,
        at_sentence_start: bool,
        lookup_func: LookupFunc[_T],
        ctor: EntryCtor[_T],
        *,
        insert_hyphen: bool = True,
    ) -> ResultTuple[_T]:
        """Return a list of matching entries for this word,
        when interpreted as a compound word. If insert_hyphen is False,
        the boundary that the compounding algorithm discovers is not marked
        with a hyphen, i.e. the bare concatenated form is returned. Hyphens
        and spaces that are already present in ``w`` are always respected."""
        m: List[_T]
        if " " in w:
            # The word is a multi-word compound, such as
            # 'félags- og barnamálaráðherra': Look at the last part only
            prefix, suffix = w.rsplit(" ", maxsplit=1)
            w_suffix, m = self._compound_meanings(
                suffix, suffix.lower(), False, lookup_func, ctor,
                insert_hyphen=insert_hyphen,
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
                suffix, suffix.lower(), False, lookup_func, ctor,
                insert_hyphen=insert_hyphen,
            )
            if not m:
                return w, m
            # For words such as 'Ytri-Hnaus', retain the uppercasing of the suffix
            uppercase_suffix = suffix[0].isupper() and suffix[1:].islower()
            w = prefix + "-" + suffix
            # The hyphen here belongs to the queried word, so it is always
            # retained, regardless of the insert_hyphen setting
            m = self._prefix_meanings(
                m, prefix, ctor, uppercase_suffix=uppercase_suffix
            )
            return w, m
        return_w = w
        candidates = Wordbase.slice_compound_word_candidates(w)
        if not candidates and lower_w != w:
            # If not able to slice in original case, try lower case
            candidates = Wordbase.slice_compound_word_candidates(lower_w)
            if candidates:
                return_w = lower_w
        if not candidates:
            # No way to find a compound meaning: give up
            return w, []
        cw = self._select_compound_candidate(candidates, lookup_func)
        # This looks like a compound word:
        # use the meaning of its last part. The component boundaries are
        # marked with hyphens only if insert_hyphen is True; otherwise the
        # prefix components are concatenated directly.
        prefix = ("-" if insert_hyphen else "").join(cw[0:-1])
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
        return return_w, self._prefix_meanings(
            m, prefix, ctor, insert_hyphen=insert_hyphen
        )

    def _lookup(
        self,
        w: str,
        at_sentence_start: bool,
        auto_uppercase: bool,
        lookup_func: LookupFunc[_T],
        ctor: EntryCtor[_T],
        *,
        insert_hyphen: bool = True,
    ) -> ResultTuple[_T]:
        """Lookup a simple or compound word in the database and
        return its meaning(s). This function checks for abbreviations,
        upper/lower case variations, etc. The insert_hyphen flag controls
        whether compound-component boundaries found by the compounding
        algorithm are marked with a hyphen (see _compound_meanings())."""

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
                w, lower_w, at_sentence_start, lookup_func, ctor,
                insert_hyphen=insert_hyphen,
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
                insert_hyphen=insert_hyphen,
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
            insert_hyphen=self._add_compound_hyphens,
        )

    def _lookup_keep_hyphens(
        self, w: str, at_sentence_start: bool = False, auto_uppercase: bool = False
    ) -> ResultTuple[BinEntry]:
        """Like lookup(), but always marks compound-component boundaries with
        a hyphen, regardless of the add_compound_hyphens flag. Used internally
        by the case-casting functions, which rely on the hyphen to locate the
        boundary between prefix and suffix; the hyphen itself does not appear
        in their (concatenated) output."""
        return self._lookup(
            w,
            at_sentence_start,
            auto_uppercase,
            self._meanings_cache_lookup,
            make_bin_entry,
            insert_hyphen=True,
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
            insert_hyphen=self._add_compound_hyphens,
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
            insert_hyphen=self._add_compound_hyphens,
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
            insert_hyphen=self._add_compound_hyphens,
        )
        return set((mm.ord, mm.ofl) for mm in m)

    def lookup_forms(self, lemma: str, cat: str, case: str) -> BinEntryList:
        """Lookup all word forms in the indicated case, of the given lemma.
        This is mainly used to retrieve inflection forms of nouns, where
        we want to retrieve singular and plural, definite and indefinite
        forms in particular cases. Note that lookup_variants() below is
        a more flexible alternative to this function. If the lemma is not
        found in BÍN but can be resolved as a compound word, the forms of
        its head are enumerated and re-prefixed."""
        assert self._bc is not None
        bc: BinCompressed = self._bc
        norm_case = case.upper().replace("GR", "gr")
        m = self._filter_meanings(
            bc.lookup_case(lemma, norm_case, lemma=lemma, cat=cat, all_forms=True)
        )
        if m or bc.contains(lemma):
            # Either the lemma was found, or it is present in BÍN as a non-lemma
            # surface form (and thus deliberately yields nothing here): only a
            # lemma that is absent from BÍN is a candidate for compounding.
            return m

        def suffix_forms_lookup(key: str, compound: bool = False) -> BinEntryList:
            """Enumerate the forms of a compound head (the last component),
            in the requested case. The head is a genuine BÍN word, so no
            further compounding or lemma/id constraints apply."""
            return self._filter_meanings(
                bc.lookup_case(key, norm_case, cat=cat, all_forms=True)
            )

        return self._compound_case(lemma, suffix_forms_lookup)

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

        _, m = self._lookup(
            w, False, False, variant_lookup, Ksnid.make,
            insert_hyphen=self._add_compound_hyphens,
        )
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
        """Deprecated: prefer lookup_nominative(). Returns a set of BinEntry
        tuples for all word forms in nominative case, unfiltered except for
        the presence of 'NF' in the mark field."""
        assert self._bc is not None
        return self._filter_meanings(self._bc.raw_nominative(w))

    def _compound_case(
        self, w: str, suffix_lookup: LookupFunc[BinEntry]
    ) -> BinEntryList:
        """Resolve case forms for a word that is not present in BÍN as a whole
        but can be interpreted as a compound. The compounding algorithm splits
        ``w``; ``suffix_lookup`` is then applied to the head (the last
        component) to obtain its forms in the desired case, and the prefix is
        prepended to each result. Component boundaries discovered by the
        algorithm honour the add_compound_hyphens flag, while hyphens and
        spaces that are part of ``w`` itself are always retained — exactly as
        in lookup(). Returns [] when compounding is disabled or ``w`` has no
        compound interpretation."""
        if not self._add_compounds:
            return []
        _, m = self._compound_meanings(
            w,
            w.lower(),
            False,
            suffix_lookup,
            make_bin_entry,
            insert_hyphen=self._add_compound_hyphens,
        )
        return m

    def _lookup_case(
        self,
        case_func: Callable[..., Set[BinEntryTuple]],
        w: str,
        *,
        cat: Optional[str] = None,
        lemma: Optional[str] = None,
        bin_id: Optional[int] = None,
        singular: bool = False,
        indefinite: bool = False,
        all_forms: bool = False,
        inflection_filter: Optional[InflectionFilter] = None,
    ) -> BinEntryList:
        """Shared implementation of lookup_nominative/accusative/dative/genitive."""
        assert self._bc is not None
        m = self._filter_meanings(case_func(
            w,
            cat=cat,
            lemma=lemma,
            utg=bin_id,
            singular=singular,
            indefinite=indefinite,
            all_forms=all_forms,
            inflection_filter=inflection_filter,
        ))
        if m or bin_id is not None or self.contains(w):
            # We resolve a compound only when the word is genuinely absent from
            # BÍN, mirroring lookup(). So we stop here if anything was found, or
            # a specific BÍN id was requested (a constructed compound has no id
            # of its own), or the word does occur in BÍN but failed the
            # cat/lemma/case constraints above (in which case the empty result
            # is intentional and must not be second-guessed by compounding).
            return m

        def suffix_case_lookup(key: str, compound: bool = False) -> BinEntryList:
            """Case forms of a compound head. The whole-word lemma/bin_id are
            not propagated here, as they identify the compound, not its head;
            the cat constraint, however, does apply to the head."""
            return self._filter_meanings(case_func(
                key,
                cat=cat,
                lemma=None,
                utg=None,
                singular=singular,
                indefinite=indefinite,
                all_forms=all_forms,
                inflection_filter=inflection_filter,
            ))

        m = self._compound_case(w, suffix_case_lookup)
        if lemma is not None:
            # Restrict to the requested lemma, which for a compound is the
            # whole-word lemma (matched with or without inserted hyphens)
            m = [e for e in m if lemma in (e.ord, e.ord.replace("-", ""))]
        return m

    def lookup_nominative(
        self,
        w: str,
        *,
        cat: Optional[str] = None,
        lemma: Optional[str] = None,
        bin_id: Optional[int] = None,
        singular: bool = False,
        indefinite: bool = False,
        all_forms: bool = False,
        inflection_filter: Optional[InflectionFilter] = None,
    ) -> BinEntryList:
        """Return BinEntry tuples for all word forms in nominative case
        for the lemmas of the given word. See lookup_accusative() for a
        description of the keyword arguments."""
        assert self._bc is not None
        return self._lookup_case(
            self._bc.nominative, w,
            cat=cat, lemma=lemma, bin_id=bin_id,
            singular=singular, indefinite=indefinite, all_forms=all_forms,
            inflection_filter=inflection_filter,
        )

    def lookup_accusative(
        self,
        w: str,
        *,
        cat: Optional[str] = None,
        lemma: Optional[str] = None,
        bin_id: Optional[int] = None,
        singular: bool = False,
        indefinite: bool = False,
        all_forms: bool = False,
        inflection_filter: Optional[InflectionFilter] = None,
    ) -> BinEntryList:
        """Return BinEntry tuples for all word forms in accusative case
        for the lemmas of the given word.

        Keyword arguments:
          cat: restrict to a single word category (e.g. 'kk', 'kvk', 'hk', 'lo');
            pass 'no' to match any of {'kk', 'kvk', 'hk'}.
          lemma: restrict to entries whose lemma equals this string.
          bin_id: restrict to entries with this BÍN id.
          singular: force singular forms only.
          indefinite: force indefinite forms only (drop the definite article 'gr'
            and weak adjective declensions).
          all_forms: return every form regardless of number/definiteness — overrides
            singular/indefinite and the number/definiteness of the input word.
          inflection_filter: callable taking the 'mark' (beyging) string and
            returning True for entries that should be included."""
        assert self._bc is not None
        return self._lookup_case(
            self._bc.accusative, w,
            cat=cat, lemma=lemma, bin_id=bin_id,
            singular=singular, indefinite=indefinite, all_forms=all_forms,
            inflection_filter=inflection_filter,
        )

    def lookup_dative(
        self,
        w: str,
        *,
        cat: Optional[str] = None,
        lemma: Optional[str] = None,
        bin_id: Optional[int] = None,
        singular: bool = False,
        indefinite: bool = False,
        all_forms: bool = False,
        inflection_filter: Optional[InflectionFilter] = None,
    ) -> BinEntryList:
        """Return BinEntry tuples for all word forms in dative case
        for the lemmas of the given word. See lookup_accusative() for a
        description of the keyword arguments."""
        assert self._bc is not None
        return self._lookup_case(
            self._bc.dative, w,
            cat=cat, lemma=lemma, bin_id=bin_id,
            singular=singular, indefinite=indefinite, all_forms=all_forms,
            inflection_filter=inflection_filter,
        )

    def lookup_genitive(
        self,
        w: str,
        *,
        cat: Optional[str] = None,
        lemma: Optional[str] = None,
        bin_id: Optional[int] = None,
        singular: bool = False,
        indefinite: bool = False,
        all_forms: bool = False,
        inflection_filter: Optional[InflectionFilter] = None,
    ) -> BinEntryList:
        """Return BinEntry tuples for all word forms in genitive case
        for the lemmas of the given word. See lookup_accusative() for a
        description of the keyword arguments."""
        assert self._bc is not None
        return self._lookup_case(
            self._bc.genitive, w,
            cat=cat, lemma=lemma, bin_id=bin_id,
            singular=singular, indefinite=indefinite, all_forms=all_forms,
            inflection_filter=inflection_filter,
        )

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
            self._lookup_keep_hyphens,
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
            self._lookup_keep_hyphens,
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
            self._lookup_keep_hyphens,
            self.lookup_genitive,
            filter_func=filter_func,
        )

    def get_compound(
        self, w: str, at_sentence_start: bool = False
    ) -> ResultTuple[BinEntry]:
        """Lookup a word in the database and return its meaning(s),
        prioritizing returning its compound structure. The component
        boundaries are always marked with hyphens, even when the instance
        was created with add_compound_hyphens=False, since exposing the
        compound structure is the whole purpose of this function."""

        w, m = self._compound_meanings(
            w, w.lower(), at_sentence_start, self._meanings_cache_lookup,
            make_bin_entry, insert_hyphen=True,
        )

        return w, m

    def soft_hyphenate(
        self,
        word: str,
        *,
        mode: str = "natural",
        min_left: int = 2,
        min_right: int = 2,
        min_word: int = 8,
        hyphen: str = SOFT_HYPHEN,
    ) -> str:
        """Return ``word`` with soft hyphens (U+00AD by default) inserted at
        its internal compound-component boundaries, suitable for flexible
        line-breaking by a typesetter.

        This is the database-backed counterpart of
        ``Wordbase.insert_soft_hyphens`` (see there for the meaning of
        ``mode`` and the ``min_*`` parameters). On top of the length guards it
        consults BÍN to (1) leave closed-class function words (prepositions,
        conjunctions, pronouns, articles, ...) untouched, so that a word such
        as ``ásamt`` — which the DAWG would otherwise mis-split as ``ás|amt``
        — is returned unchanged, and (2) also decompose compound modifiers
        that are possessive (genitive) prefixes, which the pure-DAWG
        primitive leaves whole (``morgunverðarhlaðborð`` ->
        ``morgun|verðar|hlað|borð``)."""
        # A word is a function word when it has direct BÍN readings but none
        # of them fall in an open word category (noun, verb, adjective).
        # `lookup_cats` only falls back to compound resolution when there is
        # no direct reading, so a genuine compound still reports its (open)
        # head category here and is hyphenated normally.
        bare = word.replace(SOFT_HYPHEN, "")
        cats = self.lookup_cats(bare)
        if cats and cats.isdisjoint(_OPEN_CATS):
            return bare
        return Wordbase.insert_soft_hyphens(
            word,
            mode=mode,
            min_left=min_left,
            min_right=min_right,
            min_word=min_word,
            hyphen=hyphen,
            recurse_modifier=self._is_possessive_prefix,
        )

    def _is_possessive_prefix(self, form: str) -> bool:
        """True if ``form`` is a possessive (genitive) prefix — a modifier
        safe to decompose further. In compound-modifier position a form that
        can be genitive almost certainly is the linking genitive, so it is
        enough that ``form`` is in BÍN with at least one genitive noun reading.
        Gating on ``contains`` keeps the lookup from falling back to compound
        resolution, so we inspect the form's own readings."""
        if not self.contains(form):
            return False
        return any(
            e.ofl in _NOUNS and "EF" in e.mark
            for e in self.lookup_ksnid(form)[1]
        )


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
