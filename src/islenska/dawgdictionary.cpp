/*

   BinPackage

   C++ DAWG dictionary module

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

   --------------------------------------------------------------------------

   This module implements a C++ interface to packed DAWG (Directed Acyclic
   Word Graph) dictionaries for efficient storage and lookup of Icelandic
   word forms, primarily for compound word analysis.

   DAWG STRUCTURE:

   A DAWG is a trie-like data structure where common suffixes are merged,
   resulting in a directed acyclic graph. This provides both space efficiency
   (shared storage of common word parts) and time efficiency (fast lookups).

   BINARY FILE FORMAT:

   The binary DAWG file uses a custom packed format:

   [Header - 12 bytes]
     - Signature: "ReynirDawg!\n" (12 bytes)

   [Vocabulary section]
     - Length: 4-byte little-endian uint32 (number of UTF-8 bytes)
     - Data: UTF-8 encoded string of all unique characters in the vocabulary

   [Graph section - starts at offset (16 + vocabulary_length)]
     - Root node followed by all other nodes in the graph

   NODE FORMAT:

   Each node consists of:
     - Header byte: Lower 7 bits = number of outgoing edges
                   (High bit is reserved/unused at node level)
     - Series of edges (described below)

   EDGE FORMAT:

   Each edge from a node consists of:
     - Length byte: Lower 7 bits = number of character codes in prefix
                   (High bit reserved/unused at edge level)
     - Prefix bytes: Array of vocabulary indices (character codes)
       * Each byte is an index into the vocabulary string
       * High bit (0x80) on a byte indicates "final" marker (see below)
       * The encoding map converts these indices to actual characters
     - Next node offset (optional): 4-byte little-endian uint32
       * Only present if the last prefix byte does NOT have the 0x80 bit set
       * If 0x80 bit is set on last byte, the edge terminates (nextnode = 0)

   FINALITY MARKER:

   The 0x80 (128) bit on the LAST byte of an edge prefix indicates that
   the word formed by following the path up to (and including) that character
   is a complete, valid word in the dictionary. This allows a single edge to
   encode multiple word boundaries. For example:

     - Edge with prefix "ing" where 'g' has 0x80 bit set:
       The word ending in 'g' is final (complete word).
     - Edge with prefix "ings" where only 's' has 0x80 bit set:
       The word ending in 's' is final, but 'ing' is not.

   The encoding map stores two versions of each character:
     - Index i: The character itself (e.g., 'a')
     - Index i|0x80: The character with a pipe suffix (e.g., 'a|')

   The pipe character '|' in the decoded prefix indicates a finality point.

   ENCODING:

   Characters in the vocabulary are stored as UTF-8 bytes in the file, but
   converted to Latin-1 (ISO-8859-1) strings during processing. The Icelandic
   alphabet fits entirely within Latin-1, so no information is lost.

   Each character is assigned an index (0, 1, 2, ...) based on its position
   in the vocabulary. The DAWG uses these indices (not the actual character
   codes) to represent characters in edges. This allows for compact storage
   when the vocabulary is small (< 128 characters, since we need 1 bit for
   the finality marker).

   NAVIGATION:

   Navigating the DAWG involves following edges from the root node while
   matching characters from the input word. The Navigator pattern is used
   to control the navigation logic:

     - FindNavigator: Simple word lookup (does word exist in DAWG?)
     - CompoundNavigator: Recursive compound word splitting

   The navigation caches decoded edges in m_iter_cache to avoid repeated
   parsing of the same nodes.

*/

#include <string>
#include <vector>
#include <map>
#include <sstream>
#include <cstring>
#include <algorithm>
#include <stdexcept>

#include "dawgdictionary.h"

#define TRUE 1
#define FALSE 0

typedef uint32_t UINT32;

// Forward declarations
class DAWG_Dictionary;
class PackedNavigation;

