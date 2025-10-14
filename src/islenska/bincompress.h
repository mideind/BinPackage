/*

   BinPackage

   C++ BinCompressed dictionary module

   Copyright © 2025 Miðeind ehf.
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

*/

#include <stdint.h>

// C99 bool support (C++ has bool built-in)
#ifndef __cplusplus
#include <stdbool.h>
#endif

typedef uint8_t BYTE;
typedef uint32_t UINT;

// Opaque handle for the BinCompressed dictionary
typedef void* BcHandle;

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Initialize a BinCompressed dictionary from a memory-mapped file.
 *
 * @param pbMap Pointer to the beginning of the compressed dictionary file
 * @return Handle to the dictionary, or NULL if initialization fails
 *
 * @note The caller must ensure the memory mapping remains valid for the
 *       lifetime of the returned handle.
 */
BcHandle bin_compressed_init(const BYTE* pbMap);

/**
 * Close and free a BinCompressed dictionary.
 *
 * @param handle Handle returned by bin_compressed_init()
 */
void bin_compressed_close(BcHandle handle);

/**
 * Check if a word exists in the dictionary.
 *
 * @param handle Handle returned by bin_compressed_init()
 * @param word Latin-1 encoded word to search for
 * @return true if word exists in dictionary, false otherwise
 */
bool bin_compressed_contains(BcHandle handle, const char* word);

/**
 * Lookup a word and return results as a JSON string.
 *
 * Returns a JSON array of BinEntry objects:
 * [
 *   {"stofn": "...", "utg": 123, "ofl": "...", "fl": "...", "ordmynd": "...", "beyging": "..."},
 *   ...
 * ]
 *
 * @param handle Handle returned by bin_compressed_init()
 * @param word Latin-1 encoded word to search for
 * @param cat Optional word category filter (NULL for no filter)
 * @param lemma Optional lemma filter (NULL for no filter)
 * @param utg Optional BÍN ID filter (-1 for no filter)
 * @return JSON string (must be freed with bin_compressed_free_string), or NULL if not found
 */
char* bin_compressed_lookup(
    BcHandle handle,
    const char* word,
    const char* cat,
    const char* lemma,
    int utg
);

/**
 * Lookup a word and return Ksnid results as a JSON string.
 *
 * Returns a JSON array of Ksnid objects:
 * [
 *   {"ord": "...", "bin_id": 123, "ofl": "...", "hluti": "...", "form": "...", "mark": "...", "ksnid": "..."},
 *   ...
 * ]
 *
 * @param handle Handle returned by bin_compressed_init()
 * @param word Latin-1 encoded word to search for
 * @param cat Optional word category filter (NULL for no filter)
 * @param lemma Optional lemma filter (NULL for no filter)
 * @param utg Optional BÍN ID filter (-1 for no filter)
 * @return JSON string (must be freed with bin_compressed_free_string), or NULL if not found
 */
char* bin_compressed_lookup_ksnid(
    BcHandle handle,
    const char* word,
    const char* cat,
    const char* lemma,
    int utg
);

/**
 * Get all word forms associated with a lemma.
 *
 * Returns a JSON array of word forms (as UTF-8 encoded strings):
 * ["form1", "form2", ..., "lemma"]
 *
 * The forms are decompressed from the templates section and include
 * all inflected variants plus the base lemma itself.
 *
 * @param handle Handle returned by bin_compressed_init()
 * @param bin_id BÍN ID number
 * @return JSON string (must be freed with bin_compressed_free_string), or NULL if not found
 */
char* bin_compressed_lemma_forms(BcHandle handle, int bin_id);

/**
 * Get all Ksnid entries for a given BÍN ID.
 *
 * Returns a JSON array of Ksnid objects for all word forms of the lemma:
 * [
 *   {"ord": "...", "bin_id": 123, "ofl": "...", "hluti": "...", "form": "...", "mark": "...", "ksnid": "..."},
 *   ...
 * ]
 *
 * @param handle Handle returned by bin_compressed_init()
 * @param bin_id BÍN ID number
 * @return JSON string (must be freed with bin_compressed_free_string), or NULL if not found
 */
char* bin_compressed_lookup_id(BcHandle handle, int bin_id);

/**
 * Free a string returned by bin_compressed functions.
 *
 * @param str String to free (may be NULL)
 */
void bin_compressed_free_string(char* str);

#ifdef __cplusplus
}
#endif
