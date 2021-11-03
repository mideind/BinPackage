"""

    test_bin.py

    Tests for BinPackage module

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

"""

from typing import Optional, Callable, List

from islenska import Bin, BinEntry, BinFilterFunc
from islenska.bincompress import BinCompressed
from islenska.bindb import GreynirBin


BeygingFunc = Callable[[str], bool]


def test_lookup() -> None:
    """ Test querying for different cases of words """

    b = BinCompressed()

    assert b.lookup("") == []
    assert b.lookup("872364") == []
    assert b.lookup(" ") == []
    assert b.lookup("\u7345") == []
    assert b.lookup("blooper") == []
    assert b.lookup(" vera") == []
    assert b.lookup("vera ") == []
    assert b.lookup(" vera ") == []

    k = b.lookup("lyklaborðinu")
    assert len(k) == 1
    assert k[0][0] == "lyklaborð"
    assert k[0][1] == 428971
    assert k[0][2] == "hk"
    assert k[0][3] == "tölv"
    assert k[0][4] == "lyklaborðinu"
    assert k[0][5] == "ÞGFETgr"

    k = b.lookup("rotinborulegastur")
    assert len(k) == 1
    assert k[0][0] == "rotinborulegur"
    assert k[0][1] == 185515
    assert k[0][2] == "lo"
    assert k[0][3] == "alm"
    assert k[0][4] == "rotinborulegastur"
    assert k[0][5] == "ESB-KK-NFET"

    k = b.lookup_ksnid("rotinborulegastur")
    assert len(k) == 1
    assert k[0].ord == "rotinborulegur"
    assert k[0].bin_id == 185515
    assert k[0].ofl == "lo"
    assert k[0].hluti == "alm"
    assert k[0].bmynd == "rotinborulegastur"
    assert k[0].mark == "ESB-KK-NFET"
    assert k[0].millivisun == 391680

    k = b.lookup_ksnid("aðhjúkanin")
    assert len(k) == 1
    assert k[0].ord == "aðhjúkan"
    assert k[0].bin_id == 139772
    assert k[0].ofl == "kvk"
    assert k[0].hluti == "alm"
    assert k[0].bmynd == "aðhjúkanin"
    assert k[0].mark == "NFETgr"
    assert k[0].malsnid == "URE"

    k = b.lookup_id(495410)
    assert len(k) == 1
    assert k[0].bin_id == 495410
    assert k[0].ofl == "uh"
    assert k[0].ord == "sko"

    k = b.lookup_id(495754)
    assert len(k) == 1
    assert k[0].bin_id == 495754
    assert k[0].ofl == "ao"
    assert k[0].ord == "sko"