/**
 * Convert a UTF-8 byte array to a Latin-1 (ISO-8859-1) string.
 *
 * The DAWG vocabulary is stored as UTF-8 in the binary file, but we convert
 * it to Latin-1 for processing since all Icelandic characters fit within
 * Latin-1 (ISO-8859-1). This simplifies string handling in C++.
 *
 * @param utf8_bytes  Pointer to UTF-8 encoded byte array
 * @param utf8_len    Length of the UTF-8 byte array
 * @return Latin-1 encoded string with the same character content
 *
 * @note Only handles single-byte (ASCII) and 2-byte UTF-8 sequences.
 *       3-byte and 4-byte sequences are replaced with '?' but should
 *       not occur in Icelandic vocabulary per project guarantees.
 */
std::string utf8_to_latin1(const BYTE* utf8_bytes, size_t utf8_len) {
    std::string latin1_str;
    latin1_str.reserve(utf8_len);
    for (size_t i = 0; i < utf8_len; ) {
        BYTE c = utf8_bytes[i];
        if (c < 0x80) { // Standard ASCII
            latin1_str += c;
            i += 1;
        } else if ((c & 0xE0) == 0xC0) { // 2-byte UTF-8 sequence
            if (i + 1 < utf8_len) {
                size_t codepoint = ((c & 0x1F) << 6) | (utf8_bytes[i + 1] & 0x3F);
                latin1_str += (char)(codepoint > 255 ? '?' : codepoint);
                i += 2;
            } else {
                latin1_str += '?'; // Malformed
                i += 1;
            }
        } else {
            // Per project guarantees, we don't expect 3- or 4-byte sequences
            latin1_str += '?'; // Malformed or unexpected
            i += 1;
        }
    }
    return latin1_str;
}

/**
 * Abstract base class for DAWG navigation strategies.
 *
 * The Navigator pattern allows different types of DAWG traversals
 * (simple lookup, compound word splitting, etc.) to be implemented
 * by subclassing and providing custom logic for accepting/rejecting
 * characters and edges during graph traversal.
 *
 * The navigation engine (PackedNavigation) calls these methods to
 * control the traversal:
 *
 *   1. push_edge(): Determines if an edge should be explored
 *   2. accepts(): Determines if a character should be accepted
 *   3. accept(): Called when a (partial or complete) match is found
 *   4. pop_edge(): Called after exploring an edge (can short-circuit)
 *   5. accepting(): Determines if navigation should continue
 */
class Navigator {
public:
    virtual ~Navigator() {}

    /** Check if an edge starting with firstchar should be explored */
    virtual bool push_edge(char firstchar) = 0;

    /** Check if the navigator is still accepting more characters */
    virtual bool accepting() = 0;

    /** Accept a character and advance position. Returns false if char doesn't match */
    virtual bool accepts(char newchar) = 0;

    /** Called when a match (partial or complete) is found
     *  @param matched The string matched so far
     *  @param final   True if this is a complete word (has finality marker)
     */
    virtual void accept(const std::string& matched, bool final) = 0;

    /** Called after exploring an edge. Return false to short-circuit navigation */
    virtual bool pop_edge() = 0;
};

/**
 * Navigator for simple word existence checks.
 *
 * FindNavigator performs a straightforward lookup: it follows the path
 * matching the input word character-by-character. If the navigation
 * reaches the end of the word AND encounters a finality marker, the
 * word is found.
 *
 * This is used by DAWG_Dictionary::contains() for "word in dictionary"
 * queries.
 */
class FindNavigator : public Navigator {
private:
    const std::string& m_word;
    size_t m_len;
    size_t m_index;
    bool m_found;

public:
    FindNavigator(const std::string& word) : m_word(word), m_len(word.length()), m_index(0), m_found(false) {}

    bool push_edge(char firstchar) override {
        // Only explore edges that match the next character in our word
        if (m_index >= m_len) return false;
        return m_word[m_index] == firstchar;
    }

    bool accepting() override {
        // Continue while we haven't consumed the entire word
        return m_index < m_len;
    }

    bool accepts(char newchar) override {
        // Accept only if the character matches the next position in word
        if (m_index >= m_len || newchar != m_word[m_index]) {
            return false;
        }
        m_index++;
        return true;
    }

    void accept(const std::string& matched, bool final) override {
        // Word is found if we've consumed all characters AND hit a final marker
        if (final && m_index == m_len) {
            m_found = true;
        }
    }

