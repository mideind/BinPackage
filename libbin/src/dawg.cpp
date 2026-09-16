/*

   BinPackage

   libbin: packed DAWG reader

   Copyright © 2026 Miðeind ehf.
   Original author: Vilhjálmur Þorsteinsson

   This software is licensed under the MIT License; see bin.h.

   File layout (see tools/dawgbuilder.py):

      "ReynirDawg!\n"          12-byte signature
      uint32 len_voc           length of the vocabulary in bytes
      vocabulary               UTF-8, one character per vocabulary index
      graph                    nodes, the root node first

   A node is a header byte whose low 7 bits are the number of outgoing
   edges (the high bit marks a final node) followed by the edges. An edge
   is a length byte (low 7 bits) followed by that many character codes,
   each the index of the character in the vocabulary, with the high bit
   set on a code whose character ends a word. Unless the last code is
   final, a uint32 offset of the next node follows the codes.

   Navigation only ever follows the single edge whose first character is
   the next character of the word being matched, so no node needs to be
   decoded in full and no state needs to be cached: a lookup touches the
   map read-only.

*/

#include <string.h>

#include <stdexcept>

#include "dawg.h"

namespace libbin {

namespace {

inline uint32_t u32(const uint8_t* p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

// Decode the UTF-8 vocabulary into Latin-1 characters
size_t decode_vocabulary(const uint8_t* utf8, size_t len, char* out, size_t out_max) {
    size_t n = 0;
    for (size_t i = 0; i < len && n < out_max;) {
        uint8_t c = utf8[i];
        if (c < 0x80) {
            out[n++] = (char)c;
            i += 1;
        } else if ((c & 0xE0) == 0xC0 && i + 1 < len) {
            uint32_t cp = ((uint32_t)(c & 0x1F) << 6) | (utf8[i + 1] & 0x3F);
            out[n++] = (char)(cp > 255 ? '?' : cp);
            i += 2;
        } else {
            // Not expected in Icelandic data
            out[n++] = '?';
            i += 1;
        }
    }
    return n;
}

}  // namespace

// Navigator for an exact word match
class FindNav {
   public:
    const std::string& word;
    size_t index = 0;
    bool found = false;
    explicit FindNav(const std::string& w) : word(w) {}
    bool accepting() const { return index < word.size(); }
    bool accepts(char c) {
        if (index >= word.size() || word[index] != c) {
            return false;
        }
        index++;
        return true;
    }
    void accept(const std::string& matched, bool is_final) {
        (void)matched;
        if (is_final && index == word.size()) {
            found = true;
        }
    }
};

// Navigator that collects every split of the word into DAWG words
class CompoundNav {
   public:
    const Dawg& dawg;
    const std::string& word;
    size_t index = 0;
    std::vector<std::vector<std::string>> parts;
    CompoundNav(const Dawg& d, const std::string& w) : dawg(d), word(w) {}
    bool accepting() const { return index < word.size(); }
    bool accepts(char c) {
        if (index >= word.size() || word[index] != c) {
            return false;
        }
        index++;
        return true;
    }
    void accept(const std::string& matched, bool is_final) {
        if (!is_final) {
            return;
        }
        if (index == word.size()) {
            // The entire word has been consumed: a single-part solution
            parts.push_back(std::vector<std::string>{matched});
            return;
        }
        // Split the remainder recursively
        std::string remainder = word.substr(index);
        CompoundNav sub(dawg, remainder);
        dawg.navigate(sub);
        for (auto& tail : sub.parts) {
            std::vector<std::string> combination;
            combination.reserve(tail.size() + 1);
            combination.push_back(matched);
            combination.insert(combination.end(), tail.begin(), tail.end());
            parts.push_back(std::move(combination));
        }
    }
};

Dawg::Dawg(const uint8_t* map, size_t len) : m_map(map), m_root(0), m_voc_len(0) {
    if (!map || len < 16 || memcmp(map, "ReynirDawg!\n", 12) != 0) {
        throw std::runtime_error("Invalid DAWG file signature");
    }
    uint32_t len_voc = u32(map + 12);
    if (16 + (size_t)len_voc > len) {
        throw std::runtime_error("Truncated DAWG file");
    }
    m_voc_len = decode_vocabulary(map + 16, len_voc, m_voc, sizeof(m_voc));
    m_root = 16 + len_voc;
}

template <class Nav>
void Dawg::navigate(Nav& nav) const {
    if (nav.accepting()) {
        std::string matched;
        navigate_from_node(nav, m_root, matched);
    }
}

template <class Nav>
void Dawg::navigate_from_node(Nav& nav, uint32_t offset, std::string& matched) const {
    const uint8_t* b = m_map;
    uint32_t p = offset;
    unsigned num_edges = b[p++] & 0x7F;
    // The navigator only ever accepts the next character of its word, and
    // the edges of a node start with distinct characters, so at most one
    // edge is followed: find it without decoding the others.
    char want = nav.accepting() ? nav.word[nav.index] : '\0';
    for (unsigned i = 0; i < num_edges; i++) {
        unsigned n = b[p++] & 0x7F;
        const uint8_t* codes = b + p;
        p += n;
        bool last_final = n > 0 && (codes[n - 1] & 0x80) != 0;
        uint32_t next = 0;
        if (!last_final) {
            next = u32(b + p);
            p += 4;
        }
        if (n == 0 || m_voc[codes[0] & 0x7F] != want) {
            continue;
        }
        // Walk the edge character by character
        size_t start = matched.size();
        for (unsigned j = 0; j < n; j++) {
            if (!nav.accepting()) {
                matched.resize(start);
                return;
            }
            uint8_t code = codes[j];
            char c = m_voc[code & 0x7F];
            if (!nav.accepts(c)) {
                matched.resize(start);
                return;
            }
            matched.push_back(c);
            bool is_final = (code & 0x80) != 0;
            if (j == n - 1 && (next == 0 || (b[next] & 0x80))) {
                is_final = true;
            }
            nav.accept(matched, is_final);
        }
        if (next != 0 && nav.accepting()) {
            navigate_from_node(nav, next, matched);
        }
        matched.resize(start);
        return;
    }
}

bool Dawg::contains(const std::string& word) const {
    if (word.empty()) {
        return false;
    }
    FindNav nav(word);
    navigate(nav);
    return nav.found;
}

std::vector<std::vector<std::string>> Dawg::find_combinations(const std::string& word) const {
    if (word.empty()) {
        return {};
    }
    CompoundNav nav(*this, word);
    navigate(nav);
    return std::move(nav.parts);
}

}  // namespace libbin
