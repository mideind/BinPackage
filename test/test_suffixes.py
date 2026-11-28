"""

    test_suffixes.py

    Tests for the curation of the compound suffix list (resources/suffixes.txt)
    and for the vocabulary added on top of BÍN (resources/ord.auka.csv).
    Copyright © 2026 Miðeind ehf.

    A form in the suffix list lets any unknown word of the shape
    'known prefix + that form' pass as a compound. The list therefore leaves
    out short forms, which match foreign words and names ('Parker', 'alarm'),
    and forms that would take the linking letters of existing compounds
    ('kolefnis-verð' must not become 'kolefni-sverð').

"""

from pathlib import Path
from typing import Dict, Set, Tuple

import pytest

from islenska import Bin
from islenska.basics import data_dir
from islenska.bindb import GreynirBin
from islenska.dawgdictionary import Wordbase


def _old_released_data() -> bool:
    """True if the data come from an installed islenska-data package that
    predates the suffix list and vocabulary tested here (5.0.1)"""
    try:
        import islenska_data
    except ImportError:
        return False
    if Path(data_dir()) != Path(islenska_data.data_dir()):
        # Data built into the source checkout: always current
        return False
    try:
        version = tuple(int(x) for x in islenska_data.__version__.split(".")[:3])
    except ValueError:
        return False
    return version < (5, 0, 1)


pytestmark = pytest.mark.skipif(
    _old_released_data(), reason="needs islenska-data 5.0.1 or data built from this checkout"
)


def _lemmas(b: Bin, w: str) -> Set[str]:
    return {m.ord for m in b.lookup(w)[1]}


def test_added_suffixes() -> None:
    """Compounds that end in a suffix added in islenska-data 5.0.1"""
    b = Bin()
    for w, lemma, ofl in (
        ("brottvísunarstöð", "brottvísunar-stöð", "kvk"),
        ("borgarlínustöð", "borgar-línu-stöð", "kvk"),
        ("sætisarminn", "sætis-armur", "kk"),
        ("leiguflugsarms", "leiguflugs-armur", "kk"),
        ("svefnlengd", "svefn-lengd", "kvk"),
        ("skipulagsheilda", "skipulags-heild", "kvk"),
        ("auglýsingaskjám", "auglýsinga-skjár", "kk"),
        ("æðstaklerknum", "æðsta-klerkur", "kk"),
        ("hákarlaverkun", "hákarla-verkun", "kvk"),
        ("fylgdardömu", "fylgdar-dama", "kvk"),
        ("öfgavinstri", "öfga-vinstri", "lo"),
    ):
        _, m = b.lookup(w)
        assert any(mm.ord == lemma and mm.ofl == ofl and mm.bin_id == 0 for mm in m), w
    # The compounder resolves 'vélarmur' in plain BÍN; its accusative needs
    # the three-letter form 'arm', which only the Greynir vocabulary has
    assert "vél-armur" in _lemmas(b, "vélarmur")
    assert not b.lookup("vélarm")[1]


def test_short_forms_are_not_suffixes() -> None:
    suffixes = Wordbase.dawg_suffixes()
    for form in ("arm", "ker", "kar", "við", "hún", "ost", "vá", "úr", "ætlun", "höld"):
        assert form not in suffixes, form
    b = Bin()
    for w in ("alarm", "parker", "barker", "bunker"):
        assert not b.lookup(w)[1], w


def test_suffixes_do_not_take_linking_letters() -> None:
    """A suffix must not win over the split of an existing compound by
    taking the last letters of its first part: the longest last part ranks
    first, so 'sverð' would turn 'kolefnis-verð' into 'kolefni-sverð'"""
    suffixes = Wordbase.dawg_suffixes()
    for form in ("sverð", "skafl", "skafla", "sæði", "seyra", "spanna", "tjakka", "armanna", "damanna"):
        assert form not in suffixes, form
    b = Bin()
    for w, lemma in (
        ("kolefnisverð", "kolefnis-verð"),
        ("efniskafla", "efnis-kafli"),
        ("blómkálseyra", "blómkáls-eyra"),
        ("pottjárnspanna", "pottjárns-panna"),
        ("haustjakka", "haust-jakki"),
        ("grautarmanna", "grautar-maður"),
        ("landamanna", "landa-maður"),
    ):
        lemmas = _lemmas(b, w)
        assert lemma in lemmas, w
        assert all(x.rsplit("-", 1)[0] == lemma.rsplit("-", 1)[0] for x in lemmas), w