    bool pop_edge() override {
        // Short-circuit: stop searching once we've explored an edge
        // (no need to continue since we're doing exact match)
        return false;
    }

    bool is_found() const {
        return m_found;
    }
};

/**
 * Navigator for compound word analysis.
 *
 * CompoundNavigator attempts to split an unknown word into valid parts
 * (compound word decomposition). When it finds a complete word that is
 * a prefix of the input, it recursively searches for ways to split the
 * remainder.
 *
 * For example, "efnahagsráðherra" might be split as:
 *   - ["efnahags", "ráðherra"]
 *   - ["efna", "hags", "ráðherra"]
 *
 * The navigator returns all possible splits where each part is a valid
 * word in the DAWG.
 *
 * This is used by DAWG_Dictionary::find_combinations() for compound
 * word analysis in Icelandic text processing.
 */
class CompoundNavigator : public Navigator {
private:
    DAWG_Dictionary* m_dawg;
    const std::string& m_word;
    size_t m_len;
    size_t m_index;
    std::vector<std::vector<std::string>> m_parts;

public:
    CompoundNavigator(DAWG_Dictionary* dawg, const std::string& word);

    bool push_edge(char firstchar) override {
        if (m_index >= m_len) return false;
        return m_word[m_index] == firstchar;
    }

    bool accepting() override {
        return m_index < m_len;
    }

    bool accepts(char newchar) override {
        if (m_index >= m_len || newchar != m_word[m_index]) {
            return false;
        }
        m_index++;
        return true;
    }

    void accept(const std::string& matched, bool final) override;

    bool pop_edge() override {
        return false; // Short-circuit
    }

    std::vector<std::vector<std::string>> result() const {
        return m_parts;
    }
};

/**
 * Main DAWG dictionary class.
 *
 * DAWG_Dictionary loads and provides access to a packed binary DAWG file.
 * It handles:
 *   - Loading and parsing the binary file format
 *   - Building the character encoding map from the vocabulary
 *   - Providing word lookup (contains) and compound splitting (find_combinations)
 *   - Caching parsed nodes for performance
 *
 * The dictionary is initialized from a memory-mapped file pointer and
 * maintains references to that memory throughout its lifetime. The caller
 * is responsible for keeping the memory mapping valid.
 */
class DAWG_Dictionary {
private:
    // Pointer to memory-mapped DAWG file data
    const BYTE* m_pbMap;

    // Byte offset in m_pbMap where the root node begins
    UINT32 m_root_offset;

    // Encoding map: byte code -> character string
    // Maps vocabulary indices (0, 1, 2, ...) to their characters.
    // Also maps (index | 0x80) to character with '|' suffix for finality.
    std::map<BYTE, std::string> m_encoding;

    // Cache of parsed nodes: node_offset -> (prefix -> next_node_offset)
    // Avoids re-parsing the same node multiple times during navigation.
    std::map<UINT32, std::map<std::string, UINT32>> m_iter_cache;

public:
    /**
     * Load a DAWG dictionary from a memory-mapped file.
     * @param pbMap Pointer to the beginning of the DAWG file in memory
     * @throws std::runtime_error if the file signature is invalid
     */
    DAWG_Dictionary(const BYTE* pbMap);
    ~DAWG_Dictionary();

    /**
     * Check if a word exists in the dictionary.
     * @param word Latin-1 encoded word to search for
     * @return true if word is in the dictionary, false otherwise
     */
    bool contains(const std::string& word);

    /**
     * Find all ways to split a word into valid dictionary parts.
     * @param word Latin-1 encoded word to split
     * @return Vector of possible splits, each split is a vector of word parts
     *         Returns empty vector if no valid splits exist
     */
    std::vector<std::vector<std::string>> find_combinations(const std::string& word);

    /**
     * Navigate the DAWG using a custom Navigator strategy.
     * @param nav Navigator that controls the traversal logic
     */
    void navigate(Navigator& nav);

    friend class PackedNavigation;
};

/**
 * Navigation engine for traversing the packed DAWG.
 *
 * PackedNavigation handles the low-level details of:
 *   - Parsing node and edge structures from the binary format
 *   - Decoding character codes using the encoding map
 *   - Managing the navigation state (current position, matched prefix)
 *   - Delegating control decisions to the Navigator
 *
 * It works by starting at the root node and recursively following edges
 * that the Navigator approves, calling Navigator::accept() when matches
 * (partial or complete words) are found.
 */
