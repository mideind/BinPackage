"""

    test_compact.py

    Tests for the compact build of compressed.bin and for the libbin
    compound policy. Copyright © 2026 Miðeind ehf.

    The tests that need a compact file look for it at
    src/islenska/resources/compressed-compact.bin, or at the path in the
    ISLENSKA_COMPACT_BIN environment variable, and are skipped otherwise
    (the CI job 'compact' builds it). The other tests run against whatever
    file the package is using.

"""

from typing import List

import os

import pytest

from islenska import Bin
from islenska.basics import Ksnid
from islenska.bincompress import BinCompressed
from islenska.dawgdictionary import Wordbase

_HERE = os.path.dirname(os.path.abspath(__file__))
_RESOURCES = os.path.join(_HERE, "..", "src", "islenska", "resources")
_COMPACT = os.environ.get("ISLENSKA_COMPACT_BIN") or os.path.join(
    _RESOURCES, "compressed-compact.bin"
)
_FULL = os.path.join(_RESOURCES, "compressed.bin")

needs_compact = pytest.mark.skipif(
    not os.path.isfile(_COMPACT), reason="no compact compressed.bin available"
)


def _keys(klist: List[Ksnid]):
    return sorted(
        (k.ord, k.bin_id, k.ofl, k.hluti, k.bmynd, k.mark, k.ksnid_string) for k in klist
    )


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


@needs_compact
def test_compact_file_opens() -> None:
    c = BinCompressed(_COMPACT)
    f = BinCompressed(_FULL)
    assert c.is_compact and not f.is_compact
    assert c._max_bin_id == f._max_bin_id
    assert c.begin_greynir_utg == f.begin_greynir_utg


@needs_compact
def test_compact_restores_dropped_compounds() -> None:
    c = BinCompressed(_COMPACT)
    f = BinCompressed(_FULL)
    # Every reading of a compound that the compact build drops comes back
    # unchanged, bin_id, subcategory and KRISTINsnid fields included
    for w in ("bókahillum", "járnbrautarlestin", "knattspyrnusnillingur", "hestarnir", "xyzzy"):
        assert _keys(c.lookup_ksnid(w)) == _keys(f.lookup_ksnid(w))
        assert c.contains(w) == f.contains(w)
        assert (w in c) == (w in f)
    bin_id = f.lookup_ksnid("bókahillum")[0].bin_id
    assert _keys(c.lookup_id(bin_id)) == _keys(f.lookup_id(bin_id))
    assert sorted(c.lemma_forms(bin_id)) == sorted(f.lemma_forms(bin_id))
    assert c.lemma(bin_id) == f.lemma(bin_id)


@needs_compact
def test_compact_bin_api() -> None:
    """The Bin class gives the same answers over the compact file,
    including for words it has to interpret as novel compounds"""

    class CompactBin(Bin):
        _bc = BinCompressed(_COMPACT)

    class FullBin(Bin):
        _bc = BinCompressed(_FULL)

    cb = CompactBin()
    fb = FullBin()
    for w in (
        "bókahillum",
        "Bókahillum",
        "járnbrautarlestin",
        "fornsögulegur",
        "Fornsögulegur",
        "síamskattarkjóll",
        "xqbókahillum",
        "óhefðbundinn",
    ):
        for kwargs in ({}, {"at_sentence_start": True}):
            wa, ma = fb.lookup(w, **kwargs)
            wb, mb = cb.lookup(w, **kwargs)
            assert (wa, sorted(ma)) == (wb, sorted(mb)), w
        assert _keys(fb.lookup_ksnid(w)[1]) == _keys(cb.lookup_ksnid(w)[1])
        assert fb.lookup_forms("bókahilla", "kvk", "þgf") == cb.lookup_forms("bókahilla", "kvk", "þgf")
