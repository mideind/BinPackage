/*

   BinPackage

   libbin: C API for the compressed BÍN dictionary and the compounder

   Copyright © 2026 Miðeind ehf.
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

   This is the complete public interface of libbin. It is consumed by the
   Python package (via CFFI, which reads the section between the CFFI-BEGIN
   and CFFI-END markers verbatim, so keep that section free of preprocessor
   directives and C++ constructs) and by C/C++ clients such as GreynirKbd.

   Conventions:

   - All strings passed in and out are Latin-1 encoded and NUL-terminated.
     Every character of Icelandic fits in Latin-1, and this is also the
     encoding of the data files, so no conversion happens on the hot path.
   - The library never owns the memory maps it is given. The caller maps
     the data files (compressed.bin and the three ordalisti-*.dawg.bin
     files) and keeps the maps valid for the lifetime of the handles.
   - Handles are immutable after creation and safe to share between threads
     without locking. Result objects belong to the caller and are freed
     with the matching *_free function.

*/

#ifndef LIBBIN_BIN_H
#define LIBBIN_BIN_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* CFFI-BEGIN */

/* A packed DAWG (ordalisti-*.dawg.bin), used by the compounder */
typedef struct BinDawg BinDawg;

/* A compressed BÍN dictionary (compressed.bin) with, optionally, the
   three compounder DAWGs. */
typedef struct BinDict BinDict;

/* One BÍN entry, i.e. one reading of a word form. */
typedef struct {
    const char* ord;     /* lemma (stofn) */
    uint32_t bin_id;     /* BÍN id of the lemma (utg); 0 for synthetic entries */
    const char* ofl;     /* word category (kk, kvk, hk, so, lo, ...) */
    const char* hluti;   /* subcategory / domain (fl) */
    const char* bmynd;   /* word form (ordmynd) */
    const char* mark;    /* inflection description (beyging) */
    const char* ksnid;   /* the additional KRISTINsnid fields, ';'-separated */
} BinEntry;

/* A list of entries. */
typedef struct {
    BinEntry* entries;
    uint32_t count;
    /* Nonzero if the entries were restored by the compact build's
       compounder rather than found in the word-form trie. */
    int restored;
    /* bin_compound_lookup only: the word that was actually split, i.e.
       the query or its lowercase form. */
    const char* word;
} BinResult;

/* A raw entry: indices into the dictionary's tables, as stored in the
   mappings section. Decode with bin_meaning(), bin_ksnid_string() and
   bin_lemma(). */
typedef struct {
    uint32_t bin_id;
    uint32_t meaning_index;
    uint32_t ksnid_index;
} BinRawEntry;

typedef struct {
    BinRawEntry* entries;
    uint32_t count;
} BinRawResult;

/* A list of strings. */
typedef struct {
    char** items;
    uint32_t count;
} BinStrings;

/* A list of compound splits, each a list of word parts. */
typedef struct {
    BinStrings* splits;
    uint32_t count;
} BinSplits;

/* A decoded lemma record. */
typedef struct {
    const char* lemma;
    const char* hluti;      /* subcategory (fl) */
    int dropped;            /* nonzero if this lemma is dropped from the
                               word-form trie of a compact build */
    uint32_t ksnid_index;   /* dropped lemmas only: the shared ksnid string */
    const uint32_t* heads;  /* dropped lemmas only: bin_ids of the kept
                               lemmas that regenerate this one */
    uint32_t num_heads;
} BinLemma;

/* ---- DAWGs ---- */

/* Load a packed DAWG from a memory map. Returns NULL if the signature is
   wrong. The map must outlive the handle. */
BinDawg* bin_dawg_open(const uint8_t* map, size_t len);
void bin_dawg_close(BinDawg* dawg);
int bin_dawg_contains(const BinDawg* dawg, const char* word);
/* All ways of splitting the word into a sequence of DAWG words, in the
   order of the depth-first search (shorter first parts first, the
   single-part split last). */
BinSplits* bin_dawg_find_combinations(const BinDawg* dawg, const char* word);

/* ---- Dictionary ---- */

/* Open a dictionary over a memory-mapped compressed.bin. The three DAWGs
   (all forms, prefixes, suffixes) are optional; without them the
   compound functions return nothing, and a compact build (see
   bin_is_compact) cannot restore its dropped compounds. Returns NULL on
   error, with a message in errbuf if given. The maps and the DAWG handles
   must outlive the dictionary. */