def test_greynir_vocabulary() -> None:
    """Words and forms added on top of BÍN, visible through GreynirBin only"""
    g = GreynirBin()
    b = Bin()
    # BÍN has only the plural 'innviðir'; the singular is a headword of its own
    _, m = g.lookup("innviður")
    assert [(mm.ord, mm.ofl, mm.mark) for mm in m] == [("innviður", "kk", "NFET")]
    assert m[0].bin_id > 0
    assert _lemmas(g, "grunninnviður") == {"grunn-innviður"}
    # Every valid form is there, also where it coincides with a form of
    # another word: 'innviði' is the dative singular and the accusative plural
    assert _lemmas(g, "innviði") == {"innviðir", "innviður"}
    assert {mm.mark for mm in g.lookup("innviði")[1] if mm.ord == "innviður"} == {"ÞGFET2"}
    assert not b.lookup("innviður")[1]

    _, m = g.lookup("vélarm")
    assert [(mm.ord, mm.mark) for mm in m] == [("vélarmur", "ÞFET")]
    assert {mm.mark for mm in g.lookup("vélörmum")[1]} == {"ÞGFFT"}
    # 'vélarmanna' is the genitive plural of both 'vélarmur' and 'vélarmaður'
    assert _lemmas(g, "vélarmanna") == {"vélarmaður", "vélarmur"}

    for w in ("eldgosavá", "eldfjallavá", "hraunavá", "hraunvá"):
        _, m = g.lookup(w)
        assert {(mm.ord, mm.ofl) for mm in m} == {(w, "kvk")}, w
        assert {mm.mark for mm in m} == {"NFET", "ÞFET", "ÞGFET"}, w
        assert _lemmas(g, w + "r") == {w}
        assert not b.lookup(w)[1], w

    # The plural of 'framhjáhald', which BÍN lists in the singular only
    _, m = g.lookup("framhjáhöld")
    assert {(mm.ord, mm.mark) for mm in m} == {("framhjáhald", "NFFT"), ("framhjáhald", "ÞFFT")}
    assert all(mm.bin_id == b.lookup("framhjáhald")[1][0].bin_id for mm in m)
    assert not b.lookup("framhjáhöld")[1]

    # Recurring compounds whose last parts are deliberately not suffixes
    for w, lemma, ofl in (
        ("fiskeldisseyru", "fiskeldisseyra", "kvk"),
        ("holdasæðis", "holdasæði", "hk"),
        ("hrossasæði", "hrossasæði", "hk"),
        ("bíltjakk", "bíltjakkur", "kk"),
    ):
        _, m = g.lookup(w)
        assert {(mm.ord, mm.ofl) for mm in m} == {(lemma, ofl)}, w
        assert all(mm.bin_id > 0 for mm in m), w
        assert not b.lookup(w)[1], w

    # The singular of 'sifjaspell', which BÍN lists in the plural only
    assert {mm.mark for mm in g.lookup("sifjaspellsins")[1]} == {"EFETgr"}
    assert {mm.mark for mm in g.lookup("sifjaspells")[1]} == {"EFET"}


def test_suffix_only_entries() -> None:
    """'-varpari' and '-passari' are suffix-only entries (ord.suffixes.csv):
    last parts of compounds, but not words on their own"""
    b = Bin()
    for w, lemma in (
        ("hlaðvarpari", "hlað-varpari"),
        ("hlaðvarparar", "hlað-varpari"),
        ("skjávarpara", "skjá-varpari"),
        ("eldvörpurum", "eld-varpari"),
        ("hundapassarinn", "hunda-passari"),
        ("barnapössurum", "barna-passari"),
    ):
        _, m = b.lookup(w)
        assert m, w
        assert {(mm.ord, mm.ofl, mm.bin_id) for mm in m} == {(lemma, "kk", 0)}, w
    for w in ("varpari", "passari", "passarar"):
        assert not b.lookup(w)[1], w
        assert not b.lookup_dative(w), w
        assert b.cast_to_dative(w) == w
    # The compounds are cast, by Bin as well as GreynirBin
    for db in (b, GreynirBin()):
        assert db.cast_to_accusative("hlaðvarpari") == "hlaðvarpara"
        assert db.cast_to_dative("barnapassarar") == "barnapössurum"
        assert db.cast_to_genitive("hundapassarinn") == "hundapassarans"
        assert [mm.bmynd for mm in db.lookup_dative("skjávarparar")] == [
            "skjá-vörpurum"
        ]
    # A compound that BÍN has is found there, not composed
    _, m = b.lookup("kúluvarpari")
    assert m and all(mm.ord == "kúluvarpari" and mm.bin_id > 0 for mm in m)


