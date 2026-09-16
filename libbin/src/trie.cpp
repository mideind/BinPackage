/*

   BinPackage

   libbin: the compressed word-form trie

   Copyright © 2026 Miðeind ehf.
   Original author: Vilhjálmur Þorsteinsson

   This software is licensed under the MIT License; see bin.h.

   Node layout (all little-endian, 32-bit aligned):

      Single-character node:
         1 bit  : 1
         1 bit  : childless
         7 bits : index of the character in the alphabet, plus one
         23 bits: value (mappings index), 0x7FFFFF if none
      Multi-character node:
         1 bit  : 0
         1 bit  : childless
         7 bits : 0
         23 bits: value
         [number of children, then their offsets, unless childless]
         NUL-terminated fragment, padded to 32 bits

   Children are sorted by their first character (Latin-1 ordinal), which
   allows a binary search at each level.

*/

#include <string.h>

#include "trie.h"

namespace libbin {

namespace {

inline uint32_t u32(const uint8_t* p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

// Header offsets (see tools/binpack.py, BinCompressor.write_binary())
const uint32_t HDR_FORMS_OFFSET = 20;
const uint32_t HDR_ALPHABET_OFFSET = 36;

class TrieSearch {
   private:
    const uint8_t* m_map;
    const uint8_t* m_alphabet;
    const uint8_t* m_word;
    uint32_t m_len;

    uint32_t at(uint32_t offset) const { return u32(m_map + offset); }

    // If the fragment word[index:] matches the node, return the number of
    // characters matched. Otherwise return -1 if the node is
    // lexicographically less than the fragment, or 0 if it is greater.
    int matches(uint32_t node, uint32_t hdr, uint32_t index) const {
        if (hdr & 0x80000000u) {
            // Single-character fragment
            uint8_t ch = m_alphabet[((hdr >> 23) & 0x7F) - 1];
            uint8_t wch = m_word[index];
            if (ch == wch) {
                return 1;
            }
            return (ch > wch) ? 0 : -1;
        }
        uint32_t frag;
        if (hdr & 0x40000000u) {
            // Childless node
            frag = node + 4;
        } else {
            uint32_t num_children = at(node + 4);
            frag = node + 8 + 4 * num_children;
        }
        const uint8_t* p = m_map + frag;
        int matched = 0;
        while (*p && (index + matched < m_len) && (*p == m_word[index + matched])) {
            p++;
            matched++;
        }
        if (!*p) {
            // Matched the entire fragment
            return matched;
        }
        if (index + matched >= m_len) {
            // The node is longer, and thus greater, than the fragment
            return 0;
        }
        return (*p > m_word[index + matched]) ? 0 : -1;
    }

   public:
    TrieSearch(const uint8_t* map, const uint8_t* word)
        : m_map(map),
          m_alphabet(map + u32(map + HDR_ALPHABET_OFFSET) + 4),
          m_word(word),
          m_len((uint32_t)strlen((const char*)word)) {}

    uint32_t run() const {
        uint32_t node = u32(m_map + HDR_FORMS_OFFSET);
        uint32_t hdr = at(node);
        uint32_t index = 0;
        for (;;) {
            if (index >= m_len) {
                // Arrived: return the value, unless this is an interim node
                uint32_t value = hdr & 0x007FFFFFu;
                return (value == 0x007FFFFFu) ? TRIE_NOT_FOUND : value;
            }
            if (hdr & 0x40000000u) {
                // Childless node: nowhere to go
                return TRIE_NOT_FOUND;
            }
            uint32_t num_children = at(node + 4);
            uint32_t children = node + 8;
            // Binary search for a matching child
            uint32_t lo = 0;
            uint32_t hi = num_children;
            bool descended = false;
            while (!descended) {
                if (lo >= hi) {
                    return TRIE_NOT_FOUND;
                }
                uint32_t mid = (lo + hi) / 2;
                uint32_t mid_node = at(children + mid * 4);
                uint32_t mid_hdr = at(mid_node);
                int m = matches(mid_node, mid_hdr, index);
                if (m > 0) {
                    node = mid_node;
                    hdr = mid_hdr;
                    index += (uint32_t)m;
                    descended = true;
                } else if (m < 0) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }
        }
    }
};

}  // namespace

uint32_t trie_lookup(const uint8_t* map, const uint8_t* word) {
    if (!map || !word || !*word) {
        return TRIE_NOT_FOUND;
    }
    return TrieSearch(map, word).run();
}

}  // namespace libbin