BinDict* bin_open(const uint8_t* map, size_t len,
                  const BinDawg* dawg_all, const BinDawg* dawg_prefixes,
                  const BinDawg* dawg_suffixes,
                  char* errbuf, size_t errbuf_len);
void bin_close(BinDict* dict);

/* Nonzero if this is a compact build, i.e. a file from which the word
   forms of exactly regenerable compounds were left out (tools/binpack.py
   --compact). All lookups below restore those compounds transparently,
   with their original bin_ids and metadata, provided the DAWGs are
   present. */
int bin_is_compact(const BinDict* dict);
int bin_has_dawgs(const BinDict* dict);
/* The lowest bin_id of the Greynir additions (ord.add.csv etc.) */
uint32_t bin_begin_greynir_utg(const BinDict* dict);
/* The highest bin_id in the dictionary */
uint32_t bin_max_bin_id(const BinDict* dict);

/* Is the word form in the dictionary? */
int bin_contains(const BinDict* dict, const char* word);

/* All entries of a word form. cat and lemma are optional filters (NULL
   for none; cat "no" matches any noun gender); bin_id 0 means no filter.
   Returns NULL if nothing is found. */
BinResult* bin_lookup(const BinDict* dict, const char* word,
                      const char* cat, const char* lemma, uint32_t bin_id);
/* The raw entries of a word form (NULL if none). */
BinRawResult* bin_lookup_raw(const BinDict* dict, const char* word);
/* All entries of a lemma, given its bin_id (NULL if unknown). */
BinResult* bin_lookup_id(const BinDict* dict, uint32_t bin_id);
/* All word forms of a lemma, the lemma itself last (NULL if unknown). */
BinStrings* bin_lemma_forms(const BinDict* dict, uint32_t bin_id);

/* Decode a lemma record. Returns 0 if the bin_id is unknown. The
   pointers in the record are valid until bin_lemma_free. */
BinLemma* bin_lemma(const BinDict* dict, uint32_t bin_id);
void bin_lemma_free(BinLemma* lemma);
/* Decode a meaning index into (ofl, mark): two strings. */
BinStrings* bin_meaning(const BinDict* dict, uint32_t meaning_index);
/* Decode a ksnid string index. The result must be freed with bin_string_free. */
char* bin_ksnid_string(const BinDict* dict, uint32_t ksnid_index);

/* ---- Compounds ---- */

/* The legal compound splits of the word in the ranking order of the
   compounder: longest last part first, then fewest parts. A split is
   legal when its last part is in the suffix DAWG and every other part is
   in the prefix DAWG; the single-part split (the whole word, if it is a
   legal suffix) is included. NULL if there is none or no DAWGs. */
BinSplits* bin_compound_candidates(const BinDict* dict, const char* word);

/* The split that the compounder settles on for the word: the first
   candidate whose last part is not a defective noun (one lacking a
   singular or a plural), or the first candidate if all are. Returns a
   list of exactly one split, or NULL if the word does not split. This is
   the policy of Bin._compound_meanings() in bindb.py. */
BinSplits* bin_compound_split(const BinDict* dict, const char* word);

typedef struct {
    /* Mark the boundaries found by the compounder with a hyphen in the
       lemma and the word form ('b\xf3ka-hilla'); otherwise concatenate. */
    int insert_hyphen;
    /* Keep only noun readings of the last part (for a capitalized word in
       the middle of a sentence); otherwise keep the readings in the open
       word categories (nouns, adjectives, verbs). */
    int nouns_only;
    /* If the word has no legal split, try its lowercase form; the result
       then reports the lowercase word. */
    int try_lowercase;
} BinCompoundOptions;

/* Interpret a word that is not in the dictionary as a compound: the
   readings of the last part of its chosen split (bin_compound_split),
   with the other parts glued onto the lemma and the word form, and bin_id
   0. Readings marked as Greynir additions are left out, suffix-only
   entries (ord.suffixes.csv) are included. NULL if the word does not
   split or the last part has no acceptable reading. */
BinResult* bin_compound_lookup(const BinDict* dict, const char* word, const BinCompoundOptions* options);

/* ---- Memory ---- */

void bin_result_free(BinResult* result);
void bin_raw_result_free(BinRawResult* result);
void bin_strings_free(BinStrings* strings);
void bin_splits_free(BinSplits* splits);
void bin_string_free(char* s);

/* CFFI-END */

#ifdef __cplusplus
}
#endif

#endif /* LIBBIN_BIN_H */