def test_suffix_only_entries_are_not_in_bin() -> None:
    """A suffix-only entry that repeats a BÍN entry (same lemma, same
    category, no form that BÍN lacks) adds nothing, and gives every compound
    of it each reading twice. 'beri', 'gjafi' and 'stýra' were such entries."""
    csv = Path(__file__).parent.parent / "src/islenska/resources/ord.suffixes.csv"
    entries: Dict[Tuple[str, str], Set[Tuple[str, str]]] = {}
    for line in csv.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        lemma, _, ofl, _, form, mark = line.split(";")[:6]
        entries.setdefault((lemma, ofl), set()).add((form, mark))
    assert ("isti", "kk") in entries
    b = Bin()
    for (lemma, ofl), forms in entries.items():
        # Bin.lookup_ksnid() returns the BÍN entries only
        for bin_id in {
            k.bin_id for k in b.lookup_ksnid(lemma)[1] if (k.ord, k.ofl) == (lemma, ofl)
        }:
            bin_forms = {(k.bmynd, k.mark) for k in b.lookup_id(bin_id)}
            assert not forms <= bin_forms, f"{lemma} ({ofl}) is BÍN entry {bin_id}"
    # A compound of such a word gets each reading of it once, from the BÍN
    # entry. (Other readings can still come twice, where BÍN itself has two
    # entries of one lemma and category: the verb 'bera' in 'pönk-bera'.)
    for w, lemma, ofl in (
        ("barnagjafi", "barna-gjafi", "kk"),
        ("pönkbera", "pönk-beri", "kk"),
        ("hundastýrunnar", "hunda-stýra", "kvk"),
    ):
        for mm in (
            b.lookup(w)[1],
            b.lookup_dative(w, all_forms=True),
            b.lookup_forms(lemma.replace("-", ""), ofl, "ef"),
        ):
            m = [e for e in mm if (e.ord, e.ofl) == (lemma, ofl)]
            assert m, w
            assert len(m) == len(set(m)), w
    assert b.cast_to_dative("barnagjafi") == "barnagjafa"
    assert b.cast_to_genitive("hundastýra") == "hundastýru"


def test_agent_nouns_in_vocabulary() -> None:
    """Agent nouns in '-ari' that BÍN lacks, with their whole paradigm"""
    g = GreynirBin()
    for stem in ("röfl", "gigg", "hekl", "púl", "pepp"):
        lemma = stem + "ari"
        marks: Set[str] = set()
        for ending in (
            "ari", "arinn", "ara", "arann", "aranum", "arans",
            "arar", "ararnir", "arana", "urum", "urunum", "aranna",
        ):
            _, m = g.lookup(stem + ending)
            assert m and all(mm.ord == lemma and mm.ofl == "kk" and mm.bin_id > 0 for mm in m), stem + ending
            marks |= {mm.mark for mm in m}
        assert len(marks) == 16, lemma
        assert g.cast_to_dative(lemma) == stem + "ara"
        assert g.cast_to_genitive(stem + "ararnir") == stem + "aranna"


def test_capitalized_vocabulary() -> None:
    g = GreynirBin()
    for w, marks in (("Thorsari", {"NFET"}), ("Thorsararnir", {"NFFTgr"}), ("Thorsurum", {"ÞGFFT"})):
        _, m = g.lookup(w)
        assert {mm.ord for mm in m} == {"Thorsari"}, w
        assert {mm.mark for mm in m} == marks, w


def test_casting_compounds_with_added_suffixes() -> None:
    """'armur', 'stöð' and 'lengd' are also forms of adjectives ('armur',
    'staður', 'lengdur'): a compound that ends in one is cast as the noun"""
    b = Bin()
    for w, acc, dat, gen in (
        ("sætisarmur", "sætisarm", "sætisarmi", "sætisarms"),
        ("brottvísunarstöð", "brottvísunarstöð", "brottvísunarstöð", "brottvísunarstöðvar"),
        ("svefnlengd", "svefnlengd", "svefnlengd", "svefnlengdar"),
        ("sætisarmarnir", "sætisarmana", "sætisörmunum", "sætisarmanna"),
    ):
        assert b.cast_to_accusative(w) == acc, w
        assert b.cast_to_dative(w) == dat, w
        assert b.cast_to_genitive(w) == gen, w