class PackedNavigation {
private:
    Navigator& m_nav;
    DAWG_Dictionary* m_dawg;
    const BYTE* m_b;
    UINT32 m_root_offset;

    void navigate_from_node(UINT32 offset, std::string matched);
    void navigate_from_edge(const std::string& prefix, UINT32 nextnode, std::string matched);

public:
    PackedNavigation(Navigator& nav, DAWG_Dictionary* dawg)
        : m_nav(nav), m_dawg(dawg), m_b(dawg->m_pbMap), m_root_offset(dawg->m_root_offset) {}

    void go();
};

CompoundNavigator::CompoundNavigator(DAWG_Dictionary* dawg, const std::string& word)
    : m_dawg(dawg), m_word(word), m_len(word.length()), m_index(0) {}

/**
 * Accept a matched word and recursively search for splits of the remainder.
 *
 * This is where the compound word splitting magic happens:
 *
 * 1. If we've matched a complete word (final=true):
 *    a. If we've consumed the entire input word: record single-part solution
 *    b. If there's remaining text: recursively search for ways to split it
 *       - Create a new CompoundNavigator for the remainder
 *       - For each valid split of the remainder, prepend our matched part
 *       - Record all resulting combinations
 *
 * For example, with "efnahagsráðherra":
 *   - When "efnahags" matches (final=true), remainder is "ráðherra"
 *   - Recursive search finds ["ráðherra"] and ["ráð", "herra"]
 *   - Results: ["efnahags", "ráðherra"], ["efnahags", "ráð", "herra"]
 *
 * @param matched The word part matched so far
 * @param final   True if matched is a complete word in the dictionary
 */
void CompoundNavigator::accept(const std::string& matched, bool final) {
    if (!final) {
        return; // Only proceed if we have a complete word
    }
    if (m_index == m_len) {
        // We've consumed the entire input word - single part solution
        m_parts.push_back({matched});
    } else {
        // There's more to match - recursively split the remainder
        std::string remainder = m_word.substr(m_index);
        CompoundNavigator nav(m_dawg, remainder);
        m_dawg->navigate(nav);
        std::vector<std::vector<std::string>> result = nav.result();
        if (!result.empty()) {
            // For each way to split the remainder, prepend our matched part
            for (const auto& tail : result) {
                std::vector<std::string> combination = {matched};
                combination.insert(combination.end(), tail.begin(), tail.end());
                m_parts.push_back(combination);
            }
        }
    }
}

/**
 * Load and initialize a DAWG dictionary from a memory-mapped file.
 *
 * This constructor:
 * 1. Validates the file signature
 * 2. Reads the vocabulary section (UTF-8 encoded)
 * 3. Converts vocabulary to Latin-1 for easier processing
 * 4. Builds the encoding map for decoding edge prefixes
 * 5. Calculates the root node offset
 *
 * ENCODING MAP CONSTRUCTION:
 *
 * The encoding map is critical for decoding the packed format. Each
 * character in the vocabulary gets an index (0, 1, 2, ...). The DAWG
 * stores character INDICES (not the characters themselves) in edges.
 *
 * We create two map entries per character:
 *   - index i: Maps to the character (e.g., 'a')
 *   - index i|0x80: Maps to character+'|' (e.g., 'a|')
 *
 * The '|' suffix indicates a word boundary (finality marker). During
 * edge traversal, when we decode a byte with the 0x80 bit set, we get
 * the character plus '|', signaling that the word up to that point is
 * a complete dictionary entry.
 *
 * @param pbMap Pointer to the beginning of the DAWG file in memory
 * @throws std::runtime_error if file signature is invalid
 */
