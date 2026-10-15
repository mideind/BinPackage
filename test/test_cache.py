"""The cache of word form lookups must not change any result.

A cached word form serves both plain lookups and compound suffixes, which also see
suffix-only entries (birting 'S'), so interleaving the two must keep them apart.
"""

from typing import Any, Callable

import pytest

from islenska import Bin
from islenska.basics import GenerationalCache
from islenska.bindb import GreynirBin

# Plain words, compounds, unknown words, and the suffix-only 'gresi' alone and as a suffix
WORDS = [
    "hestur", "hestinum", "Reykjavík", "á", "og", "fór", "betri", "kvótakerfi",
    "Gauksstaðamál", "xyzqw", "gresi", "hafragresi", "gresið", "Hafragresinu",
    "kúagresi", "gresi", "fjölskyldubílarnir", "óhefðbundinn", "skemmtilega",
]  # fmt: skip

OPS: dict[str, Callable[[Bin, str], Any]] = {
    "lookup": lambda b, w: b.lookup(w),
    "lookup_sentence_start": lambda b, w: b.lookup(w, at_sentence_start=True),
    "lookup_auto_uppercase": lambda b, w: b.lookup(w, auto_uppercase=True),
    "lookup_ksnid": lambda b, w: b.lookup_ksnid(w),
    "lookup_cats": lambda b, w: b.lookup_cats(w),
    "lookup_lemmas_and_cats": lambda b, w: b.lookup_lemmas_and_cats(w),
    "lookup_nominative": lambda b, w: b.lookup_nominative(w),
    "cast_to_dative": lambda b, w: b.cast_to_dative(w),
}


def _results(cls: type[Bin]) -> list[Any]:
    b = cls()
    return [op(b, w) for w in WORDS for op in OPS.values()]


@pytest.mark.parametrize("cls", [Bin, GreynirBin])
def test_cached_results_match_uncached(
    cls: type[Bin], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A generation of one word form keeps almost nothing: nearly every lookup misses
    monkeypatch.setattr(cls, "_ksnid_cache", GenerationalCache[str, Any](1))
    uncached = _results(cls)
    monkeypatch.setattr(cls, "_ksnid_cache", GenerationalCache[str, Any](4096))
    assert _results(cls) == uncached  # Cold cache
    assert _results(cls) == uncached  # Warm cache


def test_lookup_returns_a_new_list() -> None:
    b = Bin()
    _, first = b.lookup("hestur")
    first.clear()
    assert b.lookup("hestur")[1]


def test_generational_cache() -> None:
    calls: list[str] = []

    def compute(key: str) -> str:
        calls.append(key)
        return key.upper()

    cache: GenerationalCache[str, str] = GenerationalCache(2)
    assert [cache.lookup(k, compute) for k in "abab"] == ["A", "B", "A", "B"]
    assert calls == ["a", "b"]
    # 'c' fills a new generation; 'a' is found in the old one and copied to the new
    assert cache.lookup("c", compute) == "C"
    assert cache.lookup("a", compute) == "A"
    # 'd' starts another generation: 'b', unused for a whole generation, is dropped
    assert cache.lookup("d", compute) == "D"
    assert cache.lookup("a", compute) == "A"
    assert cache.lookup("b", compute) == "B"
    assert calls == ["a", "b", "c", "d", "b"]


def test_generational_cache_size_must_be_positive() -> None:
    with pytest.raises(ValueError):
        GenerationalCache(0)
