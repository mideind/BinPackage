![GitHub](https://img.shields.io/github/license/mideind/BinPackage)
![Python 3.9+](https://img.shields.io/badge/python-3.9-blue.svg)
![Release](https://shields.io/github/v/release/mideind/BinPackage?display_name=tag)
![PyPI](https://img.shields.io/pypi/v/islenska)
[![Python package](https://github.com/mideind/BinPackage/actions/workflows/python-package.yml/badge.svg)](https://github.com/mideind/BinPackage/actions/workflows/python-package.yml)

# BinPackage

**The Database of Icelandic Morphology (DIM, BÍN) encapsulated in a Python package**

<img src="img/greynir-logo-large.png" alt="Greynir" width="200" height="200" align="right" style="margin-left:20px; margin-bottom: 20px;">

*BinPackage* is a Python (>= 3.9) package, published by
[*Miðeind ehf*](https://mideind.is), that embeds the vocabulary of the
[*Database of Icelandic Morphology*](https://bin.arnastofnun.is/DMII/)
([*Beygingarlýsing íslensks nútímamáls*](https://bin.arnastofnun.is/), *BÍN*)
and offers various lookups and queries of the data.

The database, maintained by
[*The Árni Magnússon Institute for Icelandic Studies*](https://arnastofnun.is)
and edited by chief editor *Kristín Bjarnadóttir*, contains over
6.5 million entries, over 3.1 million unique word forms,
and about 300,000 distinct lemmas.

Miðeind has encapsulated the database in an easy-to-install Python package,
compressing it
from a 400+ megabyte CSV file into an ~82 megabyte indexed binary structure.
The package maps this structure directly into memory (via `mmap`) for fast lookup.
An algorithm for handling compound words is an important additional feature
of the package.

With BinPackage, `pip install islenska` is all you need to have almost all
of the commonly used vocabulary of the modern Icelandic language at your
disposal via Python. Batteries are included; no additional databases,
downloads or middleware are required.

BinPackage allows querying for word forms, as well as lemmas and grammatical variants.
This includes information about word classes/categories (noun, verb, ...),
domains (person names, place names, ...), inflectional tags and
various annotations, such as degrees of linguistic acceptability and alternate
spelling forms.

## The basics of BÍN

The DMI/BÍN database is
[published in electronic form](https://bin.arnastofnun.is/gogn/mimisbrunnur/)
by [*The Árni Magnússon Institute for Icelandic Studies*](https://arnastofnun.is).
The database is
released under the CC BY-SA 4.0 license, in CSV files having two main formats:
*Sigrúnarsnið* (the *Basic Format*) and *Kristínarsnið* (the *Augmented Format*).
Sigrúnarsnið is more compact with six attributes
for each word form. Kristínarsnið is newer and more detailed,
with up to 15 attributes for each word form.

BinPackage supports both formats, with the augmented format (represented
by the class `Ksnid`) being returned from several functions
and the basic format (represented by the named tuple `BinEntry`)
from others, as documented below.

Further information in English about the word classes and the inflectional
categories in the DMI/BÍN database can be found
[here](https://bin.arnastofnun.is/DMII/infl-system/).

### The Basic Format

The BÍN *Basic Format* is represented in BinPackage with a Python `NamedTuple`
called `BinEntry`, having the following attributes (further documented
[here in Icelandic](https://bin.arnastofnun.is/gogn/SH-snid) and
[here in English](https://bin.arnastofnun.is/DMII/LTdata/s-format/)):

| Name     | Type  | Content  |
|----------|-------|----------|
| `ord` | `str` | Lemma (headword, *uppflettiorð*). |
| `bin_id` | `int` | Identifier of the lemma, unique for a particular lemma/class combination. |
| `ofl` | `str` | Word class/category, i.e. `kk`/`kvk`/`hk` for (masculine/feminine/neutral) nouns, `lo` for adjectives, `so` for verbs, `ao` for adverbs, etc.|
| `hluti` | `str` | Semantic classification, i.e. `alm` for general vocabulary, `ism` for Icelandic person names, `örn` for place names (*örnefni*), etc.|
| `bmynd` | `str` | Inflectional form (*beygingarmynd*). |
| `mark` | `str` | Inflectional tag of this inflectional form, for instance `ÞGFETgr` for dative (*þágufall*, `ÞGF`), singular (*eintala*, `ET`), definite (*með greini*, `gr`). |

The inflectional tag in the `mark` attribute is documented in detail
[here in Icelandic](https://bin.arnastofnun.is/gogn/greiningarstrengir/) and
[here in English](https://bin.arnastofnun.is/DMII/LTdata/tagset/).

### The Augmented Format

The BÍN *Augmented Format*, *Kristínarsnið*, is represented by instances of
the `Ksnid` class. It has the same six attributes as `BinEntry` (the Basic
Format) but adds nine attributes, shortly summarized below.
For details, please refer to the full documentation
[in Icelandic](https://bin.arnastofnun.is/gogn/k-snid)
or [in English](https://bin.arnastofnun.is/DMII/LTdata/k-format/).

| Name     | Type  | Content  |
|----------|-------|----------|
| `einkunn` | `int` | Headword correctness grade, ranging from 0-5. |
| `malsnid` | `str` | Genre/register indicator; e.g. `STAD` for dialectal, `GAM` for old-fashioned or `URE` for obsolete. |
| `malfraedi` | `str` | Grammatical marking for further consideration, such as `STAFS` (spelling) or `TALA` (singular/plural). |
| `millivisun` | `int` | Cross reference to the identifier (`bin_id` field) of a variant of this headword. |
| `birting` | `str` | `K` for the DMII Core (*BÍN kjarni*) of most common and accepted word forms, `V` for other published BÍN entries. |
| `beinkunn` | `int` | Correctness grade for this inflectional form, ranging from 0-5. |
| `bmalsnid` | `str` | Genre/register indicator for this inflectional form. |
| `bgildi` | `str` | Indicator for inflectional forms bound to idioms and other special cases. |
| `aukafletta` | `str` | Alternative headword, e.g. plural form. |

## Word compounding algorithm

Icelandic allows almost unlimited creation of compound words. Examples are
*síamskattarkjóll* (noun), *sólarolíulegur* (adjective), *öskurgrenja* (verb).
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
optimal compound in the `ord` and `bmynd` fields of the returned
`BinEntry` / `Ksnid` instances, separated by hyphens `-`. As an example,
*síamskattarkjóll* is returned as follows (note the hyphens):

```python
>>> b.lookup("síamskattarkjóll")
('síamskattarkjóll', [
    (ord='síamskattar-kjóll', kk/alm/0, bmynd='síamskattar-kjóll', NFET)
])
```

Lookups that are resolved via the compounding algorithm have a `bin_id` of zero.
Note that the compounding algorithm will occasionally recognize nonexistent
words, for instance spelling errors, as compounds.

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
    (ord='fara', so/alm/433568, bmynd='færi', OP-ÞGF-GM-VH-ÞT-1P-ET),
    (ord='fara', so/alm/433568, bmynd='færi', OP-ÞGF-GM-VH-ÞT-1P-FT),
    (ord='fara', so/alm/433568, bmynd='færi', OP-ÞGF-GM-VH-ÞT-2P-ET),
    (ord='fara', so/alm/433568, bmynd='færi', OP-ÞGF-GM-VH-ÞT-2P-FT),
    (ord='fara', so/alm/433568, bmynd='færi', OP-ÞGF-GM-VH-ÞT-3P-ET),
    (ord='fara', so/alm/433568, bmynd='færi', OP-það-GM-VH-ÞT-3P-ET),
    (ord='fara', so/alm/433568, bmynd='færi', OP-ÞGF-GM-VH-ÞT-3P-FT),
    (ord='fara', so/alm/433568, bmynd='færi', GM-VH-ÞT-1P-ET),
    (ord='fara', so/alm/433568, bmynd='færi', GM-VH-ÞT-3P-ET),
    (ord='fær', lo/alm/448392, bmynd='færi', FVB-KK-NFET),
    (ord='færa', so/alm/434742, bmynd='færi', GM-FH-NT-1P-ET),
    (ord='færa', so/alm/434742, bmynd='færi', GM-VH-NT-1P-ET),
    (ord='færa', so/alm/434742, bmynd='færi', GM-VH-NT-3P-ET),
    (ord='færa', so/alm/434742, bmynd='færi', GM-VH-NT-3P-FT),
    (ord='færi', hk/alm/1198, bmynd='færi', NFET),
    (ord='færi', hk/alm/1198, bmynd='færi', ÞFET),
    (ord='færi', hk/alm/1198, bmynd='færi', ÞGFET),
    (ord='færi', hk/alm/1198, bmynd='færi', NFFT),
    (ord='færi', hk/alm/1198, bmynd='færi', ÞFFT)
])
```

`Bin.lookup()` returns the matched search key, usually identical to the
passed-in word (here *færi*), and a list of matching entries
in the basic format (*Sigrúnarsnið*), i.e. as instances of `BinEntry`.

Each entry is a named tuple containing the
lemma (`ord`), the word class, domain and id number (`hk/alm/1198`),
the inflectional form (`bmynd`) and tag (`GM-VH-NT-3P-FT`).
The tag strings are documented in detail
[here in Icelandic](https://bin.arnastofnun.is/gogn/greiningarstrengir/) and
[here in English](https://bin.arnastofnun.is/DMII/LTdata/tagset/).

## Detailed word query

*Uppfletting ítarlegra upplýsinga*

```python
>>> from islenska import Bin
>>> b = Bin()
>>> w, m = b.lookup_ksnid("allskonar")
>>> # m is a list of 24 matching entries; we look at the first item only
>>> m[0].malfraedi
'STAFS'
>>> m[0].einkunn
4
```

`Bin.lookup_ksnid()` returns the matched search key and a list of all matching
entries in the augmented format (*Kristínarsnið*). The fields of *Kristínarsnið*
are documented in detail [here in Icelandic](https://bin.arnastofnun.is/gogn/k-snid)
and [here in English](https://bin.arnastofnun.is/DMII/LTdata/k-format/).

As the example shows, the word `allskonar` is marked with the
tag `STAFS` in the `malfraedi` field, and has an `einkunn` (correctness grade)
of 4 (where 1 is the normal grade), giving a clue that this spelling is
nonstandard. (A more correct form is `alls konar`, in two words.)

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

## Lookup by BÍN identifier

Given a BÍN identifier (id number), BinPackage can return all entries for that id:

```python
>>> from islenska import Bin
>>> b = Bin()
>>> b.lookup_id(495410)
[<Ksnid: bmynd='sko', ord/ofl/hluti/bin_id='sko'/uh/alm/495410, mark=OBEYGJANLEGT, ksnid='1;;;;K;1;;;'>]
```

## Grammatical variants

With BinPackage, it is easy to obtain grammatical variants
(alternative inflectional forms) of words: convert them between cases,
singular and plural, persons, degrees, moods, etc. Let's look
at an example:

```python
>>> from islenska import Bin
>>> b = Bin()
>>> m = b.lookup_variants("Laugavegur", "kk", "ÞGF")
>>> # m is a list of all possible variants of 'Laugavegur' in dative case.
>>> # In this particular example, m has only one entry.
>>> m[0].bmynd
'Laugavegi'
```

This is all it takes to convert the (masculine, `kk`) street name *Laugavegur*
to dative case, commonly used in addresses.

```python
>>> from islenska import Bin
>>> b = Bin()
>>> m = b.lookup_variants("fallegur", "lo", ("EVB", "HK", "NF", "FT"))
>>> # m contains a list of all inflectional forms that meet the given
>>> # criteria. In this example, we use the first form in the list.
>>> adj = m[0].bmynd
>>> f"Ég sá {adj} norðurljósin"
'Ég sá fallegustu norðurljósin'
```

Here, we obtained the superlative degree, weak form (`EVB`, *efsta stig*,
*veik beyging*), neutral gender (`HK`), nominative case (`NF`), plural (`FT`),
of the adjective (`lo`) *fallegur* and used it in a sentence.

# Documentation

## `Bin()` constructor

To create an instance of the `Bin` class, do as follows:

```python
>>> from islenska import Bin
>>> b = Bin()
```

You can optionally specify the following boolean flags in the `Bin()`
constructor call:

| Flag              | Default | Description                                    |
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

To look up word forms and return summarized data in the Basic Format
(`BinEntry` tuples), call the `lookup` function:

```python
>>> w, m = b.lookup("mæla")
>>> w
'mæla'
>>> m
[
    (ord='mæla', kvk/alm/16302, bmynd='mæla', NFET),
    (ord='mæla', kvk/alm/16302, bmynd='mæla', EFFT2),
    (ord='mæla', so/alm/469211, bmynd='mæla', GM-NH),
    (ord='mæla', so/alm/469211, bmynd='mæla', GM-FH-NT-3P-FT),
    (ord='mæla', so/alm/469210, bmynd='mæla', GM-NH),
    (ord='mæla', so/alm/469210, bmynd='mæla', GM-FH-NT-3P-FT),
    (ord='mæli', hk/alm/2512, bmynd='mæla', EFFT),
    (ord='mælir', kk/alm/4474, bmynd='mæla', ÞFFT),
    (ord='mælir', kk/alm/4474, bmynd='mæla', EFFT)
]
```

This function returns a `Tuple[str, List[BinEntry]]` containing the string that
was actually used as a search key, and a list of `BinEntry` instances that
match the search key. The list is empty if no matches were found, in which
case the word is probably not Icelandic or at least not spelled correctly.

In this example, however, the list has nine matching entries.
We see that the word form *mæla* is an inflectional form of five different
headwords (lemmas), including two verbs (`so`):
(1) *mæla* meaning *to measure* (past tense *mældi*), and (2) *mæla* meaning *to speak*
(past tense *mælti*). Other headwords are nouns, in all three genders:
feminine (`kvk`), neutral (`hk`) and masculine (`kk`).

Let's try a different twist:

```python
>>> w, m = b.lookup("síamskattarkjólanna")
>>> w
'síamskattarkjólanna'
>>> m
[
    (ord='síamskattar-kjóll', kk/alm/0, bmynd='síamskattar-kjólanna', EFFTgr)
]
```

Here we see that *síamskattarkjólanna* is a compound word, amalgamated
from *síamskattar* and *kjólanna*, with *kjóll* being the base lemma of the compound
word. This is a masculine noun (`kk`), in the `alm` (general vocabulary) domain.
Note that it has an id number (*bin_id*) equal to 0 since it is constructed
on-the-fly by BinPackage, rather than being found in BÍN. The grammatical
tag string is `EFFTgr`, i.e. genitive (*eignarfall*, `EF`), plural (*fleirtala*,
`FT`) and definite (*með greini*, `gr`).

You can specify the `at_sentence_start` option as being `True`, in which case
BinPackage will also look for lower case words in BÍN even if the lookup word
is upper case. As an example:

```python
>>> _, m = b.lookup("Geysir", at_sentence_start=True)
>>> m
[
    (ord='geysa', so/alm/483756, bmynd='geysir', GM-FH-NT-2P-ET),
    (ord='geysa', so/alm/483756, bmynd='geysir', GM-FH-NT-3P-ET),
    (ord='geysa', so/alm/483756, bmynd='geysir', GM-VH-NT-2P-ET),
    (ord='Geysir', kk/bær/263617, bmynd='Geysir', NFET)
]
>>> _, m = b.lookup("Geysir", at_sentence_start=False)  # This is the default
>>> m
[
    (ord='Geysir', kk/bær/263617, bmynd='Geysir', NFET)
]
```

As you can see, the lowercase matches for *geysir* are returned as well
as the single uppercase one, if `at_sentence_start` is set to `True`.

Another example:

```python
>>> b.lookup("Heftaranum", at_sentence_start=True)
('heftaranum', [
    (ord='heftari', kk/alm/7958, bmynd='heftaranum', ÞGFETgr)
])
```

Note that here, the returned search key is `heftaranum` in lower case,
since `Heftaranum` in upper case was not found in BÍN.

Another option is `auto_uppercase`, which if set to `True`, causes the returned
search key to be in upper case if any upper case entry exists in BÍN for the
lookup word. This can be helpful when attempting to normalize
all-lowercase input, for example from voice recognition systems. (Additional
disambiguation is typically still needed, since many common words and names do
exist both in lower case and in upper case, and BinPackage cannot infer which
form is desired in the output.)

A final example of when the returned search key is different from the lookup word:

```python
>>>> b.lookup("þýzk")
('þýsk', [
    (ord='þýskur', lo/alm/408914, bmynd='þýsk', FSB-KVK-NFET),
    (ord='þýskur', lo/alm/408914, bmynd='þýsk', FSB-HK-NFFT),
    (ord='þýskur', lo/alm/408914, bmynd='þýsk', FSB-HK-ÞFFT)
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

The function returns a `Tuple[str, List[BinEntry]]` instance.
The first element of the tuple is the search key that was matched in BÍN,
and the second element is the list of matches, each represented
by a `BinEntry` instance.

## `lookup_ksnid()` function

To look up word forms and return full augmented format (*Kristínarsnið*)
entries, call the `lookup_ksnid()` function:

```python
>>> w, m = b.lookup_ksnid("allskonar")
>>> w
'allskonar'
>>> # m is a list of all matches of the word form; here we show the first item
>>> str(m[0])
"<Ksnid: bmynd='allskonar', ord/ofl/hluti/bin_id='allskonar'/lo/alm/175686, mark=FSB-KK-NFET, ksnid='4;;STAFS;496369;V;1;;;'>"
>>> m[0].malfraedi
'STAFS'
>>> m[0].einkunn
4
>>> m[0].millivisun
496369
```

This function is identical to `lookup()` except that it returns full
augmented format entries of class `Ksnid`, with 15 attributes each, instead of
basic format (`BinEntry`) tuples. The same option flags are available
and the logic for returning the search key is the same.

The example shows how the word *allskonar* has a grammatical comment
regarding spelling (`m[0].malfraedi == 'STAFS'`) and a correctness grade
(`m[0].einkunn`) of 4, as well as a cross-reference
to the entry with id number (`bin_id`) 496369 - which is the lemma
*alls konar*.

`lookup_ksnid()` has the following parameters:

| Name | Type | Default | Description |
|------|------|---------|-------------|
| w | `str` | | The word to look up |
| at_sentence_start | `bool` | `False` | `True` if BinPackage should also return lower case forms of the word, if it is given in upper case. |
| auto_uppercase | `bool` | `False` | `True` if BinPackage should use and return upper case search keys, if the word exists in upper case. |

The function returns a tuple of type `Tuple[str, List[Ksnid]]`.
The first element of the tuple is the search key that was matched in BÍN,
and the second element is the list of matching entries, each represented
by an instance of class `Ksnid`.

## `lookup_id()` function

If you have a BÍN identifier (integer id) and need to look up the associated
augmented format (*Kristínarsnið*) entries, call the `lookup_id()` function:

```python
>>> b.lookup_id(495410)
[<Ksnid: bmynd='sko', ord/ofl/hluti/bin_id='sko'/uh/alm/495410, mark=OBEYGJANLEGT, ksnid='1;;;;K;1;;;'>]

```

`lookup_id()` has a single mandatory parameter:

| Name | Type | Default | Description |
|------|------|---------|-------------|
| bin_id | `int` | | The BÍN identifier of the entries to look up. |

The function returns a list of type `List[Ksnid]`. If the given id number is not found
in BÍN, an empty list is returned.

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

This function returns grammatical variants (particular inflectional forms)
of a given word. For instance,
it can return a noun in a different case, plural instead of singular,
and/or with or without an attached definite article (*greinir*). It can return
adjectives in different degrees (*frumstig*, *miðstig*, *efsta stig*), verbs
in different persons or moods, etc.

Here is a simple example, converting the masculine noun *heftaranum* from dative
to nominative case (`NF`):

```python
>>> m = b.lookup_variants("heftaranum", "kk", "NF")
>>> m[0].bmynd
'heftarinn'
```

Here we add a conversion to plural (`FT`) as well - note that we can pass multiple
inflectional tags in a tuple:

```python
>>> m = b.lookup_variants("heftaranum", "kk", ("NF", "FT"))
>>> m[0].bmynd
'heftararnir'
```

Finally, we specify a conversion to indefinite form (`nogr`):

```python
>>> m = b.lookup_variants("heftaranum", "kk", ("NF", "FT", "nogr"))
>>> m[0].bmynd
'heftarar'
```

Definite form is requested via `gr`, and indefinite form via `nogr`.

To see how `lookup_variants()` handles ambiguous word forms, let's
try our old friend *mæli* again:

```python
>>> b.lookup_variants("mæli", "no", "NF")
[
    <Ksnid: bmynd='mæli', ord/ofl/hluti/bin_id='mæli'/hk/alm/2512, mark=NFET, ksnid='1;;;;K;1;;;'>,
    <Ksnid: bmynd='mæli', ord/ofl/hluti/bin_id='mæli'/hk/alm/2512, mark=NFFT, ksnid='1;;;;K;1;;;'>,
    <Ksnid: bmynd='mælir', ord/ofl/hluti/bin_id='mælir'/kk/alm/4474, mark=NFET, ksnid='1;;;;K;1;;;'>
]
```

We specified `no` (noun) as the word class constraint. The result thus contains
nominative case forms of two nouns, one neutral (*mæli*, definite form *mælið*,
with identical singular `NFET` and plural `NFFT` form), and one
masculine (*mælir*, definite form *mælirinn*). If we had specified `hk` as the
word class constraint, we would have gotten back the first two (neutral) entries only;
for `kk` we would have gotten back the third entry (masculine) only.

Let's try modifying a verb from subjunctive (*viðtengingarháttur*)
(e.g., *Ég/hún hraðlæsi bókina ef ég hefði tíma til þess*) to
indicative mood (*framsöguháttur*), present tense
(e.g. *Ég/hún hraðles bókina í flugferðinni*):

```python
>>> m = b.lookup_variants("hraðlæsi", "so", ("FH", "NT"))
>>> for mm in m: print(f"{mm.ord} | {mm.bmynd} | {mm.mark}")
hraðlesa | hraðles | GM-FH-NT-1P-ET
hraðlesa | hraðles | GM-FH-NT-3P-ET
```

We get back both the 1st and the 3rd person inflection forms,
since they can both be derived from *hraðlæsi* and we don't constrain
the person in our variant specification. If only third person
results are desired, we could have specified `("FH", "NT", "3P")` in the
variant tuple.

Finally, let's describe this functionality in superlative terms:

```python
>>> adj = b.lookup_variants("frábær", "lo", ("EVB", "KVK"))[0].bmynd
>>> f"Þetta er {adj} virknin af öllum"
'Þetta er frábærasta virknin af öllum'
```

Note how we ask for a superlative weak form (`EVB`) for a feminine subject (`KVK`),
getting back the adjective *frábærasta*. We could also ask for the
strong form (`ESB`), and then for the comparative (*miðstig*, `MST`):

```python
>>> adj = b.lookup_variants("frábær", "lo", ("ESB", "KVK"))[0].bmynd
>>> f"Þessi virkni er {adj} af öllum"
'Þessi virkni er frábærust af öllum'
>>> adj = b.lookup_variants("frábær", "lo", ("MST", "KVK"))[0].bmynd
>>> f"Þessi virkni er {adj} en allt annað"
'Þessi virkni er frábærari en allt annað'
```

Finally, for some cool Python code for converting any adjective to
the superlative degree (*efsta stig*):

```python
from islenska import Bin
b = Bin()
def efsta_stig(lo: str, kyn: str, veik_beyging: bool=True) -> str:
    """ Skilar efsta stigi lýsingarorðs, í umbeðnu kyni og beygingu """
    vlist = b.lookup_variants(lo, "lo", (kyn, "EVB" if veik_beyging else "ESB"))
    return vlist[0].bmynd if vlist else ""
print(f"Þetta er {efsta_stig('nýr', 'kvk')} framförin í íslenskri máltækni!")
print(f"Þetta er {efsta_stig('sniðugur', 'hk')} verkfærið!")
```

This will output:

```
Þetta er nýjasta framförin í íslenskri máltækni!
Þetta er sniðugasta verkfærið!
```

`lookup_variants()` has the following parameters:

| Name | Type | Default | Description |
|------|------|---------|-------------|
| w | `str` | | The word to use as a base for the lookup |
| cat | `str` | | The word class, used to disambiguate the word. `no` (*nafnorð*) can be used to match any of `kk`, `kvk` and `hk`. |
| to_inflection | `Union[str, Tuple[str, ...]]` | | One or more requested grammatical features, specified using fragments of the BÍN tag string. As a special case, `nogr` means indefinite form (no `gr`) for nouns. The parameter can be a single string or a tuple of several strings. |
| lemma | `Optional[str]` | `None` | The lemma of the word, optionally used to further disambiguate it |
| bin_id | `Optional[int]` | `None` | The id number of the word, optionally used to further disambiguate it |
| inflection_filter | `Optional[Callable[[str], bool]]` | `None` | A callable taking a single string parameter and returning a `bool`. The `mark` attribute of a potential match will be passed to this function, and only included in the result if the function returns `True`. |

The function returns `List[Ksnid]`, i.e. a list of `Ksnid` instances that
match the grammatical features requested in `to_inflection`. If no such
instances exist, an empty list is returned.

## `lookup_lemmas()` function

To look up all entries having the given string as a lemma/headword,
call the `lookup_lemmas` function:

```python
>>> b.lookup_lemmas("þyrla")
('þyrla', [
    (ord='þyrla', kvk/alm/16445, bmynd='þyrla', NFET),  # Feminine noun
    (ord='þyrla', so/alm/425096, bmynd='þyrla', GM-NH)  # Verb
])
>>> b.lookup_lemmas("þyrlast")
('þyrlast', [
    (ord='þyrla', so/alm/425096, bmynd='þyrlast', MM-NH)  # Middle voice infinitive
])
>>> b.lookup_lemmas("þyrlan")
('þyrlan', [])
```

The function returns a `Tuple[str, List[BinEntry]]` like `lookup()`,
but where the `BinEntry` list
has been filtered to include only lemmas/headwords. This is the reason why
`b.lookup_lemmas("þyrlan")` returns an empty list in the example above -
*þyrlan* does not appear in BÍN as a lemma/headword.

Lemmas/headwords of verbs include the middle voice (*miðmynd*) of the
infinitive, `MM-NH`, as in the example for *þyrlast*.

`lookup_lemmas()` has a single parameter:

| Name | Type | Default | Description |
|------|------|---------|-------------|
| lemma | `str` | | The word to look up as a lemma/headword. |

# Implementation

BinPackage is written in [Python 3](https://www.python.org/)
and requires Python 3.9 or later. It runs on CPython and [PyPy](http://pypy.org/).

The Python code calls a small C++ library to speed up lookup of word forms in the
compressed binary structure into which BÍN has been encoded.
This means that if a pre-compiled Python wheel is not
available on PyPI for your platform, you may need a set of development tools installed
on your machine, before you install BinPackage using `pip`:

```bash
# The following works on Debian/Ubuntu GNU/Linux
sudo apt-get install python3-dev libffi-dev
```

BinPackage is fully type-annotated for use with Python static type checkers such
as `mypy` and `Pylance` / `Pyright`.

# Installation and setup

You must have Python >= 3.9 installed on your machine (CPython or PyPy).
If you are using a Python virtual environment (`virtualenv`), activate it
first (substituting your environment name for `venv` below):

```bash
venv/bin/activate
```

...or, on Windows:

```cmd
C:\> venv\scripts\activate
```

Then, install BinPackage from the Python Package Index (PyPI),
where the package is called `islenska`:

```bash
pip install islenska
```

Now, you are ready to `import islenska` or `from islenska import Bin`
in your Python code.

----

If you want to install the package in editable source code mode,
do as follows:

```bash
# Clone the GitHub repository
git clone https://github.com/mideind/BinPackage
cd BinPackage
# Install the package in editable mode
pip install -e .  # Note the dot!
cd src/islenska/resources
# Fetch the newest BÍN data (KRISTINsnid.csv.zip)
# (We remind you that the BÍN data is under the CC BY-SA 4.0 license; see below.)
wget -O KRISTINsnid.csv.zip https://bin.arnastofnun.is/django/api/nidurhal/?file=KRISTINsnid.csv.zip
# Unzip the data
unzip -q KRISTINsnid.csv.zip
rm KRISTINsnid.csv.*
cd ../../..
# Run the compressor to generate src/islenska/resources/compressed.bin
python tools/binpack.py
# Run the DAWG builder for the prefix and suffix files
python tools/dawgbuilder.py
# Now you're ready to go
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
* `basics.py`: Basic data structures, such as the `BinEntry` NamedTuple.
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

BinPackage embeds the vocabulary of the
**[Database of Icelandic Morphology](https://bin.arnastofnun.is/DMII/)**
(**[Beygingarlýsing íslensks nútímamáls](https://bin.arnastofnun.is/)**),
abbreviated *BÍN*.

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

----

**Miðeind ehf., the publisher of BinPackage, claims no endorsement, sponsorship,**
**or official status granted to it by the BÍN copyright holder.**

BinPackage includes certain program logic, created by Miðeind ehf.,
that optionally exposes additions and modifications to the original
BÍN source data. Such logic is enabled or disabled by user-settable flags,
as described in the documentation above.

----

BinPackage is Copyright © 2024 [Miðeind ehf.](https://mideind.is)
The original author of this software is *Vilhjálmur Þorsteinsson*.

<img src="img/MideindLogoVert400.png" alt="Miðeind ehf."
   width="118" height="100" align="left"
   style="margin-right:20px; margin-top: 10px; margin-bottom: 10px;">

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
