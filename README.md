# BinPackage

**The Database of Modern Icelandic Inflection (DMII, BÍN) encapsulated in a Python package**

[![Python package](https://github.com/mideind/BinPackage/actions/workflows/python-package.yml/badge.svg)](https://github.com/mideind/BinPackage/actions/workflows/python-package.yml)

![GitHub](https://img.shields.io/github/license/mideind/BinPackage)
![Python 3.6+](https://img.shields.io/badge/python-3.6-blue.svg)

<img src="static/img/greynir-logo-large.png" alt="Greynir" width="200" height="200" align="right" style="margin-left:20px; margin-bottom: 20px;">

*BinPackage* is a Python package that embeds the entire Database of Modern Icelandic
Inflection (Beygingarlýsing íslensks nútímamáls, BÍN) and allows various
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

Querying for word forms:

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

What category or categories does a word form belong to?

```python
>>> from islenska import Bin
>>> b = Bin()
>>> set(m.ordfl for m in b.lookup("laga")[1])
>>> {'hk', 'so', 'kk'}
```

Here, we see that the word form *laga* can be a neutral (`'hk'`) or masculine (`'kk'`) noun,
or a verb (`'so'`).

## Implementation

BinPackage is written in [Python 3](https://www.python.org/)
and requires Python 3.6 or later. It runs on CPython and [PyPy](http://pypy.org/).

## File details

* `main.py`: WSGI web server application and main module for command-line invocation
* `routes/*.py`: Routes for the web application
* `query.py`: Natural language query processor
* `queries/*.py`: Question answering modules
* `db/*.py`: Database models and functions via SQLAlchemy
* `scraper.py`: Web scraper, collecting articles from a set of pre-selected websites (roots)
* `scrapers/*.py`: Scraper code for various websites
* `settings.py`: Management of global settings and configuration data
* `config/Greynir.conf`: Editable configuration file
* `fetcher.py`: Utility classes for fetching articles given their URLs
* `nertokenizer.py`: A layer on top of the tokenizer for named entity recognition
* `processor.py`: Information extraction from parse trees and token streams
* `article.py`: Representation of an article through its life cycle
* `tree.py`: Representation of parse trees for processing
* `vectors/builder.py`: Article indexer and LSA topic vector builder
* `doc.py`: Extract plain text from various document formats
* `geo.py`: Geography and location-related utility functions
* `speech.py`: Speech synthesis-related utility functions
* `tools/*.py`: Various command line tools
* `util.py`: Various utility functions

## Installation and setup

You must have Python >= 3.6 installed on your machine.
If you are using a virtual Python environment, activate it first:

```bash
$ venv/bin/activate
```
...or, on Windows:
```
C:\> venv\scripts\activate
```

Then, install BinPackage using Pip:

```bash
$ pip install islenska
```

Now, you are ready to `import islenska` or `from islenska import Bin` in your Python code.

## Using BinPackage

Once you have followed the setup and installation instructions above, change to the 
Greynir repository and activate the virtual environment:

```
cd Greynir
venv/bin/activate
```

You should now be able to run Greynir.

## Copyright and licensing

BinPackage embeds the **Database of Modern Icelandic Inflection**
(**Beygingarlýsing íslensks nútímamáls**), abbreviated *BÍN*.

The BÍN source data are publicly available under the CC-BY-4.0 license,
as further detailed here in English and here in Icelandic.

In accordance with the BÍN license terms, credit is hereby given as follows:

*Beygingarlýsing íslensks nútímamáls. Stofnun Árna Magnússonar í íslenskum fræðum.*
*Höfundur og ritstjóri Kristín Bjarnadóttir.*

----

BinPackage includes certain additions and modifications to the original
BÍN source data. These are explained in the source code file tools/binpack.py,
available in the project's GitHub repository.

----

BinPackage is Copyright (C) 2021 [Miðeind ehf.](https://mideind.is)
The original author of this software is *Vilhjálmur Þorsteinsson*.

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

Miðeind ehf.

If you would like to use this software in ways that are incompatible with the
standard MIT license, contact Miðeind ehf. to negotiate custom arrangements.

