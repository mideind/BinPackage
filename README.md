# BinPackage

**The Database of Modern Icelandic Inflection (DMII, BÍN) encapsulated in a Python package**

[![Python package](https://github.com/mideind/BinPackage/actions/workflows/python-package.yml/badge.svg)](https://github.com/mideind/BinPackage/actions/workflows/python-package.yml)

![GitHub](https://img.shields.io/github/license/mideind/BinPackage)
![Python 3.6+](https://img.shields.io/badge/python-3.6-blue.svg)

<img src="img/greynir-logo-large.png" alt="Greynir" width="200" height="200" align="right" style="margin-left:20px; margin-bottom: 20px;">

*BinPackage* is a Python package that embeds the entire *Database of Modern Icelandic*
*Inflection* (*Beygingarlýsing íslensks nútímamáls*, *BÍN*) and allows various
queries of the data.

The database contains over 6.5 million entries, over 3.1 million unique word forms,
and about 300 thousand distinct lemmas. It has been compressed from a 400+ megabyte
CSV file to a ~80 megabyte indexed binary structure that is mapped directly into memory
for fast lookup and efficient memory usage.

This means that `pip install islenska` is all you need to have most of the
vocabulary of the Icelandic language at your disposal via Python. Batteries
are included; no additional databases or middleware are required.

BinPackage allows querying for word forms, as well as lemmas and grammatical variants.
This includes information about word categories (noun, verb, ...),
subcategories (person names,
place names, ...), inflection paradigms and various annotations, such as degrees of
linguistic acceptability and alternate spelling forms.

BinPackage is fully type-annotated for use with Python static type checkers such
as `mypy` and `Pylance` / `Pyright`.

## BÍN 101

The BÍN database is available for download in CSV files in two main formats:
*Sigrúnarsnið* (`SHsnid`) and
*Kristínarsnið* (`Ksnid`). Sigrúnarsnið is more compact with 6 attributes
for each word form. Kristínarsnið, documented
[here](https://bin.arnastofnun.is/gogn/k-snid), is newer and more detailed,
with up to 15 attributes for each word form.

BinPackage supports both formats, with `Ksnid` being returned from functions
whose names end with `_ksnid`, and `SHsnid` from others.

SHsnid is represented with a Python `NamedTuple` called `BinMeaning`, which
has the following attributes:

| Name     | Type  | Content                    |
|----------|-------|----------------------------|
| `stofn`  | `str` | The lemma of the word form (*uppflettiorð*) |
| `utg`    | `int` | The issue number (*útgáfunúmer*) of the lemma, unique for a particular lemma/category combination |
| `ordfl`  | `str` | The category of the lemma, i.e. `kk`/`kvk`/`hk` for nouns, `lo` for adjectives, `so` for verbs, etc.|
| `fl`     | `str` | The subcategory of the lemma, i.e. `alm` for general vocabulary, `ism` for Icelandic person names, `örn` for place names (*örnefni*), etc.|
| `ordmynd` | `str` | The word form |
| `beyging` | `str` | The inflection paradigm of the word form, for instance `ÞGFETgr` for dative (*þágufall*, `ÞGF`), singular (*eintala*, `ET`), definite (*með greini*, `gr`) |

The inflection paradigms in the `beyging` attribute are documented in detail [here](https://bin.arnastofnun.is/gogn/greiningarstrengir/).

`Ksnid` is represented by instances of the `Ksnid` class. It adds the following
9 attributes:

| Name     | Type  | Content                    |
|----------|-------|----------------------------|
| `einkunn` | `int` | A general linguistic acceptability metric, ranging from 0-5. |
| `malsnid` | `str` | An indicator of origin and style; e.g. `STAD` for local and `URE` for deprecated. |
| `malfraedi` | `str` | Grammatical markings, such as `KYN` for dubious gender. |
| `millivisun` | `int` | Reference to the `utg` number of a related lemma. |
| `birting` | `str` | `K` for the BÍN *kernel* of most common and accepted word forms, `V` for other published BÍN entries. |
| `beinkunn` | `int` | An inflectional acceptability metric, ranging from 0-5. |
| `bmalsnid` | `str` | An indicator of origin and style for this inflectional form. |
| `bgildi` | `str` | |
| `aukafletta` | `str` | Another, related lemma, e.g. plural form |


## Examples

### Querying for word forms

*Uppfletting beygingarmynda*

```python
>>> from islenska import Bin
>>> b = Bin()
>>> b.lookup("færi")
('færi', [
(stofn='fara', so/alm/433568, ordmynd='færi', OP-ÞGF-GM-VH-ÞT-1P-ET),
(stofn='fara', so/alm/433568, ordmynd='færi', OP-ÞGF-GM-VH-ÞT-1P-FT),
(stofn='fara', so/alm/433568, ordmynd='færi', OP-ÞGF-GM-VH-ÞT-2P-ET),
(stofn='fara', so/alm/433568, ordmynd='færi', OP-ÞGF-GM-VH-ÞT-2P-FT),
(stofn='fara', so/alm/433568, ordmynd='færi', OP-ÞGF-GM-VH-ÞT-3P-ET),
(stofn='fara', so/alm/433568, ordmynd='færi', OP-það-GM-VH-ÞT-3P-ET),
(stofn='fara', so/alm/433568, ordmynd='færi', OP-ÞGF-GM-VH-ÞT-3P-FT),
(stofn='fara', so/alm/433568, ordmynd='færi', GM-VH-ÞT-1P-ET),
(stofn='fara', so/alm/433568, ordmynd='færi', GM-VH-ÞT-3P-ET),
(stofn='fær', lo/alm/448392, ordmynd='færi', FVB-KK-NFET),
(stofn='færa', so/alm/434742, ordmynd='færi', GM-FH-NT-1P-ET),
(stofn='færa', so/alm/434742, ordmynd='færi', GM-VH-NT-1P-ET),
(stofn='færa', so/alm/434742, ordmynd='færi', GM-VH-NT-3P-ET),
(stofn='færa', so/alm/434742, ordmynd='færi', GM-VH-NT-3P-FT),
(stofn='færi', hk/alm/1198, ordmynd='færi', NFET),
(stofn='færi', hk/alm/1198, ordmynd='færi', ÞFET),
(stofn='færi', hk/alm/1198, ordmynd='færi', ÞGFET),
(stofn='færi', hk/alm/1198, ordmynd='færi', NFFT),
(stofn='færi', hk/alm/1198, ordmynd='færi', ÞFFT)
])
```

`Bin.lookup()` returns the original lookup word
and a list of its possible meanings in a summary form (*Sigrúnarsnið*).
Each meaning tuple contains the
lemma (`stofn`), the category, subcategory and issue number (`hk/alm/1198`),
the word form (`ordmynd`) and the inflection paradigm (`GM-VH-NT-3P-FT`).
The inflection paradigm strings are [documented on the BÍN website](https://bin.arnastofnun.is/gogn/k-snid).

### Detailed word query

*Uppfletting ítarlegra upplýsinga*

```python
>>> from islenska import Bin
>>> b = Bin()
>>> w, m = b.lookup_ksnid("allskonar")
>>> m[0].malfraedi
'STAFS'
```

`Bin.lookup_ksnid()` returns the original lookup word
and a list of its possible meanings in a detailed format called
*Kristínarsnið* (`ksnid`). The fields of *Kristínarsnið* are
[documented on the BÍN website](https://bin.arnastofnun.is/gogn/k-snid).
In the example, we show how the word `allskonar` is marked with the
tag `STAFS` in the `malfraedi` field, indicating that this spelling
is nonstandard. A more correct form is `alls konar`, in two words.

### Word categories

*Orðflokkar*

```python
>>> from islenska import Bin
>>> b = Bin()
>>> b.lookup_cats("laga")
{'hk', 'so', 'kk'}
```

Here, we see that the word form *laga* can mean a neutral (`'hk'`) or
masculine (`'kk'`) noun, or a verb (`'so'`).

### Lemmas

*Lemmur*

```python
>>> from islenska import Bin
>>> b = Bin()
>>> b.lookup_lemmas_and_cats("laga")
{('lag', 'hk'), ('lög', 'hk'), ('laga', 'so'), ('lagi', 'kk'), ('lögur', 'kk')}
```

Here we see, perhaps unexpectedly, that the word form *laga* has five possible lemmas:
four nouns (*lag*, *lög*, *lagi* and *lögur*, neutral and masculine respectively),
and one verb (*laga*).

## Documentation

### Constructor

To create an instance of the Bin class, do as follows:

```python
>>> from islenska import Bin
>>> b = Bin()
```

You can optionally specify the following boolean flags in the `Bin()`
constructor call:

| Flag              | Default | Meaning                                        |
|-------------------|---------|------------------------------------------------|
| `add_negation`    | True    | For adjectives, find forms with the prefix `ó` even if only the non-prefixed version is present in BÍN. Example: find `ófíkinn` because `fíkinn` is in BÍN. |
| `add_legur`       | True    | For adjectives, find all forms with an "adjective-like" suffix, i.e. `-legur`, `-leg`, etc. even if they are not present in BÍN. Example: `sólarolíulegt`. |
| `add_compounds`   | True    | Find compound words that can be derived from BinPackage's collection of allowed prefixes and suffixes. The algorithm finds the compound word with the fewest components and the longest suffix. Example: `síamskattarkjóll`. |
| `replace_z`       | True    | Find words containing `tzt` and `z` by replacing these strings by `st` and `s`, respectively. Example: `veitzt` -> `veist`. |
| `only_bin`        | False   | Find only word forms that are originally present in BÍN, disabling all of the above described flags. |

As an example, to create an instance that only returns word forms that occur
in the original BÍN, do like so:

```python
>>> from islenska import Bin
>>> b = Bin(only_bin=True)
```

### Lookup function

To look up word forms, call the `lookup` function:

```python
>>> w, m = b.lookup("síamskattarkjólanna")
>>> w
'síamskattarkjólanna'
>>> m
[(stofn='síamskattar-kjóll', kk/alm/0, ordmynd='síamskattar-kjólanna', EFFTgr)]
```

Here we see that *síamskattarkjólanna* is a composite word, amalgamated
from *síamskattar* and *kjólanna*, with *kjóll* being the base lemma of the composite
word. This is a masculine noun (`kk`), of the `alm` (general) subcategory.
It has an issue number (*útgáfunúmer*) equal to 0 since it is constructed by
BinPackage, rather than being fetched directly from BÍN. The inflection
paradigm is `EFFTgr`, i.e. genitive (*eignarfall*, `EF`), plural (*fleirtala*,
`FT`) and definite (*með greini*, `gr`).


## Implementation

BinPackage is written in [Python 3](https://www.python.org/)
and requires Python 3.6 or later. It runs on CPython and [PyPy](http://pypy.org/).

The Python code calls a small C++ library to speed up lookup of word forms in the
compressed binary structure into which BÍN has been encoded.
This means that if a pre-compiled wheel is not
available on PyPI for your platform, you may need a set of development tools installed
on your machine, before you install BinPackage using `pip`:

```bash
$ # The following works on Debian/Ubuntu Linux
$ sudo apt-get install python3-dev libffi-dev
```

## Installation and setup

You must have Python >= 3.6 installed on your machine (CPython or PyPy).
If you are using a Python virtual environment (`virtualenv`), activate it first:

```bash
$ venv/bin/activate
```
...or, on Windows:
```
C:\> venv\scripts\activate
```

Then, install BinPackage from the Python Package Index (PyPI),
where the package is called `islenska`:

```bash
$ pip install islenska
```

Now, you are ready to `import islenska` or `from islenska import Bin`
in your Python code.

----

If you want to install the package in editable source code mode,
do as follows:

```bash
$ # Clone the GitHub repository
$ git clone https://github.com/mideind/BinPackage
$ cd BinPackage
$ # Install the package in editable mode
$ pip install -e .  # Note the dot!
$ cd src/islenska/resources
$ # Fetch the newest BÍN data (KRISTINsnid.csv.zip)
$ wget -O KRISTINsnid.csv.zip https://bin.arnastofnun.is/django/api/nidurhal/?file=KRISTINsnid.csv.zip
$ # Unzip the data
$ unzip KRISTINsnid.csv.zip
$ rm KRISTINsnid.csv.zip
$ cd ../../..
$ # Run the compressor to generate src/islenska/resources/compressed.bin
$ python tools/binpack.py
$ # Run the DAWG builder for the prefix and suffix files
$ python tools/dawgbuilder.py
$ # Now you're ready to go
```

This will clone the GitHub repository into the BinPackage directory,
and install the package into your Python environment from the source files.
Then, the newest BÍN data is fetched via `wget`
from *Stofnun Árna Magnússonar* and compressed into a binary file.
Finally, the Directed Acyclic Word Graph builder is run to
create DAWGs for word prefixes and suffixes, used by the compound word
algorithm.

## File details

The following files are located in the `src/islenska` directory within
BinPackage:

* `bindb.py`: The main `Bin` class; high-level interfaces into BinPackage.
* `bincompress.py`: The lower-level `BinCompressed` class, interacting directly with
  the compressed data in a binary buffer in memory.
* `basics.py`: Basic data structures, such as the `BinMeaning` NamedTuple.
* `dawgdictionary.py`: Classes that handle compound words.
* `bin.h`, `bin.cpp`: C++ code for fast lookup of word forms, called from Python via CFFI.
* `tools/binpack.py`: A command-line tool that reads vocabulary data in .CSV
  form and outputs a compressed binary file, `compressed.bin`.
* `tools/dawgbuilder.py`: A command-line tool that reads information about word prefixes and suffixes
  and creates corresponding directed acyclic word graph (DAWG) structures for
  the word compounding logic.
* `resources/prefixes.txt`, `resources/suffixes.txt`: Text files containing
  valid Icelandic word prefixes and suffixes, respectively.

## Copyright and licensing

BinPackage embeds the
**[Database of Modern Icelandic Inflection](https://bin.arnastofnun.is/)**
(**[Beygingarlýsing íslensks nútímamáls](https://bin.arnastofnun.is/)**),
abbreviated *BÍN*.

The BÍN source data are publicly available under the CC-BY-4.0 license,
as further detailed
[here in English](https://bin.arnastofnun.is/DMII/LTdata/conditions/) and
[here in Icelandic](https://bin.arnastofnun.is/gogn/mimisbrunnur/).

In accordance with the BÍN license terms, credit is hereby given as follows:

*Beygingarlýsing íslensks nútímamáls. Stofnun Árna Magnússonar í íslenskum fræðum.*
*Höfundur og ritstjóri Kristín Bjarnadóttir.*

----

BinPackage includes certain additions and modifications to the original
BÍN source data. These are explained in the source code file `tools/binpack.py`,
available in the project's GitHub repository.

----

BinPackage is Copyright (C) 2021 [Miðeind ehf.](https://mideind.is)
The original author of this software is *Vilhjálmur Þorsteinsson*.

<img src="img/MideindLogoVert400.png" alt="Miðeind ehf." width="118" height="100" align="left" style="margin-right:20px; margin-top: 10px; margin-bottom: 10px;">

This software is licensed under the **MIT License**:

*Permission is hereby granted, free of charge, to any person obtaining a*
*copy of this software and associated documentation files (the "Software"),*
*to deal in the Software without restriction, including without limitation*
*the rights to use, copy, modify, merge, publish, distribute, sublicense,*
*and/or sell copies of the Software, and to permit persons to whom the*
*Software is furnished to do so, subject to the following conditions:*

*The above copyright notice and this permission notice shall be included*
*in all copies or substantial portions of the Software.*

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

If you would like to use this software in ways that are incompatible with the
standard MIT license, [contact Miðeind ehf.](mailto:mideind@mideind.is) to negotiate custom arrangements.