DAWG_Dictionary::DAWG_Dictionary(const BYTE* pbMap) : m_pbMap(pbMap) {
    // Verify file signature
    if (memcmp(m_pbMap, "ReynirDawg!\n", 12) != 0) {
        throw std::runtime_error("Invalid DAWG file signature");
    }

    // Read vocabulary length (bytes 12-15, little-endian uint32)
    UINT32 len_voc = *(UINT32*)(m_pbMap + 12);

    // Vocabulary starts at byte 16
    const BYTE* voc_bytes = m_pbMap + 16;

    // Graph data starts immediately after vocabulary
    m_root_offset = 16 + len_voc;

    // Convert UTF-8 vocabulary to Latin-1
    // We use Latin-1 because all Icelandic characters fit in ISO-8859-1,
    // and it simplifies string handling (one byte per character)
    std::string voc_string_latin1 = utf8_to_latin1(voc_bytes, len_voc);

    // Build encoding map: vocabulary index -> character (with/without finality marker)
    // IMPORTANT: We map CHARACTER INDICES, not byte positions in the UTF-8 string!
    // This matches Python's: {i: char for i, char in enumerate(vocabulary)}
    for (size_t i = 0; i < voc_string_latin1.length(); ++i) {
        std::string c = voc_string_latin1.substr(i, 1);
        m_encoding[i] = c;              // Normal character
        m_encoding[i | 0x80] = c + "|"; // Character with finality marker
    }
}

DAWG_Dictionary::~DAWG_Dictionary() {}

bool DAWG_Dictionary::contains(const std::string& word) {
    FindNavigator nav(word);
    navigate(nav);
    return nav.is_found();
}

std::vector<std::vector<std::string>> DAWG_Dictionary::find_combinations(const std::string& word) {
    CompoundNavigator nav(this, word);
    navigate(nav);
    return nav.result();
}

void DAWG_Dictionary::navigate(Navigator& nav) {
    PackedNavigation(nav, this).go();
}

/**
 * Start navigation from the root node.
 */
void PackedNavigation::go() {
    if (m_nav.accepting()) {
        navigate_from_node(m_root_offset, "");
    }
}

/**
 * Navigate from a node by exploring its outgoing edges.
 *
 * This method handles the core node parsing logic:
 *
 * 1. Check cache: If we've parsed this node before, use cached edges
 * 2. Parse node structure from binary:
 *    a. Read number of edges from node header
 *    b. For each edge:
 *       - Read edge length byte
 *       - Decode character codes into prefix string using encoding map
 *       - Check finality of LAST character (critical!)
 *       - Read next node offset (if not final)
 *    c. Cache the parsed edges
 * 3. Traverse edges: For each edge, ask Navigator if we should explore it
 *
 * CRITICAL: Finality check must only examine the LAST byte of the prefix!
 * Checking other bytes causes incorrect offset calculations and crashes.
 * This is because intermediate characters may have the 0x80 bit set as
 * part of their vocabulary index, not as a finality marker.
 *
 * @param offset  Byte offset in m_b where this node begins
 * @param matched String matched so far (path from root to this node)
 */
void PackedNavigation::navigate_from_node(UINT32 offset, std::string matched) {
    // Check if we've already parsed this node (performance optimization)
    auto it = m_dawg->m_iter_cache.find(offset);

    if (it == m_dawg->m_iter_cache.end()) {
        // First time visiting this node - parse its structure
        std::map<std::string, UINT32> edges;
        const BYTE* b = m_b;
        UINT32 current_offset = offset;

        // Node header: lower 7 bits = number of outgoing edges
        BYTE num_edges = b[current_offset++] & 0x7F;

        // Parse each edge
        for (int i = 0; i < num_edges; ++i) {
            // Edge header: lower 7 bits = number of character codes in prefix
            BYTE len_byte = b[current_offset++] & 0x7F;

            // Decode the character codes into a prefix string
            std::string prefix = "";
            for (int j = 0; j < len_byte; ++j) {
                BYTE code = b[current_offset + j];
                auto it = m_dawg->m_encoding.find(code);
                if (it == m_dawg->m_encoding.end()) {
                    throw std::runtime_error("Invalid encoding in DAWG file");
                }
                prefix += it->second;
            }
            current_offset += len_byte;

            // Check finality: Does the LAST byte have the 0x80 bit set?
            // IMPORTANT: Only check the LAST byte! Checking other bytes breaks offset calculation.
            bool is_final = (b[current_offset - 1] & 0x80) != 0;

            // Read next node offset (only present if edge is not final)
            UINT32 nextnode = 0;
            if (!is_final) {
                nextnode = *(UINT32*)(b + current_offset);
                current_offset += 4;
            }

            edges[prefix] = nextnode;
        }

        // Cache the parsed edges for future visits to this node
        m_dawg->m_iter_cache[offset] = edges;
        it = m_dawg->m_iter_cache.find(offset);
    }

    // Traverse the edges, asking Navigator which ones to explore
    for (const auto& edge : it->second) {
        const std::string& prefix = edge.first;
        UINT32 nextnode = edge.second;

        // Ask Navigator: should we explore this edge?
        if (!prefix.empty() && m_nav.push_edge(prefix[0])) {
            navigate_from_edge(prefix, nextnode, matched);

            // Ask Navigator: should we continue to other edges?
            if (!m_nav.pop_edge()) {
                break;  // Short-circuit: stop exploring other edges from this node
            }
        }
    }
}