def test_bin() -> None:
    """ Test querying for different cases of words """

    b = BinCompressed()

    def f(
        word: str,
        case: str,
        lemma: str,
        cat: str,
        inflection_filter: Optional[BeygingFunc] = None,
    ):
        entries = b.lookup_case(
            word, case, cat=cat, lemma=lemma, inflection_filter=inflection_filter
        )
        return {(m[4], m[5]) for m in entries}

    def declension(
        word: str, lemma: str, cat: str, inflection_filter: Optional[BeygingFunc] = None
    ):
        result: List[str] = []

        def bf(b: str):
            if inflection_filter is not None and not inflection_filter(b):
                return False
            return "2" not in b and "3" not in b

        for case in ("NF", "ÞF", "ÞGF", "EF"):
            wf_list = list(f(word, case, lemma, cat, bf))
            result.append(wf_list[0][0] if wf_list else "N/A")
        return tuple(result)

    lo_filter: BeygingFunc = lambda b: "EVB" in b and "FT" in b

    assert f("fjarðarins", "NF", "fjörður", "kk") == {("fjörðurinn", "NFETgr")}
    assert f("breiðustu", "NF", "breiður", "lo", lo_filter) == {
        ("breiðustu", "EVB-KVK-NFFT"),
        ("breiðustu", "EVB-HK-NFFT"),
        ("breiðustu", "EVB-KK-NFFT"),
    }
    assert b.lookup_case("fjarðarins", "NF", cat="kk", lemma="fjörður") == {
        ("fjörður", 5697, "kk", "alm", "fjörðurinn", "NFETgr")
    }
    assert b.lookup_case("breiðastra", "NF", cat="lo", lemma="breiður") == {
        ("breiður", 388135, "lo", "alm", "breiðastir", "ESB-KK-NFFT"),
        ("breiður", 388135, "lo", "alm", "breiðastar", "ESB-KVK-NFFT"),
        ("breiður", 388135, "lo", "alm", "breiðust", "ESB-HK-NFFT"),
    }
    assert f("fjarðarins", "ÞF", "fjörður", "kk") == {("fjörðinn", "ÞFETgr")}
    assert f("breiðustu", "ÞF", "breiður", "lo", lo_filter) == {
        ("breiðustu", "EVB-KVK-ÞFFT"),
        ("breiðustu", "EVB-HK-ÞFFT"),
        ("breiðustu", "EVB-KK-ÞFFT"),
    }
    assert f("fjarðarins", "ÞGF", "fjörður", "kk") == {("firðinum", "ÞGFETgr")}
    assert f("breiðustu", "ÞGF", "breiður", "lo", lo_filter) == {
        ("breiðustu", "EVB-KVK-ÞGFFT"),
        ("breiðustu", "EVB-HK-ÞGFFT"),
        ("breiðustu", "EVB-KK-ÞGFFT"),
    }
    assert f("fjarðarins", "EF", "fjörður", "kk") == {("fjarðarins", "EFETgr")}
    assert f("breiðustu", "EF", "breiður", "lo", lo_filter) == {
        ("breiðustu", "EVB-KVK-EFFT"),
        ("breiðustu", "EVB-HK-EFFT"),
        ("breiðustu", "EVB-KK-EFFT"),
    }
    assert declension("brjóstsykur", "brjóstsykur", "kk") == (
        "brjóstsykur",
        "brjóstsykur",
        "brjóstsykri",
        "brjóstsykurs",
    )
    assert declension("smáskífa", "smáskífa", "kvk", lambda b: "ET" in b) == (
        "smáskífa",
        "smáskífu",
        "smáskífu",
        "smáskífu",
    )
    assert declension("smáskífa", "smáskífa", "kvk", lambda b: "FT" in b) == (
        "smáskífur",
        "smáskífur",
        "smáskífum",
        "smáskífa",
    )
    assert declension("ungabarn", "ungabarn", "hk") == (
        "ungabarn",
        "ungabarn",
        "ungabarni",
        "ungabarns",
    )
    assert declension("geymir", "geymir", "kk") == (
        "geymir",
        "geymi",
        "geymi",
        "geymis",
    )
    assert declension("sulta", "sulta", "kvk", lambda b: "ET" in b) == (
        "sulta",
        "sultu",
        "sultu",
        "sultu",
    )
    assert declension("vígi", "vígi", "hk", lambda b: "ET" in b) == (
        "vígi",
        "vígi",
        "vígi",
        "vígis",
    )
    assert declension("buxur", "buxur", "kvk") == ("buxur", "buxur", "buxum", "buxna")
    assert declension("ríki", "ríki", "hk", lambda b: "ET" in b) == (
        "ríki",
        "ríki",
        "ríki",
        "ríkis",
    )
    assert declension("ríki", "ríki", "hk", lambda b: "FT" in b) == (
        "ríki",
        "ríki",
        "ríkjum",
        "ríkja",
    )
    assert declension("ríki", "ríkir", "kk") == ("ríkir", "ríki", "ríki", "ríkis")
    assert declension("brjóstsykurinn", "brjóstsykur", "kk") == (
        "brjóstsykurinn",
        "brjóstsykurinn",
        "brjóstsykrinum",
        "brjóstsykursins",
    )
    assert declension("smáskífan", "smáskífa", "kvk") == (
        "smáskífan",
        "smáskífuna",
        "smáskífunni",
        "smáskífunnar",
    )
    assert declension("ungabarnið", "ungabarn", "hk") == (
        "ungabarnið",
        "ungabarnið",
        "ungabarninu",
        "ungabarnsins",
    )
    assert declension("geymirinn", "geymir", "kk") == (
        "geymirinn",
        "geyminn",
        "geyminum",
        "geymisins",
    )
    assert declension("sultan", "sulta", "kvk") == (
        "sultan",
        "sultuna",
        "sultunni",
        "sultunnar",
    )
    assert declension("vígið", "vígi", "hk") == ("vígið", "vígið", "víginu", "vígisins")
    assert declension("ríkið", "ríki", "hk") == ("ríkið", "ríkið", "ríkinu", "ríkisins")
    assert declension("geymarnir", "geymir", "kk") == (
        "geymarnir",
        "geymana",
        "geymunum",
        "geymanna",
    )
    assert declension("sulturnar", "sulta", "kvk") == (
        "sulturnar",
        "sulturnar",
        "sultunum",
        "sultnanna",
    )
    assert declension("vígin", "vígi", "hk") == (
        "vígin",
        "vígin",
        "vígjunum",
        "vígjanna",
    )
    assert declension("buxurnar", "buxur", "kvk") == (
        "buxurnar",
        "buxurnar",
        "buxunum",
        "buxnanna",
    )
    assert declension("ríkin", "ríki", "hk") == (
        "ríkin",
        "ríkin",
        "ríkjunum",
        "ríkjanna",
    )
    assert declension("Vestur-Þýskalands", "Vestur-Þýskaland", "hk") == (
        "Vestur-Þýskaland",
        "Vestur-Þýskaland",
        "Vestur-Þýskalandi",
        "Vestur-Þýskalands",
    )


