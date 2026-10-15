"""Lookups from many threads at once must give the same results as from one.

On free-threaded Python (3.14t) the threads really run in parallel, so this exercises
libbin and the shared lookup caches, including eviction, under contention.
"""

import random
import sys
import sysconfig
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import pytest

from islenska import Bin
from islenska.basics import LFU_Cache
from islenska.bindb import GreynirBin, KsnidList

THREADS = 8

WORDS = [
    "hestur",
    "hestinum",
    "hesta",
    "fjarðarins",
    "kvótakerfi",
    "instagram",
    "Reykjavík",
    "á",
    "og",
    "fara",
    "fór",
    "góður",
    "betri",
    "best",
    "síðan",
    "Gauksstaðamál",
    "Vestur-Þýskaland",
    "xyzqw",
    "ánægja",
    "Ánægja",
    "maður",
    "menn",
]
PREFIXES = [
    "hesta",
    "bíl",
    "skóla",
    "fjarðar",
    "kvóta",
    "sjávar",
    "flug",
    "vatns",
    "lands",
    "borgar",
]
HEADS = [
    "maður",
    "manni",
    "hús",
    "kerfi",
    "stjóri",
    "vegur",
    "ferð",
    "sölu",
    "nefnd",
    "bátnum",
]
# Known words, unknown words and compounds, some made up, plus capitalized forms
_WORDS = WORDS + [p + h for p in PREFIXES for h in HEADS]
ALL_WORDS = _WORDS + [w.capitalize() for w in _WORDS]

OPS: list[tuple[str, Callable[[Bin, str], Any]]] = [
    ("lookup", lambda b, w: b.lookup(w)),
    ("lookup_sentence_start", lambda b, w: b.lookup(w, at_sentence_start=True)),
    ("lookup_ksnid", lambda b, w: b.lookup_ksnid(w)),
    ("lookup_cats", lambda b, w: b.lookup_cats(w)),
    ("lookup_nominative", lambda b, w: b.lookup_nominative(w)),
    ("lookup_raw_nominative", lambda b, w: b.lookup_raw_nominative(w)),
    ("cast_to_dative", lambda b, w: b.cast_to_dative(w)),
]


def _run_all(bins: list[Bin], words: list[str]) -> dict[tuple[int, str, str], Any]:
    return {
        (i, name, w): op(b, w)
        for i, b in enumerate(bins)
        for name, op in OPS
        for w in words
    }


def test_parallel_lookups_match_serial(monkeypatch: pytest.MonkeyPatch) -> None:
    bins = [Bin(), Bin(add_compounds=False), GreynirBin()]
    expected = _run_all(bins, ALL_WORDS)

    # Start with empty caches small enough that the threads also evict entries
    monkeypatch.setattr(Bin, "_ksnid_cache", LFU_Cache[str, KsnidList](maxsize=64))
    monkeypatch.setattr(GreynirBin, "_ksnid_cache", LFU_Cache[str, KsnidList](maxsize=64))
    barrier = threading.Barrier(THREADS)

    def work(seed: int) -> list[tuple[int, str, str]]:
        keys = list(expected)
        random.Random(seed).shuffle(keys)
        barrier.wait()
        return [
            (i, name, w)
            for i, name, w in keys
            if dict(OPS)[name](bins[i], w) != expected[(i, name, w)]
        ]

    with ThreadPoolExecutor(THREADS) as pool:
        mismatches = [m for ms in pool.map(work, range(THREADS)) for m in ms]
    assert mismatches == []


@pytest.mark.skipif(
    not sysconfig.get_config_var("Py_GIL_DISABLED"), reason="needs free-threaded Python"
)
def test_gil_stays_disabled() -> None:
    # An extension that does not declare free-threading support turns the GIL back on at import
    Bin().lookup("hestur")
    assert not sys._is_gil_enabled()  # type: ignore[attr-defined]
