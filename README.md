# BinPackage

**The Database of Modern Icelandic Inflection (DMII, BÍN) encapsulated in a Python package**

[![Python package](https://github.com/mideind/BinPackage/actions/workflows/python-package.yml/badge.svg)](https://github.com/mideind/BinPackage/actions/workflows/python-package.yml)

![GitHub](https://img.shields.io/github/license/mideind/BinPackage)
![Python 3.6+](https://img.shields.io/badge/python-3.6-blue.svg)

<img src="img/greynir-logo-large.png" alt="Greynir" width="200" height="200" align="right" style="margin-left:20px; margin-bottom: 20px;">

*BinPackage* is a Python package that embeds the entire *Database of Modern Icelandic*
*Inflection* (*Beygingarlýsing íslensks nútímamáls*, *BÍN*) and allows various
queries of the data.

The database contains over 6,5 million entries, over 3,1 million unique word forms,
and about 300 thousand distinct lemmas. It has been compressed from a 400+ megabyte
CSV file to a ~80 megabyte indexed binary structure that is mapped directly into memory
for fast lookup and efficient memory usage.

BinPackage allows querying for word forms, as well as lemmas and grammatical variants,
yielding information about word categories (noun, verb, ...), subcategories (person names,
place names, ...), inflection paradigms and various annotations, such as degrees of
linguistic acceptability and alternate spelling forms.

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

`Bin.lookup()` returns a tuple containing the original lookup word
and a list of its possible meanings. Each meaning tuple contains the
lemma (`stofn`), the category, subcategory and id number (`hk/alm/1198`),
the word form (`ordmynd`) and the inflection paradigm (`GM-VH-NT-3P-FT`).
The inflection paradigm strings are [documented on the BÍN website](https://bin.arnastofnun.is/gogn/k-snid).

### Word categories

*Orðflokkar*

```python
>>> from islenska import Bin
>>> b = Bin()
>>> b.lookup_cats("laga")
>>> {'hk', 'so', 'kk'}
```

Here, we see that the word form *laga* can be a neutral (`'hk'`) or
masculine (`'kk'`) noun, or a verb (`'so'`).

### Lemmas

*Lemmur*

```python
>>> from islenska import Bin
>>> b = Bin()
>>> b.lookup_lemmas_and_cats("laga")
>>> {('lag', 'hk'), ('lög', 'hk'), ('laga', 'so'), ('lagi', 'kk'), ('lögur', 'kk')}
```

Here we see, perhaps unexpectedly, that the word form *laga* has five possible lemmas:
four nouns (*lag*, *lög*, *lagi* and *lögur*, neutral and masculine respectively),
and one verb (*laga*).

## Implementation

BinPackage is written in [Python 3](https://www.python.org/)
and requires Python 3.6 or later. It runs on CPython and [PyPy](http://pypy.org/).

## Installation and setup

You must have Python >= 3.6 installed on your machine.
If you are using a Python virtual environment (`virtualenv`), activate it first:

```bash
$ venv/bin/activate
```
...or, on Windows:
```
C:\> venv\scripts\activate
```

Then, install BinPackage from the Python Package Index (PyPi),
where the package is called `islenska`:

```bash
$ pip install islenska
```

Now, you are ready to `import islenska` or `from islenska import Bin`
in your Python code.

If you want to install the package in editable source code mode,
do as follows:

```bash
$ git clone https://github.com/mideind/BinPackage
$ cd BinPackage
$ pip install -e .  # Note the dot!
```

This will clone the GitHub repository into the BinPackage directory,
and install the package into
your environment from the source files. Now you can edit the source and
get immediate feedback on your changes in the code.

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

<img src="img/MideindLogoVert400.png" alt="Miðeind ehf." width="100" height="100" align="left" style="margin-right:20px; margin-top: 10px; margin-bottom: 10px;">

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