def test_bindb() -> None:
    db = GreynirBin()
    # Test the lemma lookup functionality
    w, m = db.lookup_lemmas("eignast")
    assert w == "eignast"
    assert len(m) > 0
    assert m[0].ord == "eigna"
    w, m = db.lookup_lemmas("ábyrgjast")
    assert w == "ábyrgjast"
    assert len(m) > 0
    assert m[0].ord == "ábyrgjast"
    w, m = db.lookup_lemmas("ábyrgja")
    assert w == "ábyrgja"
    assert len(m) > 0
    assert m[0].ord == "á-byrgja"
    w, m = db.lookup_lemmas("ábyrgir")
    assert w == "ábyrgir"
    assert len(m) == 0
    w, m = db.lookup_lemmas("stór")
    assert w == "stór"
    assert len(m) > 0
    assert m[0].ord == "stór"
    w, m = db.lookup_lemmas("stórar")
    assert w == "stórar"
    assert len(m) == 0
    w, m = db.lookup_lemmas("sig")
    assert w == "sig"
    assert len(m) > 0
    assert any(mm.ofl == "abfn" for mm in m)
    w, m = db.lookup_lemmas("sér")
    assert w == "sér"
    assert len(m) > 0
    assert not any(mm.ofl == "abfn" for mm in m)
    w, m = db.lookup_lemmas("hann")
    assert w == "hann"
    assert len(m) > 0
    assert any(mm.ofl == "pfn" for mm in m)
    w, m = db.lookup_lemmas("hán")
    assert w == "hán"
    assert len(m) > 0
    assert any(mm.ofl == "pfn" for mm in m)
    w, m = db.lookup_lemmas("háns")
    assert w == "háns"
    assert len(m) == 0
    w, m = db.lookup_lemmas("hinn")
    assert w == "hinn"
    assert len(m) > 0
    assert any(mm.ofl == "gr" for mm in m)
    w, m = db.lookup_lemmas("einn")
    assert w == "einn"
    assert len(m) > 0
    assert any(mm.ofl == "lo" for mm in m)
    assert any(mm.ofl == "fn" for mm in m)
    w, m = db.lookup_lemmas("núll")
    assert w == "núll"
    assert len(m) > 0
    assert any(mm.ofl == "töl" for mm in m)
    assert any(mm.ofl == "hk" for mm in m)


def test_compounds() -> None:
    db = Bin()
    _, m = db.lookup("fjármála- og efnahagsráðherra")
    assert m
    assert m[0].ord == "fjármála- og efnahags-ráðherra"
    assert m[0].bmynd == "fjármála- og efnahags-ráðherra"

    _, m = db.lookup("tösku- og hanskabúðina")
    assert m
    assert m[0].ord == "tösku- og hanskabúð"
    assert m[0].bmynd == "tösku- og hanskabúðina"

    _, m = db.lookup("Félags- og barnamálaráðherra")
    assert m
    assert m[0].ord == "Félags- og barnamála-ráðherra"
    assert m[0].bmynd == "Félags- og barnamála-ráðherra"

    _, m = db.lookup("Félags- og Barnamálaráðherra")  # sic
    assert m
    assert m[0].ord == "Félags- og barnamála-ráðherra"
    assert m[0].bmynd == "Félags- og barnamála-ráðherra"

    cats = db.lookup_cats("færi")
    assert set(cats) == {"hk", "lo", "so"}

    lc = db.lookup_lemmas_and_cats("færi")
    assert set(lc) == {("færi", "hk"), ("fær", "lo"), ("fara", "so"), ("færa", "so")}

    cats = db.lookup_cats("borgarstjórnarmeirihlutinn")
    assert set(cats) == {"kk"}

    cats = db.lookup_lemmas_and_cats("borgarstjórnarmeirihlutinn")
    assert set(cats) == {("borgarstjórnar-meirihluti", "kk")}

    cats = db.lookup_cats("xyz")
    assert set(cats) == set()

    lc = db.lookup_lemmas_and_cats("xyz")
    assert set(lc) == set()

    cats = db.lookup_cats("Vestur-Þýskalands")
    assert set(cats) == {"hk"}

    lc = db.lookup_lemmas_and_cats("Vestur-Þýskalands")
    assert set(lc) == {("Vestur-Þýskaland", "hk")}

    cats = db.lookup_cats("Fjármála- og efnahagsráðherranna")
    assert set(cats) == {"kk"}

    lc = db.lookup_lemmas_and_cats("Fjármála- og efnahagsráðherranna")
    assert set(lc) == {("Fjármála- og efnahags-ráðherra", "kk")}

    cats = db.lookup_cats("fjármála- og efnahagsráðherranna")
    assert set(cats) == {"kk"}

    lc = db.lookup_lemmas_and_cats("fjármála- og efnahagsráðherranna")
    assert set(lc) == {("fjármála- og efnahags-ráðherra", "kk")}


