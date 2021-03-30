# BinPackage

**The Database of Icelandic Morphology (DIM, BÍN) encapsulated in a Python package**

[![Python package](https://github.com/mideind/BinPackage/actions/workflows/python-package.yml/badge.svg)](https://github.com/mideind/BinPackage/actions/workflows/python-package.yml)

![GitHub](https://img.shields.io/github/license/mideind/BinPackage)
![Python 3.6+](https://img.shields.io/badge/python-3.6-blue.svg)

<img src="img/greynir-logo-large.png" alt="Greynir" width="200" height="200" align="right" style="margin-left:20px; margin-bottom: 20px;">

*BinPackage* is a Python package that embeds the entire
[*Database of Icelandic Morphology*](https://bin.arnastofnun.is/DMII/)
([*Beygingarlýsing íslensks nútímamáls*](https://bin.arnastofnun.is/), *BÍN*)
and offers various lookups and queries of the data.

The database, maintained by
[*The Árni Magnússon Institute for Icelandic Studies*](https://arnastofnun.is)
and edited by chief editor *Kristín Bjarnadóttir*, contains over
6.5 million entries, over 3.1 million unique word forms,
and about 300,000 distinct lemmas.

[*Miðeind ehf*](https://mideind.is), the publisher of BinPackage,
has encapsulated the database in an easy-to-install Python package, compressing it
from a 400+ megabyte CSV file into an ~80 megabyte indexed binary structure.
The package maps this structure directly into memory (via `mmap`) for fast lookup.
An algorithm for handling compound words is an important additional feature
of the package.

With BinPackage, `pip install islenska` is all you need to have almost the
entire vocabulary of the modern Icelandic language at your disposal via Python.
Batteries are included; no additional databases, downloads or middleware are required.

BinPackage allows querying for word forms, as well as lemmas and grammatical variants.
This includes information about word classes/categories (noun, verb, ...),
domains (person names, place names, ...), grammatical tags and
various annotations, such as degrees of linguistic acceptability and alternate
spelling forms.


## The basics of BÍN

The BÍN database is
[published in electronic form](https://bin.arnastofnun.is/gogn/mimisbrunnur/)
under the CC-BY 4.0 license, in CSV files in two main formats:
*Sigrúnarsnið* (`SHsnid`) and
*Kristínarsnið* (`Ksnid`). Sigrúnarsnið is more compact with 6 attributes
for each word form. Kristínarsnið, documented
[here](https://bin.arnastofnun.is/gogn/k-snid), is newer and more detailed,
with up to 15 attributes for each word form.

BinPackage supports both formats, with `Ksnid` being returned from several
functions and `SHsnid` from others, as documented below.

### SHsnid

`SHsnid` is represented in BinPackage with a Python `NamedTuple` called
`BinMeaning`, having the following attributes:

| Name     | Type  | Content |
|----------|-------|---------|
| `stofn`  | `str` | The lemma (headword) of the word form (*uppflettiorð*). |
| `utg`    | `int` | The issue number (*útgáfunúmer*) of the lemma, unique for a particular lemma/class combination. |
| `ordfl`  | `str` | The word class/category, i.e. `kk`/`kvk`/`hk` for (masculine/feminine/neutral) nouns, `lo` for adjectives, `so` for verbs, `ao` for adverbs, etc.|
| `fl`     | `str` | The domain, i.e. `alm` for general vocabulary, `ism` for Icelandic person names, `örn` for place names (*örnefni*), etc.|
| `ordmynd` | `str` | The inflected word form. |
| `beyging` | `str` | The grammatical (part-of-speech, PoS) tags of the word form, for instance `ÞGFETgr` for dative (*þágufall*, `ÞGF`), singular (*eintala*, `ET`), definite (*með greini*, `gr`). |

The grammatical tags in the `beyging` attribute are documented in detail [here](https://bin.arnastofnun.is/gogn/greiningarstrengir/).

### Ksnid

`Ksnid` is represented by instances of the `Ksnid` class. It has the same 6
attributes as `SHsnid` but adds 9 attributes, shortly summarized below
(full documentation [here](https://bin.arnastofnun.is/gogn/k-snid)):

| Name     | Type  | Content |
|----------|-------|---------|
| `einkunn` | `int` | A general correctness grade, ranging from 0-5. |
| `malsnid` | `str` | A genre/register indicator; e.g. `STAD` for local and `URE` for deprecated. |
| `malfraedi` | `str` | Grammatical marking, such as `STAFS` for dubious spelling and `TALA` for rare singular forms. |
| `millivisun` | `int` | Cross reference to the `utg` number of a related lemma. |
| `birting` | `str` | `K` for the BÍN *kernel* of most common and accepted word forms, `V` for other published BÍN entries. |
| `beinkunn` | `int` | An inflectional correctness grade, ranging from 0-5. |
| `bmalsnid` | `str` | A genre/register indicator for this inflectional form. |
| `bgildi` | `str` | Indicator for word forms bound to idioms and other special cases. |
| `aukafletta` | `str` | Alternative lemma, e.g. plural form. |


## Word compounding algorithm

Icelandic allows almost unlimited creation of compound words. Examples are
*síamskattarkjóll* (noun), *sólarolíulegt* (adjective), *öskurgrenja* (verb).
It is of course impossible for a static database to include all possible
compound words. To address this problem, BinPackage features a compound word
recognition algorithm, which is invoked when looking up any word that is not
found as-is in BÍN.

The algorithm relies on a list of valid word prefixes, stored in
`src/islenska/resources/prefixes.txt`, and suffixes, stored in
`src/islenska/resources/suffixes.txt`. These lists have been compressed
into data structures called *Directed Acyclic Word Graphs* (DAWGs). BinPackage
uses these DAWGs to find optimal solutions for the compound word
problem, where an optimal solution is defined as the prefix+suffix
combination that has (1) the fewest prefixes and (2) the longest suffix.

If an optimal compound form exists for a word, its suffix is looked up in BÍN
and used as an inflection template for the compound. *Síamskattarkjóll*
is thus resolved into the prefix *síamskattar* and the suffix *kjóll*,
with the latter providing the inflection of *síamskattarkjóll* as
a singular masculine noun in the nominative case.

The compounding algorithm returns the prefixes and suffixes of the
optimal compound in the `stofn` and `ordmynd` fields of the returned
`BinMeaning` / `Ksnid` instances, separated by hyphens `-`. As an example,
*síamskattarkjóll* is returned as follows (note the hyphens):

```python
>>> b.lookup("síamskattarkjóll")
('síamskattarkjóll', [(stofn='síamskattar-kjóll', kk/alm/0, ordmynd='síamskattar-kjóll', NFET)])
```

If desired, the compounding algorithm can be disabled
via an optional flag; see the documentation below.

# Examples

## Querying for word forms

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

`Bin.lookup()` returns the matched search key, usually identical to the
passed-in word (here *færi*), and a list of its possible meanings
in `SHsnid` (*Sigrúnarsnið*), i.e. as instances of `BinMeaning`.

Each meaning tuple contains the
lemma (`stofn`), the word class, domain and issue number (`hk/alm/1198`),
the inflectional form (`ordmynd`) and the grammatical (PoS) tags (`GM-VH-NT-3P-FT`).
The tag strings are [documented on the BÍN website](https://bin.arnastofnun.is/gogn/k-snid).

## Detailed word query

*Uppfletting ítarlegra upplýsinga*

```python
>>> from islenska import Bin
>>> b = Bin()
>>> w, m = b.lookup_ksnid("allskonar")
>>> m[0].malfraedi
'STAFS'
```

`Bin.lookup_ksnid()` returns the matched search key and a list of its possible
meanings in *Kristínarsnið* (`Ksnid`). The fields of *Kristínarsnið* are
[documented on the BÍN website](https://bin.arnastofnun.is/gogn/k-snid).
In the example, we show how the word `allskonar` is marked with the
tag `STAFS` in the `malfraedi` field, indicating that this spelling
is nonstandard. A more correct form is `alls konar`, in two words.

## Lemmas and classes

*Lemmur, uppflettiorð; orðflokkar*

BinPackage can find all possible lemmas (headwords) of a word,
and the classes/categories to which it may belong.

```python
>>> from islenska import Bin
>>> b = Bin()
>>> b.lookup_lemmas_and_cats("laga")
{('lag', 'hk'), ('lög', 'hk'), ('laga', 'so'), ('lagi', 'kk'), ('lögur', 'kk')}
```

Here we see, perhaps unexpectedly, that the word form *laga* has five possible lemmas:
four nouns (*lag*, *lög*, *lagi* and *lögur*, neutral (`hk`) and masculine (`kk`)
respectively), and one verb (`so`), having the infinitive (*nafnháttur*) *að laga*.

## Grammatical variants

With BinPackage, it is easy to obtain grammatical variants of words: convert
them between cases, singular and plural, persons, degrees, moods, etc. Let's look
at an example:

```python
>>> from islenska import Bin
>>> b = Bin()
>>> m = b.lookup_variants("Laugavegur", "kk", "ÞGF")
>>> m[0].ordmynd
'Laugavegi'
```

This is all it takes to convert the (masculine, `kk`) street name *Laugavegur*
to dative case, commonly used in addresses.

```python
>>> from islenska import Bin
>>> b = Bin()
>>> m = b.lookup_variants("fallegur", "lo", ("EVB", "HK", "FT"))
>>> adj = m[0].ordmynd
>>> f"Ég sá {adj} norðurljósin"
'Ég sá fallegustu norðurljósin'
```

Here, we obtained the superlative degree, weak form (`EVB`, *efsta stig*,
*veik beyging*), neutral gender (`HK`), plural (`FT`), of the adjective (`lo`)
*fallegur* and used it in a sentence.

# Documentation

## `Bin()` constructor

To create an instance of the `Bin` class, do as follows:

```python
>>> from islenska import Bin
>>> b = Bin()
```

You can optionally specify the following boolean flags in the `Bin()`
constructor call:

| Flag              | Default | Meaning                                        |
|-------------------|---------|------------------------------------------------|
| `add_negation`    | `True`    | For adjectives, find forms with the prefix `ó` even if only the non-prefixed version is present in BÍN. Example: find `ófíkinn` because `fíkinn` is in BÍN. |
| `add_legur`       | `True`    | For adjectives, find all forms with an "adjective-like" suffix, i.e. `-legur`, `-leg`, etc. even if they are not present in BÍN. Example: `sólarolíulegt`. |
| `add_compounds`   | `True`    | Find compound words that can be derived from BinPackage's collection of allowed prefixes and suffixes. The algorithm finds the compound word with the fewest components and the longest suffix. Example: `síamskattar-kjóll`. |
| `replace_z`       | `True`    | Find words containing `tzt` and `z` by replacing these strings by `st` and `s`, respectively. Example: `veitzt` -> `veist`. |
| `only_bin`        | `False`   | Find only word forms that are originally present in BÍN, disabling all of the above described flags. |

As an example, to create a `Bin` instance that only returns word forms that occur
in the original BÍN database, do like so:

```python
>>> from islenska import Bin
>>> b = Bin(only_bin=True)
```

## `lookup()` function

To look up word forms and return summarized `SHsnid` data (`BinMeaning` tuples),
call the `lookup` function:

```python
>>> w, m = b.lookup("síamskattarkjólanna")
>>> w
'síamskattarkjólanna'
>>> m
[(stofn='síamskattar-kjóll', kk/alm/0, ordmynd='síamskattar-kjólanna', EFFTgr)]
```

This function returns a `Tuple[str, List[BinMeaning]]` containing the word that
was actually used as a search key,
and a list of `BinMeaning` instances corresponding to the various possible
meanings of that word. The list is empty if no meanings were found, in which
case the word is probably not Icelandic or at least not spelled correctly.

Here we see that *síamskattarkjólanna* is a compound word, amalgamated
from *síamskattar* and *kjólanna*, with *kjóll* being the base lemma of the compound
word. This is a masculine noun (`kk`), in the `alm` (general vocabulary) domain.
It has an issue number (*útgáfunúmer*) equal to 0 since it is constructed
on-the-fly by BinPackage, rather than being fetched directly from BÍN. The grammatical
tag string is `EFFTgr`, i.e. genitive (*eignarfall*, `EF`), plural (*fleirtala*,
`FT`) and definite (*með greini*, `gr`).

You can specify the `at_sentence_start` option as being `True`, in which case
BinPackage will also look for lower case words in BÍN even if the lookup word
is upper case. As an example:

```python
>>> b.lookup("Heftaranum", at_sentence_start=True)
('heftaranum', [(stofn='heftari', kk/alm/7958, ordmynd='heftaranum', ÞGFETgr)])
```

Note that here, the returned search key (`w` in the first example above) is
`heftaranum` in lower case, since `Heftaranum` in upper case was not found in BÍN.

Another option is `auto_uppercase`, which if set to True, causes the returned
search key to be in upper case if any upper case meaning exists in BÍN for the
lookup word. This can be helpful when attempting to normalize
all-lowercase input, for example from voice recognition systems. (Additional
disambiguation is typically still needed, since many common words and names do
exist both in lower case and in upper case, and BinPackage cannot infer which
form is desired in the output.)

A final example of when the returned search key is different from the lookup word:

```python
>>>> b.lookup("þýzk")
('þýsk', [
    (stofn='þýskur', lo/alm/408914, ordmynd='þýsk', FSB-KVK-NFET),
    (stofn='þýskur', lo/alm/408914, ordmynd='þýsk', FSB-HK-NFFT),
    (stofn='þýskur', lo/alm/408914, ordmynd='þýsk', FSB-HK-ÞFFT)
])
```

Here, the input contains `z` or `tzt` which is translated to `s` or `st`
respectively to find a lookup match in BÍN. In this case, the actual matching
word `þýsk` is returned as the search key instead of `þýzk`. (This behavior
can be disabled with the `replace_z` flag on the `Bin()` constructor,
as described above.)

`lookup()` has the following parameters:

| Name | Type | Default | Description |
|------|------|---------|-------------|
| w | `str` | | The word to look up |
| at_sentence_start | `bool` | `False` | `True` if BinPackage should also return lower case forms of the word, if it is given in upper case. |
| auto_uppercase | `bool` | `False` | `True` if BinPackage should use and return upper case search keys, if the word exists in upper case. |

The function returns a `Tuple[str, List[BinMeaning]]` instance.
The first element of the tuple is the search key that was matched in BÍN,
and the second element is the list of potential word meanings, each represented
by a `BinMeaning` (`SHsnid`) instance.


## `lookup_ksnid()` function

To look up word forms and return full `Ksnid` instances,
call the `lookup_ksnid()` function:

```python
>>> w, m = b.lookup_ksnid("allskonar")
>>> w
'allskonar'
>>> str(m[0])
"<Ksnid: ordmynd='allskonar', stofn/ordfl/fl/utg='allskonar'/lo/alm/175686, beyging=FSB-KK-NFET, ksnid='4;;STAFS;496369;V;1;;;'>"
>>> m.malfraedi
'STAFS'
>>> m.millivisun
496369
```

This function is identical to `lookup()` except that it returns full `Ksnid`
instances, with 15 attributes each, instead of `BinMeaning` tuples. The
same option flags are available and the logic for returning the search key
is the same.

The example shows how the word *allskonar* has a grammatical comment
regarding spelling (`m.malfraedi == 'STAFS'`) and a cross-reference
to the entry with issue number (`utg`) 496369 - which is the lemma
*alls konar*.

`lookup_ksnid()` has the following parameters:

| Name | Type | Default | Description |
|------|------|---------|-------------|
| w | `str` | | The word to look up |
| at_sentence_start | `bool` | `False` | `True` if BinPackage should also return lower case forms of the word, if it is given in upper case. |
| auto_uppercase | `bool` | `False` | `True` if BinPackage should use and return upper case search keys, if the word exists in upper case. |

The function returns a `Tuple[str, List[Ksnid]]` instance.
The first element of the tuple is the search key that was matched in BÍN,
and the second element is the list of potential word meanings, each represented
in a `Ksnid` instance.


## `lookup_cats()` function

To look up the possible classes/categories of a word (*orðflokkar*),
call the `lookup_cats` function:

```python
>>> b.lookup_cats("laga")
{'so', 'hk', 'kk'}
```

The function returns a `Set[str]` with all possible word classes/categories
of the word form. If the word is not found in BÍN, or recognized using the
compounding algorithm, the function returns an empty set.

`lookup_cats()` has the following parameters:

| Name | Type | Default | Description |
|------|------|---------|-------------|
| w | `str` | | The word to look up |
| at_sentence_start | `bool` | `False` | `True` if BinPackage should also include lower case forms of the word, if it is given in upper case. |


## `lookup_lemmas_and_cats()` function

To look up the possible lemmas/headwords and classes/categories of a word
(*lemmur og orðflokkar*), call the `lookup_lemmas_and_cats` function:

```python
>>> b.lookup_lemmas_and_cats("laga")
{('lagi', 'kk'), ('lögur', 'kk'), ('laga', 'so'), ('lag', 'hk'), ('lög', 'hk')}
```

The function returns a `Set[Tuple[str, str]]` where each tuple contains
a lemma/headword and a class/category, respectively.
If the word is not found in BÍN, or recognized using the
compounding algorithm, the function returns an empty set.

`lookup_lemmas_and_cats()` has the following parameters:

| Name | Type | Default | Description |
|------|------|---------|-------------|
| w | `str` | | The word to look up |
| at_sentence_start | `bool` | `False` | `True` if BinPackage should also include lower case forms of the word, if it is given in upper case. |


## `lookup_variants()` function

This function returns grammatical variants of a given word. For instance,
it can return a noun in a different case, plural instead of singular,
and/or with or without an attached definite article (*greinir*). It can return
adjectives in different degrees (*frumstig*, *miðstig*, *efsta stig*), verbs
in different persons or moods, etc.

Here is a simple example, converting the masculine noun *heftaranum* from dative
to nominative case (`NF`):

```python
>>> m = b.lookup_variants("heftaranum", "kk", "NF")
>>> m[0].ordmynd
'heftarinn'
```

Here we add a conversion to plural (`FT`) as well - note that we can pass multiple
grammatical tags in a tuple:

```python
>>> m = b.lookup_variants("heftaranum", "kk", ("NF", "FT"))
>>> m[0].ordmynd
'heftararnir'
```

Finally, we specify a conversion to indefinite form (`nogr`):

```python
>>> m = b.lookup_variants("heftaranum", "kk", ("NF", "FT", "nogr"))
>>> m[0].ordmynd
'heftarar'
```

Definite form is requested via `gr`, and indefinite form via `nogr`.

Let's try modifying a verb from subjunctive (*viðtengingarháttur*) to
indicative mood (*framsöguháttur*), present tense:

```python
>>> m = b.lookup_variants("hraðlæsi", "so", ("FH", "NT"))
>>> for mm in m: print(mm.stofn, mm.ordmynd, mm.beyging)
hraðlesa hraðles GM-FH-NT-1P-ET
hraðlesa hraðles GM-FH-NT-3P-ET
```

Finally, let's describe this functionality in superlative terms:

```python
>>> adj = b.lookup_variants("frábær", "lo", ("EVB", "KVK"))[0].ordmynd
>>> f"Þetta er {adj} virknin af öllum"
'Þetta er frábærasta virknin af öllum'
```

Note how we ask for a superlative weak form (`EVB`) for a feminine subject (`KVK`),
getting back the adjective *frábærasta*. We could also ask for the
strong form (`ESB`), and then for the comparative (*miðstig*, `MST`):

```python
>>> adj = b.lookup_variants("frábær", "lo", ("ESB", "KVK"))[0].ordmynd
>>> f"Þessi virkni er {adj} af öllum"
'Þessi virkni er frábærust af öllum'
>>> adj = b.lookup_variants("frábær", "lo", ("MST", "KVK"))[0].ordmynd
>>> f"Þessi virkni er {adj} en allt annað"
'Þessi virkni er frábærari en allt annað'
```

`lookup_variants()` has the following parameters:

| Name | Type | Default | Description |
|------|------|---------|-------------|
| w | `str` | | The word to use as a base for the lookup |
| cat | `str` | | The word class, used to disambiguate the word. `no` (*nafnorð*) can be used to match any of `kk`, `kvk` and `hk`. |
| to_beyging | `Union[str, Tuple[str, ...]]` | | One or more requested grammatical features, using the BÍN tag string format. As a special case, `nogr` means indefinite form (no `gr`) for nouns. The parameter can be a single string or a tuple of several strings.|
| lemma | `Optional[str]` | `None` | The lemma of the word, optionally used to further disambiguate it |
| utg | `Optional[int]` | `None` | The id number of the word, optionally used to further disambiguate it |
| beyging_filter | `Optional[Callable[[str], bool]]` | `None` | A callable taking a single string parameter and returning a `bool`. The `beyging` attribute of a potential word meaning will be passed to this function, and only included in the result if the function returns `True`. |

The function returns `List[Ksnid]`.


## `lemma_meanings()` function

To look up all possible meanings of a word as a lemma/headword,
call the `lemma_meanings` function:

```python
>>> b.lemma_meanings("þyrla")
('þyrla',
  [
    (stofn='þyrla', kvk/alm/16445, ordmynd='þyrla', NFET),  # Feminine noun
    (stofn='þyrla', so/alm/425096, ordmynd='þyrla', GM-NH)  # Verb
  ]
)
>>> b.lemma_meanings("þyrlast")
('þyrlast', [(stofn='þyrla', so/alm/425096, ordmynd='þyrlast', MM-NH)])  # Middle voice infinitive
>>> b.lemma_meanings("þyrlan")
('þyrlan', [])
```

The function returns a `Tuple[str, List[BinMeaning]]` like `lookup()`,
but where the `BinMeaning` list
has been filtered to include only lemmas/headwords. This is the reason why
`b.lemma_meanings("þyrlan")` returns an empty list in the example above -
*þyrlan* does not appear in BÍN as a lemma/headword.

Lemmas/headwords of verbs include the middle voice (*miðmynd*) of the
infinitive, `MM-NH`, as in the example for *þyrlast*.

`lemma_meanings()` has a single parameter:

| Name | Type | Default | Description |
|------|------|---------|-------------|
| lemma | `str` | | The word to look up as a lemma/headword. |


# Implementation

BinPackage is written in [Python 3](https://www.python.org/)
and requires Python 3.6 or later. It runs on CPython and [PyPy](http://pypy.org/).

The Python code calls a small C++ library to speed up lookup of word forms in the
compressed binary structure into which BÍN has been encoded.
This means that if a pre-compiled Python wheel is not
available on PyPI for your platform, you may need a set of development tools installed
on your machine, before you install BinPackage using `pip`:

```bash
$ # The following works on Debian/Ubuntu GNU/Linux
$ sudo apt-get install python3-dev libffi-dev
```

BinPackage is fully type-annotated for use with Python static type checkers such
as `mypy` and `Pylance` / `Pyright`.


# Installation and setup

You must have Python >= 3.6 installed on your machine (CPython or PyPy).
If you are using a Python virtual environment (`virtualenv`), activate it first (substituting your environment name for `venv` below):

```bash
$ venv/bin/activate
```
...or, on Windows:

```cmd
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
$ unzip -q KRISTINsnid.csv.zip
$ rm KRISTINsnid.csv.*
$ cd ../../..
$ # Run the compressor to generate src/islenska/resources/compressed.bin
$ python tools/binpack.py
$ # Run the DAWG builder for the prefix and suffix files
$ python tools/dawgbuilder.py
$ # Now you're ready to go
```

This will clone the GitHub repository into the BinPackage directory
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


# Copyright and licensing

BinPackage embeds the
**[Database of Icelandic Morphology](https://bin.arnastofnun.is/)**
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
BÍN source data. These are documented above and also explained in detail
in the source code file `tools/binpack.py`, available in the project's
GitHub repository.

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

# Acknowledgements

Parts of this software were developed under the auspices of the
Icelandic Government's 5-year Language Technology Programme for Icelandic,
managed by [Almannarómur](https://almannaromur.is). The LT Programme is described
[here](https://www.stjornarradid.is/lisalib/getfile.aspx?itemid=56f6368e-54f0-11e7-941a-005056bc530c>)
(English version [here](https://clarin.is/media/uploads/mlt-en.pdf>)).
