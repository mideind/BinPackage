# islenska-data

The vocabulary data of the [islenska](https://pypi.org/project/islenska/)
package ([BinPackage](https://github.com/mideind/BinPackage)): the
**[Database of Icelandic Morphology](https://bin.arnastofnun.is/DMII/)**
(**[Beygingarlýsing íslensks nútímamáls](https://bin.arnastofnun.is/)**,
*BÍN*) in the compressed form that islenska reads, together with the word
graphs (DAWGs) of its compound word algorithm.

This package has no functionality of its own. Install `islenska`, and it
finds its data here:

```python
>>> from islenska import Bin
>>> Bin().lookup("hestur")
```

The data are kept in a package of their own because they change only when
BÍN is updated, while the code changes more often: a release of islenska
then ships small wheels for each platform and Python implementation, and the
data are downloaded once.

## Versions

The major and minor version follow the data format of `compressed.bin`
(`Greynir 05.00.00` is 5.0); the patch number goes up with each release of
new BÍN data. A version of islenska works with any islenska-data release of
the data format it reads, and checks the format when it starts.

## Contents

| File | |
|---|---|
| `compressed.bin` | BÍN (KRISTINsnid), with Miðeind's additions for the Greynir parser, compressed. Compounds that the compound word algorithm regenerates exactly are left out and restored on lookup. |
| `ordalisti-all.dawg.bin`, `ordalisti-prefixes.dawg.bin`, `ordalisti-suffixes.dawg.bin` | The word graphs of the compound word algorithm. |

The files are built in the BinPackage repository by `tools/binpack.py` and
`tools/dawgbuilder.py`.

## Copyright and licensing

The copyright holder for BÍN is *The Árni Magnússon Institute*
*for Icelandic Studies*. The BÍN data used herein are publicly available
for use under the terms of the
[CC BY-SA 4.0 license](https://creativecommons.org/licenses/by-sa/4.0/legalcode),
as further detailed
[here in English](https://bin.arnastofnun.is/DMII/LTdata/conditions/) and
[here in Icelandic](https://bin.arnastofnun.is/gogn/mimisbrunnur/).

In accordance with the BÍN license terms, credit is hereby given as follows:

*Beygingarlýsing íslensks nútímamáls. Stofnun Árna Magnússonar í íslenskum fræðum.*
*Höfundur og ritstjóri Kristín Bjarnadóttir.*

**Miðeind ehf., the publisher of this package, claims no endorsement,**
**sponsorship, or official status granted to it by the BÍN copyright holder.**

The data files are an adaptation of BÍN (compressed, and with additions made
by Miðeind ehf. for its Greynir parser), distributed under the same CC BY-SA
4.0 license as BÍN itself. The Python code of this package is
Copyright © 2026 [Miðeind ehf.](https://mideind.is) and licensed under the
MIT License.