def test_key() -> None:
    db = Bin()
    w, m = db.lookup("Farmiðasala")
    assert w == "farmiðasala"
    assert all(mm.ord in ("far-miðasala", "far-miðasali") for mm in m)
    w, m = db.lookup("farmiðasala")
    assert w == "farmiðasala"
    assert all(mm.ord in ("far-miðasala", "far-miðasali") for mm in m)
    w, m = db.lookup("lízt")
    assert w == "líst"
    assert all(mm.ord == "líta" for mm in m)
    w, m = db.lookup("Fjármála- og efnahagsráðherrans")
    assert w == "Fjármála- og efnahagsráðherrans"
    assert all(mm.ord == "Fjármála- og efnahags-ráðherra" for mm in m)
    w, m = db.lookup("Ytri-Hnausum")
    assert w == "Ytri-Hnausum"
    assert all(mm.ord == "Ytri-Hnaus" for mm in m)


def test_compatibility() -> None:
    db_bin = Bin()
    db_greynir = GreynirBin()
    _, m = db_bin.lookup("sig")
    assert any(mm.ofl == "afn" for mm in m)
    _, m = db_greynir.lookup("sig")
    assert any(mm.ofl == "abfn" for mm in m)
    _, m = db_bin.lookup("mig")
    assert any(mm.ofl == "hk" for mm in m)
    _, m = db_greynir.lookup("mig")
    assert all(mm.ofl != "hk" for mm in m)
    _, m = db_bin.lookup("versta")
    assert any(mm.ofl == "kvk" for mm in m)
    _, m = db_greynir.lookup("versta")
    assert all(mm.ofl != "kvk" for mm in m)
    _, m = db_bin.lookup("Öryggisráð")
    assert any(mm.bmynd.startswith("Ö") for mm in m)
    _, m = db_greynir.lookup("Öryggisráð")
    assert m and all(mm.bmynd.startswith("ö") for mm in m)
    _, m = db_greynir.lookup("ánægja")
    assert m and all(mm.ofl != "so" for mm in m)
    _, m = db_greynir.lookup("slæmur")
    assert m and all(mm.ofl != "kk" for mm in m)
    _, m = db_greynir.lookup("Ísland")
    assert m and all(mm.hluti == "lönd" for mm in m)
    _, m = db_greynir.lookup("Melasveit")
    assert m and all(mm.ofl == "kvk" and mm.hluti == "örn" for mm in m)
    _, m = db_greynir.lookup("Svartitangi")
    assert m and all(mm.ofl == "kk" and mm.hluti == "örn" for mm in m)
    _, m = db_greynir.lookup("Óðinsvé")
    assert m and all(mm.ofl == "hk" and mm.hluti == "örn" for mm in m)
    _, m = db_greynir.lookup("Jesús")
    assert m and all(mm.ofl == "kk" and mm.hluti == "erm" for mm in m)
    _, m = db_bin.lookup("aftur á bak")
    assert len(m) > 0
    _, m = db_greynir.lookup("aftur á bak")
    assert len(m) > 0
    _, m = db_bin.lookup("aðdáununum")
    assert len(m) == 0
    _, m = db_greynir.lookup("aðdáununum")
    assert len(m) > 0
    _, m = db_bin.lookup("þurrhreinsanirnar")
    assert len(m) == 0
    _, m = db_greynir.lookup("þurrhreinsanirnar")
    assert m and any(mm.ofl == "kvk" for mm in m)
    _, m = db_greynir.lookup("merkikertisyrðunum")
    assert m and all(mm.ofl == "hk" for mm in m)
    _, m = db_bin.lookup("merkikertisyrðunum")
    assert m and all(mm.ofl == "hk" for mm in m)
    _, m = db_greynir.lookup("sexdagsleikanum")
    assert m and all(mm.ofl == "kk" for mm in m)
    _, m = db_bin.lookup("sexdagsleikanum")
    assert m and all(mm.ofl == "kk" for mm in m)
    _, m = db_bin.lookup_ksnid("yrðunum")
    assert len(m) == 0
    _, m = db_greynir.lookup_ksnid("yrðunum")
    assert len(m) == 0
    _, m = db_bin.lookup_ksnid("leikanum")
    assert len(m) == 0
    _, m = db_greynir.lookup_ksnid("leikanum")
    assert len(m) == 0
    _, m = db_bin.lookup("yrðunum")
    assert len(m) == 0
    _, m = db_greynir.lookup("yrðunum")
    assert len(m) == 0
    _, m = db_bin.lookup("leikanum")
    assert len(m) == 0
    _, m = db_greynir.lookup("leikanum")
    assert len(m) == 0
    _, m = db_bin.lookup("kattarkjólsins")
    assert m and all(mm.ofl == "kk" for mm in m)
    db_bin = Bin(add_compounds=False)
    _, m = db_bin.lookup("merkikertisyrðunum")
    assert len(m) == 0
    _, m = db_bin.lookup("kattarkjólsins")
    assert len(m) == 0
    _, m = db_bin.lookup("sexdagsleikanum")
    assert len(m) == 0
    m = db_bin.lookup_variants("aðdáunin", "kvk", "FT")
    assert len(m) == 0
    m = db_greynir.lookup_variants("aðdáunin", "kvk", "FT")
    assert m and all(mm.bmynd == "aðdáanirnar" for mm in m)
    m = db_bin.lookup_variants("yrðið", "hk", "FT")
    assert len(m) == 0
    m = db_greynir.lookup_variants("yrðið", "hk", "FT")
    assert len(m) == 0
    m = db_bin.lookup_variants("merkikertisyrðið", "hk", "FT")
    assert len(m) == 0
    m = db_greynir.lookup_variants("merkikertisyrðið", "hk", "FT")
    assert m and all(mm.bmynd == "merkikertis-yrðin" for mm in m)