/**
 * Navigate along an edge, processing its prefix character by character.
 *
 * This method walks along a single edge from a node, character by character,
 * checking with the Navigator at each step and detecting word boundaries.
 *
 * The prefix may contain finality markers ('|') indicating points where
 * valid words end. For example, prefix "ing|s|" encodes two words:
 *   - "...ing" (word ends at first |)
 *   - "...ings" (word ends at second |)
 *
 * Algorithm:
 * 1. For each character in the prefix:
 *    a. If it's '|': signal a final word to Navigator, continue
 *    b. Otherwise: ask Navigator if it accepts this character
 *       - If rejected: stop traversing this edge
 *       - If accepted: add to matched string and continue
 *    c. Check if current position is a word boundary:
 *       - Look ahead: is next char '|'?
 *       - Look at node: if we're at end and nextnode is final or absent
 *    d. Signal match (final or non-final) to Navigator
 *
 * 2. After consuming the prefix:
 *    - If there's a next node and Navigator is still accepting: recurse
 *
 * @param prefix   Decoded edge prefix (may contain '|' finality markers)
 * @param nextnode Offset of the next node (0 if edge is terminal)
 * @param matched  String matched so far (path from root to edge start)
 */
void PackedNavigation::navigate_from_edge(const std::string& prefix, UINT32 nextnode, std::string matched) {
    size_t lenp = prefix.length();
    size_t j = 0;

    // Walk through the prefix character by character
    while (j < lenp && m_nav.accepting()) {
        char current_char = prefix[j];

        // Finality marker: signals a complete word at this position
        if (current_char == '|') {
             m_nav.accept(matched, true);  // Final=true: complete word
             j++;
             continue;
        }

        // Ask Navigator: do you accept this character?
        if (!m_nav.accepts(current_char)) {
            return;  // Navigator rejected this character, stop navigating this edge
        }

        // Accepted! Add character to our matched string
        matched += current_char;
        j++;

        // Determine if this position marks the end of a word
        bool final = false;
        if (j < lenp) {
            // Not at end of prefix - check if next char is finality marker
            if (prefix[j] == '|') {
                final = true;
            }
        } else {
            // At end of prefix - check if the edge/node is final
            // Final if: nextnode is 0 (terminal) or next node header has 0x80 bit
            if (nextnode == 0 || (m_b[nextnode] & 0x80)) {
                final = true;
            }
        }

        // Notify Navigator of the match (final or partial)
        m_nav.accept(matched, final);
    }

    // Handle any trailing finality marker
    if (j < lenp && prefix[j] == '|') {
         m_nav.accept(matched, true);
    } else if (j < lenp) {
        // Didn't consume entire prefix - Navigator stopped accepting
        return;
    }

    // Continue to next node if it exists and Navigator wants to continue
    if (nextnode != 0 && m_nav.accepting()) {
        navigate_from_node(nextnode, matched);
    }
}

// ============================================================================
// C-style API implementation
//
// These functions provide a C interface to the C++ DAWG implementation,
// allowing Python (via CFFI) and other C clients to use the dictionary.
// ============================================================================

