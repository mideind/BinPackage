/*

   BinPackage

   libbin: packed DAWG reader

   Copyright © 2026 Miðeind ehf.
   Original author: Vilhjálmur Þorsteinsson

   This software is licensed under the MIT License; see bin.h.

   Reads the ordalisti-*.dawg.bin files written by tools/dawgbuilder.py:
   a set of words in a directed acyclic word graph, used by the compounder
   to find the ways a word can be sliced into dictionary words.

   A Dawg is immutable after construction and safe to use from several
   threads at once; navigation state lives on the stack of the caller.

*/

#ifndef LIBBIN_DAWG_H
#define LIBBIN_DAWG_H

#include <stddef.h>
#include <stdint.h>

#include <string>
#include <vector>

namespace libbin {

class Dawg {
   public:
    // Throws std::runtime_error if the map is not a packed DAWG
    Dawg(const uint8_t* map, size_t len);

    // Is the Latin-1 word in the set?
    bool contains(const std::string& word) const;

    // All ways of splitting the Latin-1 word into a sequence of words in
    // the set, in depth-first order: shorter first parts come first and
    // the single-part split (if the word itself is in the set) last.
    std::vector<std::vector<std::string>> find_combinations(const std::string& word) const;

   private:
    friend class FindNav;
    friend class CompoundNav;

    const uint8_t* m_map;
    uint32_t m_root;
    // Vocabulary: code & 0x7F -> Latin-1 character
    char m_voc[128];
    size_t m_voc_len;

    // Depth-first navigation from the root, following the characters of
    // word from position index; nav is called back at each dictionary
    // word encountered. See dawg.cpp.
    template <class Nav>
    void navigate(Nav& nav) const;
    template <class Nav>
    void navigate_from_node(Nav& nav, uint32_t offset, std::string& matched) const;
};

}  // namespace libbin

#endif  // LIBBIN_DAWG_H