def test_legur() -> None:
    db = Bin()
    _, m = db.lookup("forritunarvillulegur")
    assert any(mm.ofl == "lo" and mm.ord.endswith("legur") for mm in m)
    _, m = db.lookup("forritunarvilluleg")
    assert any(mm.ofl == "lo" and mm.ord.endswith("legur") for mm in m)
    _, m = db.lookup("forritunarvillulegt")
    assert any(mm.ofl == "lo" and mm.ord.endswith("legur") for mm in m)
    _, m = db.lookup("forritunarvillulegir")
    assert any(mm.ofl == "lo" and mm.ord.endswith("legur") for mm in m)
    _, m = db.lookup("forritunarvillulegar")
    assert any(mm.ofl == "lo" and mm.ord.endswith("legur") for mm in m)
    _, m = db.lookup("forritunarvillulegu")
    assert any(mm.ofl == "lo" and mm.ord.endswith("legur") for mm in m)
    db = Bin(add_legur=False)
    _, m = db.lookup("forritunarvillulegur")
    assert all(mm.ofl != "lo" for mm in m)
    _, m = db.lookup("forritunarvilluleg")
    assert all(mm.ofl != "lo" for mm in m)
    _, m = db.lookup("forritunarvillulegt")
    assert all(mm.ofl != "lo" for mm in m)
    _, m = db.lookup("forritunarvillulegir")
    assert all(mm.ofl != "lo" for mm in m)
    _, m = db.lookup("forritunarvillulegar")
    assert all(mm.ofl != "lo" for mm in m)
    _, m = db.lookup("forritunarvillulegu")
    assert all(mm.ofl != "lo" for mm in m)
    db = GreynirBin()
    _, m = db.lookup("forritunarvillulegur")
    assert any(mm.ofl == "lo" and mm.ord.endswith("legur") for mm in m)
    _, m = db.lookup("forritunarvilluleg")
    assert any(mm.ofl == "lo" and mm.ord.endswith("legur") for mm in m)
    _, m = db.lookup("forritunarvillulegt")
    assert any(mm.ofl == "lo" and mm.ord.endswith("legur") for mm in m)
    _, m = db.lookup("forritunarvillulegir")
    assert any(mm.ofl == "lo" and mm.ord.endswith("legur") for mm in m)
    _, m = db.lookup("forritunarvillulegar")
    assert any(mm.ofl == "lo" and mm.ord.endswith("legur") for mm in m)
    _, m = db.lookup("forritunarvillulegu")
    assert any(mm.ofl == "lo" and mm.ord.endswith("legur") for mm in m)


