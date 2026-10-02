"""Lookups return the readings of a word form in a canonical order.

The order is by bin_id, then by the position of the inflection in its
category's paradigm (resources/mark_order.csv, as in MarkOrder.index()), then
in source order. It holds for compounds that a compact build restores at
lookup time ('kvótakerfi', 'bókahillu') as well as for stored forms, so
callers that take the first matching reading get the same, natural one
(singular before plural, indicative before subjunctive) from either build.
"""

from typing import Dict, List, Tuple

from pathlib import Path

from islenska import Bin
from islenska.basics import MarkOrder
from islenska.bincompress import BinCompressed

# MarkOrder reads mark_order.csv, a build input that the islenska wheel
# does not ship; load it from this checkout so that the tests also run
# against an installed package
_MARK_ORDER = Path(__file__).parent.parent / "src" / "islenska" / "resources" / "mark_order.csv"
_order: Dict[str, List[str]] = {}
for line in _MARK_ORDER.read_text(encoding="utf-8").splitlines():
    cat, mark = line.split(";")
    _order.setdefault(cat, []).append(mark)
MarkOrder._order = {k: tuple(v) for k, v in _order.items()}  # type: ignore[reportPrivateUsage]

WORDS = [
    "kvótakerfi",  # a compound; NFET, ÞFET, ÞGFET and the plural NFFT, ÞFFT
    "bókahillu",  # a compound
    "bókahilla",
    "frumstilltust",  # four verb readings: FH/VH, 2P/3P
    "á",  # many lemmas and categories
    "við",
    "hestur",
    "fjarðarins",
    "Ísland",
    "sjóða",
]


def keys(entries: List[Tuple[int, str, str]]) -> List[Tuple[int, int]]:
    return [(bin_id, MarkOrder.index(ofl, mark)) for bin_id, ofl, mark in entries]


def test_word_form_readings_are_in_canonical_order() -> None:
    bc = BinCompressed()
    for w in WORDS:
        k = keys([(e.bin_id, e.ofl, e.mark) for e in bc.lookup_ksnid(w)])
        assert k, w
        assert k == sorted(k), w


def test_lemma_entries_are_in_canonical_order_per_form() -> None:
    bc = BinCompressed()
    for w in WORDS:
        for bin_id in dict.fromkeys(e.bin_id for e in bc.lookup_ksnid(w)):
            entries = bc.lookup_id(bin_id)
            forms = list(dict.fromkeys(e.bmynd for e in entries))
            assert forms == [f for f in bc.lemma_forms(bin_id) if f in forms], w
            for form in forms:
                k = keys([(e.bin_id, e.ofl, e.mark) for e in entries if e.bmynd == form])
                assert k == sorted(k), (w, form)


def test_first_reading_is_the_natural_one() -> None:
    b = Bin()
    _, m = b.lookup("kvótakerfi")
    assert [e.mark for e in m[:4]] == ["NFET", "ÞFET", "ÞGFET", "NFFT"]
    _, m = b.lookup("frumstilltust")
    assert [e.mark for e in m] == [
        "MM-FH-ÞT-2P-FT",
        "MM-FH-ÞT-3P-FT",
        "MM-VH-ÞT-2P-FT",
        "MM-VH-ÞT-3P-FT",
    ]
    # Casting takes the first nominative reading, here the singular one
    assert b.cast_to_dative("kvótakerfi") == "kvótakerfi"
    assert b.cast_to_genitive("Kvótakerfi") == "Kvótakerfis"
