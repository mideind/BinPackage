/*

   BinPackage

   libbin: the compressed word-form trie

   Copyright © 2026 Miðeind ehf.
   Original author: Vilhjálmur Þorsteinsson

   This software is licensed under the MIT License; see bin.h.

   The forms section of compressed.bin is a packed radix trie that maps
   Latin-1 word forms to indices into the mappings section. It is written
   by BinCompressor.write_forms() in tools/binpack.py.

*/

#ifndef LIBBIN_TRIE_H
#define LIBBIN_TRIE_H

#include <stdint.h>

namespace libbin {

const uint32_t TRIE_NOT_FOUND = 0xFFFFFFFFu;

// Return the mappings index of the given Latin-1 word form, or
// TRIE_NOT_FOUND. The map points at the start of compressed.bin; the
// trie root and the alphabet are located via the file header.
uint32_t trie_lookup(const uint8_t* map, const uint8_t* word);

}  // namespace libbin

#endif  // LIBBIN_TRIE_H