def test_casting() -> None:
    """ Test functions to cast words in nominative case to other cases """
    db = Bin()

    assert db.cast_to_accusative("") == ""
    assert db.cast_to_dative("") == ""
    assert db.cast_to_genitive("") == ""

    assert db.cast_to_accusative("xxx") == "xxx"
    assert db.cast_to_dative("xxx") == "xxx"
    assert db.cast_to_genitive("xxx") == "xxx"

    assert db.cast_to_accusative("maðurinn") == "manninn"
    assert db.cast_to_dative("maðurinn") == "manninum"
    assert db.cast_to_genitive("maðurinn") == "mannsins"

    assert db.cast_to_accusative("mennirnir") == "mennina"
    assert db.cast_to_dative("mennirnir") == "mönnunum"
    assert db.cast_to_genitive("mennirnir") == "mannanna"

    assert db.cast_to_accusative("framkvæma") == "framkvæma"
    assert db.cast_to_dative("framkvæma") == "framkvæma"
    assert db.cast_to_genitive("framkvæma") == "framkvæma"

    assert db.cast_to_accusative("stóru") == "stóru"
    assert db.cast_to_dative("stóru") == "stóru"
    assert db.cast_to_genitive("stóru") == "stóru"

    assert db.cast_to_accusative("stóri") == "stóra"
    assert db.cast_to_dative("stóri") == "stóra"
    assert db.cast_to_genitive("stóri") == "stóra"

    assert db.cast_to_accusative("kattarhestur") == "kattarhest"
    assert db.cast_to_dative("kattarhestur") == "kattarhesti"
    assert db.cast_to_genitive("kattarhestur") == "kattarhests"

    assert db.cast_to_accusative("Kattarhestur") == "Kattarhest"
    assert db.cast_to_dative("Kattarhestur") == "Kattarhesti"
    assert db.cast_to_genitive("Kattarhestur") == "Kattarhests"

    f: BinFilterFunc = lambda mm: [m for m in mm if "2" not in m.mark]
    assert db.cast_to_accusative("fjórir", filter_func=f) == "fjóra"
    assert db.cast_to_dative("fjórir", filter_func=f) == "fjórum"
    assert db.cast_to_genitive("fjórir", filter_func=f) == "fjögurra"

    assert db.cast_to_accusative("Suður-Afríka") == "Suður-Afríku"
    assert db.cast_to_dative("Suður-Afríka") == "Suður-Afríku"
    assert db.cast_to_genitive("Suður-Afríka") == "Suður-Afríku"

    assert db.cast_to_accusative("Vestur-Þýskaland") == "Vestur-Þýskaland"
    assert db.cast_to_dative("Vestur-Þýskaland") == "Vestur-Þýskalandi"
    assert db.cast_to_genitive("Vestur-Þýskaland") == "Vestur-Þýskalands"

    f: BinFilterFunc = lambda mm: sorted(
        mm, key=lambda m: "2" in m.mark or "3" in m.mark
    )
    assert db.cast_to_accusative("Kópavogur", filter_func=f) == "Kópavog"
    assert db.cast_to_dative("Kópavogur", filter_func=f) == "Kópavogi"
    assert db.cast_to_genitive("Kópavogur", filter_func=f) == "Kópavogs"

    assert (
        db.cast_to_genitive("borgarstjórnarofurmeirihlutinn")
        == "borgarstjórnarofurmeirihlutans"
    )


def test_forms():
    db = Bin()
    l: List[BinEntry]
    l = db.lookup_forms("köttur", "kvk", "nf")
    assert len(l) == 0
    l = db.lookup_forms("köttur", "kzk", "nf")
    assert len(l) == 0
    try:
        l = []
        l = db.lookup_forms("köttur", "kk", "zf")
    except AssertionError:
        pass
    assert len(l) == 0
    l = db.lookup_forms("kötur", "kk", "nf")
    assert len(l) == 0
    l = db.lookup_forms("kettirnir", "kk", "nf")
    assert len(l) == 0
    l = db.lookup_forms("köttur", "kk", "nf")
    om = set(m.bmynd for m in l)
    assert "köttur" in om
    assert "kettir" in om
    assert "kötturinn" in om
    assert "kettirnir" in om
    l = db.lookup_forms("köttur", "kk", "þf")
    om = set(m.bmynd for m in l)
    assert "kött" in om
    assert "ketti" in om
    assert "köttinn" in om
    assert "kettina" in om
    l = db.lookup_forms("köttur", "kk", "þgf")
    om = set(m.bmynd for m in l)
    assert "ketti" in om
    assert "köttum" in om
    assert "kettinum" in om
    assert "köttunum" in om
    l = db.lookup_forms("köttur", "kk", "ef")
    om = set(m.bmynd for m in l)
    assert "kattar" in om
    assert "kattarins" in om
    assert "katta" in om
    assert "kattanna" in om


