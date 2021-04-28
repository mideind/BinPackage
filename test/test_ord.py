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

from islenska import Orð


def test_ord() -> None:

    o = Orð("lesa", "so")
    b = Orð("bók")

    assert f"Ég er að {o} {b:þf_gr}" == "Ég er að lesa bókina"
    assert f"Ég er að {o} {b:þf-gr}" == "Ég er að lesa bókina"
    assert f"Ég er að {o} {b:ÞF_gr}" == "Ég er að lesa bókina"
    assert f"Ég er að {o} {b:ÞF-gr}" == "Ég er að lesa bókina"
    assert f"Ég er að {o} {b:ÞF-nogr}" == "Ég er að lesa bók"
    assert f"Ég er að {o} {b:ÞF-FT-nogr}" == "Ég er að lesa bækur"
    assert f"Ég er að {o:nh} bókina" == "Ég er að lesa bókina"
    assert f"Ég er að {o:nh-nt} bókina" == "Ég er að lesa bókina"
    assert f"Ég er að {o:nh-ft} bókina" == "Ég er að lesa bókina"
    try:
        if f"Ég er að {o:nh-xx} bókina" == "Ég er að lesa bókina":
            assert False
    except ValueError:
        pass
    try:
        if f"Ég er að {o:nh_xx} bókina" == "Ég er að lesa bókina":
            assert False
    except ValueError:
        pass

    assert f"Ég hef {o:sagnb} bókina" == "Ég hef lesið bókina"

    assert f"Ég {o:vh_þt_p1_et} bókina" == "Ég læsi bókina"
    assert f"Þú {o:vh_þt_p2_et} bókina" == "Þú læsir bókina"
    assert f"Hún {o:VH_ÞT_3P_ET} bókina" == "Hún læsi bókina"
    assert f"Hún {o:VH-ÞT-3P-ET} bókina" == "Hún læsi bókina"

    l = Orð("frábær", "lo")
    assert f"Þessi pakki er alveg {l:kk-nf-et-fsb}!" == "Þessi pakki er alveg frábær!"
    assert f"Þessir pakkar eru alveg {l:kk-nf-ft-fsb}!" == "Þessir pakkar eru alveg frábærir!"

    assert f"Þessi {b:nf} er alveg {l:kvk-nf-et-fsb}!" == "Þessi bók er alveg frábær!"
    assert f"Þessar {b:nf-ft} eru alveg {l:kvk-nf-ft-fsb}!" == "Þessar bækur eru alveg frábærar!"

    assert f"Þessi {b:nf} er {l:kvk-nf-et-esb}!" == "Þessi bók er frábærust!"
    assert f"Þessar {b:nf-ft} eru {l:kvk-nf-ft-esb}!" == "Þessar bækur eru frábærastar!"

    b = Orð("Bók")

    assert f"{b:nf} er {l:kvk-nf-et-esb}!" == "Bók er frábærust!"
    assert f"{b:nf-ft} eru {l:kvk-nf-ft-esb}!" == "Bækur eru frábærastar!"
  
    assert f"{l:kvk-nf-et-evb} {b:nf-et-gr}!" == "frábærasta Bókin!"
    assert f"{l:kvk-nf-ft-evb} {b:nf-ft-gr}!" == "frábærustu Bækurnar!"
  
    b = Orð("BÓK")

    assert f"{b:nf} er {l:kvk-nf-et-esb}!" == "BÓK er frábærust!"
    assert f"{b:nf-ft} eru {l:kvk-nf-ft-esb}!" == "BÆKUR eru frábærastar!"

    b = Orð("Xxyy")
    assert f"{b:nf} er best" == "Xxyy er best"
    assert f"{b:vh_p3_nt} er best" == "Xxyy er best"

    b = Orð("XXYY")
    assert f"{b:nf} er best" == "XXYY er best"
    assert f"{b:vh_p3_nt} er best" == "XXYY er best"

    b = Orð("32409")
    assert f"{b:nf} er best" == "32409 er best"
    assert f"{b:vh_p3_nt} er best" == "32409 er best"

    b = Orð("")
    assert f"{b:nf} er best" == " er best"
    assert f"{b:vh_p3_nt} er best" == " er best"

    b = Orð(" bók ")
    assert f"{b:nf} er best" == " bók  er best"
    assert f"{b:nf_ft} eru bestar" == " bók  eru bestar"

    b = Orð("Vestur-Húnavatnssýsla")

    assert f"{b:nf} er {l:KVK-NF-ET-ESB}!" == "Vestur-Húnavatnssýsla er frábærust!"
    # assert f"{b:nf-ft} er {l:kvk-et-esb}!" == "Vestur-Húnavatnssýsla er frábærust!"

    assert f"Ég bý í {b:þgf}" == "Ég bý í Vestur-Húnavatnssýslu"
    # assert f"Ég bý í {b:þgf_gr}" == "Ég bý í Vestur-Húnavatnssýslunni"

    #b = Orð("VESTUR-HÚNAVATNSSÝSLA")
    #assert f"Ég bý í {b:þgf}" == "Ég bý í VESTUR-HÚNAVATNSSÝSLU"

    b = Orð("borgarstjórnarráðsfundur")
    assert f"Ég tók þátt í {b:þgf_gr}" == "Ég tók þátt í borgarstjórnarráðsfundinum"
    assert f"Ég saknaði {b:ef_gr}" == "Ég saknaði borgarstjórnarráðsfundarins"

    b = Orð("Borgarstjórnarráðsfundur")
    assert f"{b:ef_gr} var sárt saknað" == "Borgarstjórnarráðsfundarins var sárt saknað"

    g = Orð("Hinn", "gr")
    l = Orð("íslenskur")

    b = Orð("bókmenntafélag")
    assert f"{g:hk_nf} {l:hk_fvb_et} {b}" == "Hið íslenska bókmenntafélag"
    assert f"{g:hk_nf_ft} {l:hk_fvb_ft} {b:ft}" == "Hin íslensku bókmenntafélög"

    b = Orð("draumur")
    assert f"{g:kk_nf} {l:kk_fvb_et} {b}" == "Hinn íslenski draumur"
    assert f"{g:kk_nf_ft} {l:kk_fvb_ft} {b:ft}" == "Hinir íslensku draumar"

    b = Orð("draumsýn")
    assert f"{g:kvk_nf} {l:kvk_fvb_et} {b:nf_et}" == "Hin íslenska draumsýn"
    assert f"{g:kvk_nf_ft} {l:kvk_fvb_ft} {b:nf_ft}" == "Hinar íslensku draumsýnir"