/**
 * Load a DAWG dictionary from a memory-mapped file.
 *
 * @param pbMap Pointer to the beginning of the DAWG file in memory
 * @return Opaque handle to the DAWG dictionary, or NULL if loading fails
 *
 * @note The caller must ensure the memory mapping remains valid for the
 *       lifetime of the returned handle.
 */
DawgHandle dawg_load(const BYTE* pbMap) {
    try {
        return new DAWG_Dictionary(pbMap);
    } catch (...) {
        return nullptr;
    }
}

/**
 * Unload a DAWG dictionary and free its resources.
 *
 * @param handle Handle returned by dawg_load()
 *
 * @note Does NOT unmap the file - the caller is responsible for that.
 */
void dawg_unload(DawgHandle handle) {
    if (handle) {
        delete static_cast<DAWG_Dictionary*>(handle);
    }
}

/**
 * Check if a word exists in the DAWG dictionary.
 *
 * @param handle Handle returned by dawg_load()
 * @param word   Latin-1 encoded word to search for
 * @return true if word exists in dictionary, false otherwise
 */
bool dawg_contains(DawgHandle handle, const char* word) {
    if (!handle || !word) return false;
    std::string s_latin1(word);
    return static_cast<DAWG_Dictionary*>(handle)->contains(s_latin1);
}

/**
 * Append a Latin-1 string to a stream as UTF-8 with JSON escaping.
 *
 * Handles both UTF-8 conversion and JSON special character escaping.
 *
 * @param os Output stream to append to
 * @param latin1 Latin-1 encoded string to convert and append
 */
static void append_latin1_as_utf8_json(std::ostream& os, const std::string& latin1) {
    for (unsigned char c : latin1) {
        // JSON escaping for special characters
        if (c == '"' || c == '\\') {
            os << '\\' << c;
        } else if (c < 0x80) {
            // ASCII range: single byte
            os << c;
        } else {
            // Latin-1 extended range: two bytes in UTF-8
            os << static_cast<char>(0xC0 | (c >> 6));
            os << static_cast<char>(0x80 | (c & 0x3F));
        }
    }
}

/**
 * Serialize compound word combinations to JSON format with UTF-8 encoding.
 *
 * Converts a vector of word-part vectors into a JSON string:
 *   [["part1", "part2"], ["part1", "part2", "part3"]]
 *
 * Converts all Latin-1 strings to UTF-8 for JSON output, allowing
 * Python's json.loads() to consume the bytes directly without decoding.
 *
 * @param combinations Vector of word splits to serialize
 * @return Newly allocated JSON string (caller must free with dawg_free_string)
 */
char* serialize_combinations(const std::vector<std::vector<std::string>>& combinations) {
    std::stringstream ss;
    ss << "[";
    for (size_t i = 0; i < combinations.size(); ++i) {
        if (i > 0) ss << ",";
        ss << "[";
        for (size_t j = 0; j < combinations[i].size(); ++j) {
            if (j > 0) ss << ",";
            ss << "\"";
            append_latin1_as_utf8_json(ss, combinations[i][j]);
            ss << "\"";
        }
        ss << "]";
    }
    ss << "]";

    std::string s = ss.str();
    char* result = new char[s.length() + 1];
    std::strcpy(result, s.c_str());
    return result;
}

/**
 * Find all possible ways to split a word into valid dictionary parts.
 *
 * Used for compound word analysis: given an unknown word, attempts to
 * split it into known parts. For example, "efnahagsráðherra" might
 * split into ["efnahags", "ráðherra"].
 *
 * @param handle Handle returned by dawg_load()
 * @param word   Latin-1 encoded word to split
 * @return JSON string of combinations, or NULL if no splits found
 *         Caller must free the returned string with dawg_free_string()
 */
char* dawg_find_combinations(DawgHandle handle, const char* word) {
    if (!handle || !word) return nullptr;
    std::string s_latin1(word);
    auto combinations = static_cast<DAWG_Dictionary*>(handle)->find_combinations(s_latin1);
    if (combinations.empty()) {
        return nullptr;
    }
    return serialize_combinations(combinations);
}

/**
 * Free a string returned by dawg_find_combinations().
 *
 * @param str String to free (may be NULL)
 */
void dawg_free_string(char* str) {
    if (str) {
        delete[] str;
    }
}