def test_variants() -> None:
    b = Bin()

    m = b.lookup_variants("borgarstjórnin", "no", "EF")
    assert all(mm.bmynd == "borgarstjórnarinnar" for mm in m)
    m = b.lookup_variants("borgarstjórnin", "kvk", "EF")
    assert all(mm.bmynd == "borgarstjórnarinnar" for mm in m)
    m = b.lookup_variants("borgarstjórnin", "hk", "EF")
    assert not m
    m = b.lookup_variants("borgarstjórnin", "no", ("EF", "nogr"))
    assert all(mm.bmynd == "borgarstjórnar" for mm in m)
    m = b.lookup_variants("borgarstjórnin", "kvk", ("EF", "nogr"))
    assert all(mm.bmynd == "borgarstjórnar" for mm in m)
    m = b.lookup_variants("borgarstjórnin", "hk", ("EF", "nogr"))
    assert not m
    m = b.lookup_variants("borgarstjórnin", "no", ("EF", "FT"))
    assert all(mm.bmynd == "borgarstjórnanna" for mm in m)
    m = b.lookup_variants("borgarstjórnin", "kvk", ("EF", "FT"))
    assert all(mm.bmynd == "borgarstjórnanna" for mm in m)
    m = b.lookup_variants("borgarstjórnin", "kk", ("EF", "FT"))
    assert not m
    m = b.lookup_variants("borgarstjórn", "no", ("EF", "gr"))
    assert all(mm.bmynd == "borgarstjórnarinnar" for mm in m)
    m = b.lookup_variants("borgarstjórn", "kvk", ("EF", "gr"))
    assert all(mm.bmynd == "borgarstjórnarinnar" for mm in m)
    m = b.lookup_variants("borgarstjórn", "kk", ("EF", "gr"))
    assert not m
    m = b.lookup_variants("borgarstjórn", "no", ("EF", "FT", "gr"))
    assert all(mm.bmynd == "borgarstjórnanna" for mm in m)
    m = b.lookup_variants("borgarstjórn", "kvk", ("EF", "FT", "gr"))
    assert all(mm.bmynd == "borgarstjórnanna" for mm in m)
    m = b.lookup_variants("borgarstjórn", "kk", ("EF", "FT", "gr"))
    assert not m
    m = b.lookup_variants("borgarstjórn", "no", ("EF", "FT", "nogr"))
    assert all(mm.bmynd == "borgarstjórna" for mm in m)
    m = b.lookup_variants("borgarstjórn", "kvk", ("EF", "FT", "nogr"))
    assert all(mm.bmynd == "borgarstjórna" for mm in m)
    m = b.lookup_variants("borgarstjórn", "kk", ("EF", "FT", "nogr"))
    assert not m

    m = b.lookup_variants("fór", "so", ("VH", "ÞT"), lemma="fara")
    assert all(mm.bmynd == "færi" for mm in m)
    m = b.lookup_variants("fór", "so", ("VH", "NT"), lemma="fara")
    assert all(mm.bmynd == "fari" for mm in m)
    m = b.lookup_variants(
        "fór",
        "so",
        ("VH", "FT", "NT", "1P"),
        lemma="fara",
        inflection_filter=lambda b: "OP" not in b,
    )
    assert all(mm.bmynd == "förum" for mm in m)
    m = b.lookup_variants(
        "fór",
        "so",
        ("VH", "FT", "ÞT", "1P"),
        lemma="fara",
        inflection_filter=lambda b: "OP" not in b,
    )
    assert all(mm.bmynd == "færum" for mm in m)
    m = b.lookup_variants(
        "fór",
        "so",
        ("vh", "ft", "þt", "p1"),
        lemma="fara",
        inflection_filter=lambda b: "OP" not in b,
    )
    assert all(mm.bmynd == "færum" for mm in m)
    m = b.lookup_variants("fór", "so", ("NT",), lemma="fara")
    assert all(mm.bmynd == "fer" for mm in m)
    m = b.lookup_variants("fór", "so", ("MM",), lemma="fara")
    assert all(mm.bmynd == "fórst" for mm in m)
    m = b.lookup_variants("fór", "so", ("MM", "NT"), lemma="fara")
    assert all(mm.bmynd == "ferst" for mm in m)
    m = b.lookup_variants(
        "fór",
        "so",
        ("MM", "NT", "2P", "FT"),
        lemma="fara",
        inflection_filter=lambda b: "OP" not in b,
    )
    assert all(mm.bmynd == "farist" for mm in m)
    m = b.lookup_variants(
        "fór",
        "so",
        ("MM", "NT", "p2", "FT"),
        lemma="fara",
        inflection_filter=lambda b: "OP" not in b,
    )
    assert all(mm.bmynd == "farist" for mm in m)
    m = b.lookup_variants("skrifar", "so", ("ÞT", "1P"))
    assert all(mm.bmynd == "skrifaði" for mm in m)
    m = b.lookup_variants("skrifar", "so", ("ÞT", "2P"))
    assert all(mm.bmynd == "skrifaðir" for mm in m)
    m = b.lookup_variants("skrifuðu", "so", ("FH", "ET", "NT"))
    assert all(mm.bmynd == "skrifar" for mm in m)
    m = b.lookup_variants("skrifuðu", "so", "LHNT")
    assert all(mm.bmynd == "skrifandi" for mm in m)

    m = b.lookup_variants("fallegur", "lo", "MST")
    assert all(mm.bmynd == "fallegri" for mm in m)
    m = b.lookup_variants("fallegur", "lo", ("MST", "HK"))
    assert all(mm.bmynd == "fallegra" for mm in m)
    m = b.lookup_variants("fallegur", "lo", ("MST", "KVK"))
    assert all(mm.bmynd == "fallegri" for mm in m)
    m = b.lookup_variants("fallegur", "lo", "EVB")
    assert all(mm.bmynd == "fallegasti" for mm in m)
    m = b.lookup_variants("fallegur", "lo", "ESB")
    assert all(mm.bmynd == "fallegastur" for mm in m)
    m = b.lookup_variants("fallegur", "lo", ("EVB", "KVK"))
    assert all(mm.bmynd == "fallegasta" for mm in m)
    m = b.lookup_variants("fallegur", "lo", ("ESB", "KVK"))
    assert all(mm.bmynd == "fallegust" for mm in m)
    m = b.lookup_variants("fallegur", "lo", ("EVB", "HK"))
    assert all(mm.bmynd == "fallegasta" for mm in m)
    m = b.lookup_variants("fallegur", "lo", ("ESB", "HK"))
    assert all(mm.bmynd == "fallegast" for mm in m)

    m = b.lookup_variants("höfuðborgarstjórnarmeirihluti", "kk", ("ÞF", "FT", "gr"))
    assert len(m) == 1
    assert m[0].bmynd == "höfuð-borgarstjórnar-meirihlutana"

    m = b.lookup_variants("höndinni", "kvk", ("NF", "nogr"))
    assert len(m) == 1
    assert m[0].bmynd == "hönd"

    m = b.lookup_variants("hendinni", "kvk", ("NF", "nogr"))
    assert len(m) == 1
    assert m[0].bmynd == "hönd"

    m = b.lookup_variants("langifrjádagur", "kk", ("NF", "FT"))
    assert len(m) == 1
    assert m[0].bmynd == "löngufrjádagar"

    m = b.lookup_variants("langifrjádagur", "kk", ("EF", "FT", "gr"))
    assert len(m) == 1
    assert m[0].bmynd == "löngufrjádaganna"

    # Test lower case variant specifications (should also work)
    m = b.lookup_variants("langifrjádagur", "kk", ("nf", "ft"))
    assert len(m) == 1
    assert m[0].bmynd == "löngufrjádagar"

    m = b.lookup_variants("langifrjádagur", "kk", ("ef", "ft", "gr"))
    assert len(m) == 1
    assert m[0].bmynd == "löngufrjádaganna"

    m = b.lookup_variants("langifrjádagurinn", "kk", ("ef", "ft", "nogr"))
    assert len(m) == 1
    assert m[0].bmynd == "löngufrjádaga"

    m = b.lookup_variants("sjóntækjafræðinga", "no", ("ef", "gr"))
    assert len(m) == 1
    assert m[0].bmynd == "sjóntækjafræðinganna"

    m = b.lookup_variants("margborga", "so", ("expl", "et", "nt"))
    assert len(m) == 1
    assert m[0].bmynd == "margborgar"

    m = b.lookup_variants("margborga", "so", ("expl", "et", "þt"))
    assert len(m) == 1
    assert m[0].bmynd == "margborgaði"

    m = b.lookup_variants("margborga", "so", ("expl", "et", "þt", "vh"))
    assert len(m) == 1
    assert m[0].bmynd == "margborgaði"

    m = b.lookup_variants("margborga", "so", ("expl", "et", "nt", "vh"))
    assert len(m) == 1
    assert m[0].bmynd == "margborgi"

    m = b.lookup_variants("margborgi", "so", ("expl", "þt", "gm"))
    assert len(m) == 1
    assert m[0].bmynd == "margborgaði"

    m = b.lookup_variants("smíða", "so", ("expl", "et", "nt"))
    assert len(m) == 0

    m = b.lookup_variants("smíðar", "so", ("expl", "et", "nt"))
    assert len(m) == 0


def test_sorting() -> None:
    b = Bin()
    assert b.lookup_ksnid("arfa")[1][0].ofl == "kk"
    assert b.lookup_ksnid("arfa")[1][-1].ofl == "kvk"


def test_id() -> None:
    b = Bin()

    k = b.lookup_id(495410)
    assert len(k) == 1
    assert k[0].bin_id == 495410
    assert k[0].ofl == "uh"
    assert k[0].ord == "sko"

    k = b.lookup_id(495754)
    assert len(k) == 1
    assert k[0].bin_id == 495754
    assert k[0].ofl == "ao"
    assert k[0].ord == "sko"

    k = b.lookup_id(416784)  # 'köttur'
    assert len(k) == 17
    assert all(item.bin_id == 416784 for item in k)
    assert all(item.ord == "köttur" for item in k)
    assert all(item.ofl == "kk" for item in k)

    assert b.lookup_id(-100) == []  # No such bin_id
    assert b.lookup_id(77) == []  # No such bin_id
    assert b.lookup_id(1000000) == []  # No such bin_id


if __name__ == "__main__":

    test_lookup()
    test_bin()
    test_bindb()
    test_compounds()
    test_legur()
    test_casting()
    test_forms()
    test_sorting()
    test_id()
