"""

    test_compact.py

    Tests for the compact build of compressed.bin (the only build that
    tools/binpack.py makes) and for the libbin compound policy.
    Copyright © 2026 Miðeind ehf.

    The expected entries of the dropped compounds below are their rows in
    BÍN, as a full (non-compact) build returned them: the compact build
    must restore them exactly, bin_id, subcategory and KRISTINsnid fields
    included.

"""

from typing import List

from islenska import Bin
from islenska.basics import Ksnid
from islenska.bincompress import BinCompressed
from islenska.dawgdictionary import Wordbase


def _keys(klist: List[Ksnid]):
    return [(k.ord, k.bin_id, k.ofl, k.hluti, k.bmynd, k.mark, k.ksnid_string) for k in klist]


def test_compound_split_matches_python_ranking() -> None:
    """The split chosen by libbin is a legal candidate in the ranking
    of Wordbase, and the first one unless a defective noun head was demoted"""
    bc = BinCompressed()
    for w in ("bókahillum", "skólabókasafnsins", "gauksstaðamálið", "járnbrautarlestin", "xyzzy"):
        cands = Wordbase.slice_compound_word_candidates(w)
        cw = bc.compound_split(w)
        if not cands:
            assert cw == []
            continue
        assert cw in cands
        assert bc.compound_candidates(w) == cands
    # The whole word ranks first when it is itself a legal suffix; the
    # first multi-part candidate of a plain compound is its two parts
    cands = bc.compound_candidates("bókahillum")
    assert cands[0] == ["bókahillum"]
    assert [c for c in cands if len(c) > 1][0] == ["bóka", "hillum"]
    assert bc.compound_split("bókahillum") == cands[0]


def test_lookup_id_and_lemma_forms_agree() -> None:
    bc = BinCompressed()
    entries = bc.lookup_ksnid("bókahillum")
    assert entries
    bin_id = entries[0].bin_id
    forms = bc.lemma_forms(bin_id)
    assert forms[-1] == "bókahilla"
    assert set(forms) == {k.bmynd for k in bc.lookup_id(bin_id)}


def test_compressed_bin_is_compact() -> None:
    assert BinCompressed().is_compact


# Word form -> its BÍN entries. All but 'hestarnir' (a form of a kept
# lemma) and 'xyzzy' (no entry) belong to compounds that the compact build
# drops and restores on lookup.
EXPECTED = {
    "bókahillum": [("bókahilla", 154009, "kvk", "alm", "bókahillum", "ÞGFFT", "1;;;;K;1;;;")],
    "járnbrautarlestin": [
        ("járnbrautarlest", 118811, "kvk", "alm", "járnbrautarlestin", "NFETgr", "1;;;;K;1;;;")
    ],
    "knattspyrnusnillingur": [
        ("knattspyrnusnillingur", 98703, "kk", "alm", "knattspyrnusnillingur", "NFET", "1;;;;V;1;;;")
    ],
    "hestarnir": [("hestur", 6179, "kk", "alm", "hestarnir", "NFFTgr", "1;;;;K;1;;;")],
    "xyzzy": [],
}


def test_compact_restores_dropped_compounds() -> None:
    c = BinCompressed()
    for w, expected in EXPECTED.items():
        assert _keys(c.lookup_ksnid(w)) == expected, w
        assert c.contains(w) == bool(expected), w
        assert (w in c) == bool(expected), w
    bin_id = 154009
    assert c.lemma(bin_id) == ("bókahilla", "alm")
    assert c.lemma_forms(bin_id) == [
        "bókahillan", "bókahillanna", "bókahillna", "bókahillnanna", "bókahillu",
        "bókahillum", "bókahilluna", "bókahillunnar", "bókahillunni", "bókahillunum",
        "bókahillur", "bókahillurnar", "bókahilla",
    ]
    entries = c.lookup_id(bin_id)
    assert len(entries) == 18
    assert {k.bmynd for k in entries} == set(c.lemma_forms(bin_id))
    assert all(k.bin_id == bin_id and k.ord == "bókahilla" for k in entries)


def test_compact_bin_api() -> None:
    """The Bin class gives the BÍN answers for dropped compounds, and
    still interprets novel compounds"""
    b = Bin()
    expected = {
        "bókahillum": [("bókahilla", 154009, "ÞGFFT")],
        "Bókahillum": [("bókahilla", 154009, "ÞGFFT")],
        "járnbrautarlestin": [("járnbrautarlest", 118811, "NFETgr")],
        "fornsögulegur": [("fornsögulegur", 390488, "FSB-KK-NFET")],
        "síamskattarkjóll": [("síamskattar-kjóll", 0, "NFET")],
        "xqbókahillum": [],
        "óhefðbundinn": [
            ("óhefðbundinn", 494839, "FSB-KK-NFET"),
            ("óhefðbundinn", 494839, "FSB-KK-ÞFET"),
        ],
    }
    for w, e in expected.items():
        _, m = b.lookup(w, at_sentence_start=True)
        assert [(x.ord, x.bin_id, x.mark) for x in m] == e, w
    assert [(m.bmynd, m.mark) for m in b.lookup_forms("bókahilla", "kvk", "þgf")] == [
        ("bókahillu", "ÞGFET"),
        ("bókahillum", "ÞGFFT"),
        ("bókahillunni", "ÞGFETgr"),
        ("bókahillunum", "ÞGFFTgr"),
    ]
