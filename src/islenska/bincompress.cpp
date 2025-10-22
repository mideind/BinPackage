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

   --------------------------------------------------------------------------

   This module provides C++ access to the compressed BÍN dictionary format.

   COMPRESSED DICTIONARY FORMAT:

   The binary file contains multiple sections accessed via offsets:

   [Header - 56 bytes]
     - Signature: 16 bytes (BIN_COMPRESSOR_VERSION)
     - Offsets: 10 × 4-byte uint32 values:
       * mappings_offset
       * forms_offset
       * lemmas_offset
       * templates_offset
       * meanings_offset
       * alphabet_offset
       * subcats_offset
       * ksnid_offset
       * begin_greynir_utg
       * max_bin_id

   [Forms Section]
     Trie structure for word form lookups (accessed via bin.cpp)

   [Mappings Section]
     Maps word forms to (bin_id, meaning_index, ksnid_index) tuples.
     Uses packed 32-bit format for space efficiency:
     - Type 0x60000000: Single 32-bit packed entry
     - Type 0x40000000: Same bin_id as previous entry
     - Type 0x00000000: Two 32-bit words

   [Lemmas Section]
     Indexed by bin_id. Each entry contains:
     - Flags/subcat bits (32-bit)
     - Lemma string (length-prefixed Latin-1)
     - Optional template reference (if flag 0x80000000 set)

   [Meanings Section]
     Indexed by meaning_index. Contains (ofl, beyging) strings.

   [KSNIDs Section]
     Indexed by ksnid_index. Contains KRISTINsnid strings.

   [Subcats Section]
     List of subcategory ('fl') strings.

*/

#include <string>
#include <vector>
#include <unordered_set>
#include <cstring>
#include <sstream>
#include <stdexcept>

#include "bincompress.h"

// Import the mapping() function from bin.cpp
extern "C" UINT mapping(const BYTE* pbMap, const BYTE* pbWordLatin);

// Constants from basics.py
static const int BIN_ID_BITS = 20;         // Line 74
static const UINT BIN_ID_MASK = 0xFFFFF;   // 2^20 - 1 = 1,048,575
static const int MEANING_BITS = 10;        // Line 78
static const UINT MEANING_MASK = 0x3FF;    // 2^10 - 1 = 1,023
static const int KSNID_BITS = 14;          // Line 82
static const UINT KSNID_MASK = 0x3FFF;     // 2^14 - 1 = 16,383
static const int SUBCAT_BITS = 8;          // Line 87 (for subcategory 'hluti')
static const int COMMON_KIX_0 = 0;         // Line 94
static const int COMMON_KIX_1 = 1;         // Line 95

/**
 * Structure to hold raw lookup results.
 * Corresponds to (bin_id, meaning_index, ksnid_index) tuples in Python.
 */
struct RawEntry {
    int bin_id;
    int meaning_index;
    int ksnid_index;
};

/**
 * Structure to hold a BÍN entry.
 * Corresponds to BinEntryTuple: (stofn, utg, ofl, fl, ordmynd, beyging)
 */
struct BinEntry {
    std::string stofn;      // Lemma
    int utg;                // BÍN id
    std::string ofl;        // Word category (kk, kvk, hk, so, lo, etc.)
    std::string fl;         // Subcategory
    std::string ordmynd;    // Word form
    std::string beyging;    // Inflection description
};

/**
 * Structure to hold a Ksnid entry.
 * Corresponds to Ksnid.from_parameters(ord, bin_id, ofl, hluti, form, mark, ksnid)
 */
struct KsnidEntry {
    std::string ord;        // Lemma (stofn)
    int bin_id;             // BÍN id
    std::string ofl;        // Word category
    std::string hluti;      // Subcategory (fl)
    std::string form;       // Word form
    std::string mark;       // Inflection marks (beyging)
    std::string ksnid;      // Ksnid string

    /**
     * Equality operator matching Python's Ksnid.__eq__()
     * Compares all fields: bmynd, mark, bin_id, ord, ofl, hluti, ksnid_string
     */
    bool operator==(const KsnidEntry& other) const {
        return form == other.form       // bmynd
            && mark == other.mark
            && bin_id == other.bin_id
            && ord == other.ord
            && ofl == other.ofl
            && hluti == other.hluti
            && ksnid == other.ksnid;    // ksnid_string
    }
};

/**
 * Hash function for KsnidEntry, matching Python's Ksnid.__hash__()
 * Hashes only the "primary key" fields: (bin_id, ofl, bmynd, mark)
 */
struct KsnidEntryHash {
    std::size_t operator()(const KsnidEntry& entry) const {
        // Combine hashes using the same approach as Python's tuple hash
        std::size_t h1 = std::hash<int>()(entry.bin_id);
        std::size_t h2 = std::hash<std::string>()(entry.ofl);
        std::size_t h3 = std::hash<std::string>()(entry.form);  // bmynd
        std::size_t h4 = std::hash<std::string>()(entry.mark);

        // Simple hash combination (similar to boost::hash_combine)
        std::size_t seed = 0;
        seed ^= h1 + 0x9e3779b9 + (seed << 6) + (seed >> 2);
        seed ^= h2 + 0x9e3779b9 + (seed << 6) + (seed >> 2);
        seed ^= h3 + 0x9e3779b9 + (seed << 6) + (seed >> 2);
        seed ^= h4 + 0x9e3779b9 + (seed << 6) + (seed >> 2);
        return seed;
    }
};

/**
 * Main BinCompressed class.
 *
 * Wraps a memory-mapped compressed BÍN dictionary file and provides
 * efficient lookup operations.
 */
class BinCompressed {
private:
    const BYTE* m_pbMap;              // Pointer to memory-mapped file
    UINT m_forms_offset;              // Offset to forms trie
    const BYTE* m_mappings;           // Pointer to mappings section
    const BYTE* m_lemmas;             // Pointer to lemmas section
    const BYTE* m_templates;          // Pointer to templates section
    const BYTE* m_meanings;           // Pointer to meanings section
    const BYTE* m_ksnid_strings;      // Pointer to ksnid section
    std::vector<std::string> m_subcats;  // Subcategory strings
    UINT m_begin_greynir_utg;         // First Greynir addition ID
    UINT m_max_bin_id;                // Maximum BÍN ID

    /**
     * Read a 32-bit little-endian unsigned integer at offset.
     */
    inline UINT read_uint32(UINT offset) const {
        return (m_pbMap[offset + 0] <<  0) |
               (m_pbMap[offset + 1] <<  8) |
               (m_pbMap[offset + 2] << 16) |
               (m_pbMap[offset + 3] << 24);
    }

    /**
     * Read a 32-bit little-endian unsigned integer from a byte pointer.
     */
    inline UINT read_uint32(const BYTE* p) const {
        return (p[0] <<  0) |
               (p[1] <<  8) |
               (p[2] << 16) |
               (p[3] << 24);
    }

public:
    /**
     * Initialize BinCompressed from a memory-mapped file.
     *
     * @param pbMap Pointer to the memory-mapped compressed dictionary
     * @throws std::runtime_error if file signature is invalid
     */
    BinCompressed(const BYTE* pbMap);
    ~BinCompressed();

    /**
     * Get the beginning Greynir utg number.
     */
    UINT begin_greynir_utg() const { return m_begin_greynir_utg; }

    /**
     * Decode a meaning entry.
     *
     * @param ix Meaning index
     * @return Pair of (ofl, beyging) strings
     */
    std::pair<std::string, std::string> meaning(int ix) const;

    /**
     * Decode a KRISTINsnid string.
     *
     * @param ix KSnid index
     * @return KSnid string
     */
    std::string ksnid_string(int ix) const;

    /**
     * Decode a lemma entry.
     *
     * @param bin_id BÍN ID number
     * @return Pair of (stofn, fl) strings
     */
    std::pair<std::string, std::string> lemma(int bin_id) const;

    /**
     * Get all word forms associated with a lemma.
     *
     * Returns all inflected forms of the lemma identified by bin_id,
     * decompressed from the templates section. The result includes
     * the base lemma form as well as all inflected variants.
     *
     * @param bin_id BÍN ID number
     * @return Vector of Latin-1 encoded word forms (as strings)
     */
    std::vector<std::string> lemma_forms(int bin_id) const;

    /**
     * Perform raw lookup of a word form.
     *
     * Returns all (bin_id, meaning_index, ksnid_index) tuples for the word.
     *
     * @param word Latin-1 encoded word to lookup
     * @return Vector of raw entries
     */
    std::vector<RawEntry> raw_lookup(const char* word) const;

    /**
     * Check if a word exists in the dictionary.
     *
     * @param word Latin-1 encoded word
     * @return true if word exists, false otherwise
     */
    bool contains(const char* word) const;

    /**
     * Lookup a word and return all matching BÍN entries.
     *
     * @param word Latin-1 encoded word to lookup
     * @param cat Optional word category filter (NULL for no filter)
     * @param lemma Optional lemma filter (NULL for no filter)
     * @param utg Optional BÍN ID filter (-1 for no filter)
     * @return Vector of BinEntry structures
     */
    std::vector<BinEntry> lookup(
        const char* word,
        const char* cat = nullptr,
        const char* lemma = nullptr,
        int utg = -1
    ) const;

    /**
     * Lookup a word and return all matching Ksnid entries.
     *
     * @param word Latin-1 encoded word to lookup
     * @param cat Optional word category filter (NULL for no filter)
     * @param lemma Optional lemma filter (NULL for no filter)
     * @param utg Optional BÍN ID filter (-1 for no filter)
     * @return Vector of KsnidEntry structures
     */
    std::vector<KsnidEntry> lookup_ksnid(
        const char* word,
        const char* cat = nullptr,
        const char* lemma = nullptr,
        int utg = -1
    ) const;

    /**
     * Get all Ksnid entries for a given BÍN ID.
     *
     * Returns all word forms of the lemma identified by bin_id,
     * with their full Ksnid information.
     *
     * @param bin_id BÍN ID number
     * @return Vector of KsnidEntry structures
     */
    std::vector<KsnidEntry> lookup_id(int bin_id) const;
};

// ============================================================================
// Implementation
// ============================================================================

BinCompressed::BinCompressed(const BYTE* pbMap) : m_pbMap(pbMap) {
    // Expected signature (from basics.py BIN_COMPRESSOR_VERSION)
    const char* expected_sig = "Greynir 04.00.00";
    if (memcmp(m_pbMap, expected_sig, 16) != 0) {
        throw std::runtime_error("Invalid compressed dictionary signature");
    }

    // Read header (10 uint32 values at offset 16)
    UINT mappings_offset = read_uint32(16);
    m_forms_offset = read_uint32(20);
    UINT lemmas_offset = read_uint32(24);
    UINT templates_offset = read_uint32(28);
    UINT meanings_offset = read_uint32(32);
    // UINT alphabet_offset = read_uint32(36);  // Not currently used
    UINT subcats_offset = read_uint32(40);
    UINT ksnid_offset = read_uint32(44);
    m_begin_greynir_utg = read_uint32(48);
    m_max_bin_id = read_uint32(52);

    // Set section pointers
    m_mappings = m_pbMap + mappings_offset;
    m_lemmas = m_pbMap + lemmas_offset;
    m_templates = m_pbMap + templates_offset;
    m_meanings = m_pbMap + meanings_offset;
    m_ksnid_strings = m_pbMap + ksnid_offset;

    // Read subcategories
    UINT subcats_length = read_uint32(subcats_offset);
    const BYTE* subcats_bytes = m_pbMap + subcats_offset + 4;

    // Split on whitespace (space-separated Latin-1 strings)
    std::string subcats_str(reinterpret_cast<const char*>(subcats_bytes), subcats_length);
    std::istringstream iss(subcats_str);
    std::string subcat;
    while (iss >> subcat) {
        m_subcats.push_back(subcat);
    }
}

BinCompressed::~BinCompressed() {
    // Nothing to do - we don't own the memory map
}

std::pair<std::string, std::string> BinCompressed::meaning(int ix) const {
    // Read offset to meaning string
    if (ix < 0) {
        throw std::runtime_error("Invalid meaning index");
    }
    UINT off = read_uint32(m_meanings + ix * 4);

    // Read up to 24 bytes of Latin-1 data
    const BYTE* p = m_pbMap + off;
    char buffer[25];
    memcpy(buffer, p, 24);
    buffer[24] = '\0';

    // Parse "ofl beyging ..." (space-separated)
    std::string s(buffer);
    size_t first_space = s.find(' ');
    if (first_space == std::string::npos) {
        throw std::runtime_error("Invalid meaning format");
    }
    size_t second_space = s.find(' ', first_space + 1);
    std::string ofl = s.substr(0, first_space);
    std::string beyging;
    if (second_space != std::string::npos) {
        beyging = s.substr(first_space + 1, second_space - first_space - 1);
    } else {
        beyging = s.substr(first_space + 1);
    }

    return std::make_pair(ofl, beyging);
}

std::string BinCompressed::ksnid_string(int ix) const {
    if (ix < 0) {
        throw std::runtime_error("Invalid Ksnid index");
    }
    // Read offset to ksnid string
    UINT off = read_uint32(m_ksnid_strings + ix * 4);

    // First byte is length
    UINT len = m_pbMap[off];

    // Read Latin-1 string
    return std::string(reinterpret_cast<const char*>(m_pbMap + off + 1), len);
}

std::pair<std::string, std::string> BinCompressed::lemma(int bin_id) const {
    if (bin_id < 0 || (UINT)bin_id > m_max_bin_id) {
        throw std::runtime_error("Invalid BÍN ID");
    }
    // Read offset to lemma entry
    UINT off = read_uint32(m_lemmas + bin_id * 4);
    if (off == 0) {
        // Return empty strings instead of throwing - some lookups return bin_id 0
        return std::make_pair("", "");
    }

    // Read flags/bits
    UINT bits = read_uint32(off) & 0x7FFFFFFF;

    // Extract subcategory index (lower SUBCAT_BITS)
    size_t cix = bits & ((1 << SUBCAT_BITS) - 1);

    // Read lemma string (length-prefixed)
    UINT p = off + 4;
    UINT lw = m_pbMap[p];  // Length byte
    p += 1;

    std::string stofn(reinterpret_cast<const char*>(m_pbMap + p), lw);
    std::string fl = (cix < m_subcats.size()) ? m_subcats[cix] : "";

    return std::make_pair(stofn, fl);
}

std::vector<std::string> BinCompressed::lemma_forms(int bin_id) const {
    // Sanity check on the BÍN id
    if (bin_id < 0 || (UINT)bin_id > m_max_bin_id) {
        return std::vector<std::string>();
    }

    // Read offset to lemma entry
    UINT off = read_uint32(m_lemmas + bin_id * 4);
    if (off == 0) {
        // No entry with this BÍN id
        return std::vector<std::string>();
    }

    // Read flags/bits
    UINT bits = read_uint32(off);

    // Skip past the flags to read the lemma string (length-prefixed)
    UINT p = off + 4;
    UINT lw = m_pbMap[p];  // Length byte

    // Extract the base lemma (at p+1)
    std::string lemma(reinterpret_cast<const char*>(m_pbMap + p + 1), lw);

    // Check if templates are attached (bit 0x80000000)
    if ((bits & 0x80000000) == 0) {
        // No templates associated with this lemma
        return std::vector<std::string>{lemma};
    }

    // Skip past the lemma to get to the template pointer
    // The lemma is 4-byte aligned: length byte (1) + string (lw) + padding
    lw += 1;  // Include the length byte
    if (lw & 3) {
        lw += 4 - (lw & 3);  // Round up to next multiple of 4
    }
    p += lw;  // Now p points to template offset

    // Read the template set offset
    UINT template_offset = read_uint32(p);

    // Decompress the template set using differential encoding
    std::vector<std::string> result;
    std::string last_w = lemma;
    size_t last_len = lemma.length();
    p = template_offset;

    while (true) {
        // Read the cut byte
        BYTE cut_byte = m_templates[p];
        p += 1;

        if (cut_byte == 0x00) {
            // End of template set
            break;
        }

        size_t cut;
        size_t new_len;

        if (cut_byte & 0x80) {
            // Long form: cut is in lower 7 bits, length in next byte
            cut = cut_byte & 0x7F;
            new_len = m_templates[p];
            p += 1;
        } else {
            // Short form: cut in upper bits, length difference in lower bits
            // Note: The expression below is a bit opaque. It extracts a signed
            // integer from a 3-bit signed representation. The 0x04 bit is
            // the sign bit, and the lower (0x01 and 0x02) bits are the magnitude.
            // 100 (0 minus 4) thus becomes -4, 101 (1 minus 4) becomes -3,
            // 011 (3 minus 0) becomes +3, etc.
            int diff = static_cast<int>(cut_byte & 0x03) - static_cast<int>(cut_byte & 0x04);
            cut = cut_byte >> 3;
            // diff can be negative, so we need to handle the sign carefully
            int new_len_signed = static_cast<int>(cut) + diff;
            if (new_len_signed < 0 || new_len_signed > 255) {
                // Invalid new_len - would wrap around or be too large
                return std::vector<std::string>();
            }
            new_len = static_cast<size_t>(new_len_signed);
        }

        // Calculate the common prefix length
        if (cut > last_len) {
            // Invalid data - cut is larger than previous word length
            return std::vector<std::string>();
        }
        size_t common = last_len - cut;

        // Assemble the new word: common prefix + divergent part
        std::string w = last_w.substr(0, common) +
            std::string(reinterpret_cast<const char*>(m_templates + p), new_len);
        p += new_len;

        // Add to results
        result.push_back(w);

        // Update for next iteration
        last_w = w;
        last_len = common + new_len;
    }

    // Append the base lemma itself
    result.push_back(lemma);

    return result;
}

std::vector<RawEntry> BinCompressed::raw_lookup(const char* word) const {
    // Call the C++ mapping() function from bin.cpp to find the word in the trie
    UINT map_offset = mapping(m_pbMap, reinterpret_cast<const BYTE*>(word));

    if (map_offset == 0xFFFFFFFF) {
        // Word not found
        return std::vector<RawEntry>();
    }

    // Decode the mappings
    std::vector<RawEntry> result;
    int bin_id = -1;

    while (true) {
        UINT w0 = read_uint32(m_mappings + map_offset * 4);
        map_offset += 1;

        int meaning_index;
        int ksnid_index;

        if ((w0 & 0x60000000) == 0x60000000) {
            // Single 32-bit packed entry
            meaning_index = ((w0 >> BIN_ID_BITS) & 0xFF) - 1;  // 8 bits for freq_ix
            bin_id = w0 & BIN_ID_MASK;
            ksnid_index = (w0 & 0x10000000) ? COMMON_KIX_1 : COMMON_KIX_0;
        }
        else if ((w0 & 0x60000000) == 0x40000000) {
            // Same bin_id as previous entry
            meaning_index = (w0 >> KSNID_BITS) & MEANING_MASK;
            ksnid_index = w0 & KSNID_MASK;
        }
        else {
            // Two 32-bit words
            bin_id = w0 & BIN_ID_MASK;
            UINT w1 = read_uint32(m_mappings + map_offset * 4);
            map_offset += 1;
            meaning_index = (w1 >> KSNID_BITS) & MEANING_MASK;
            ksnid_index = w1 & KSNID_MASK;
        }

        RawEntry entry;
        entry.bin_id = bin_id;
        entry.meaning_index = meaning_index;
        entry.ksnid_index = ksnid_index;
        result.push_back(entry);

        if (w0 & 0x80000000) {
            // Last mapping indicator
            break;
        }
    }

    return result;
}

bool BinCompressed::contains(const char* word) const {
    UINT map_offset = mapping(m_pbMap, reinterpret_cast<const BYTE*>(word));
    return map_offset != 0xFFFFFFFF;
}

std::vector<BinEntry> BinCompressed::lookup(
    const char* word,
    const char* cat,
    const char* lemma_filter,
    int utg
) const {
    std::vector<BinEntry> result;
    bool cat_is_no = (cat != nullptr && strcmp(cat, "no") == 0);

    // Get raw entries
    std::vector<RawEntry> raw_entries = raw_lookup(word);

    for (const auto& raw : raw_entries) {
        // Apply utg filter
        if (utg != -1 && raw.bin_id != utg) {
            continue;
        }

        // Get meaning
        std::pair<std::string, std::string> meaning_pair = meaning(raw.meaning_index);
        std::string ofl = meaning_pair.first;
        std::string beyging = meaning_pair.second;

        // Apply category filter
        if (cat != nullptr) {
            // Special case: "no" matches any gender (kk, kvk, hk)
            if (cat_is_no) {
                if (ofl != "kk" && ofl != "kvk" && ofl != "hk") {
                    continue;
                }
            } else if (ofl != cat) {
                continue;
            }
        }

        // Get lemma
        std::pair<std::string, std::string> lemma_pair = lemma(raw.bin_id);
        std::string stofn = lemma_pair.first;
        std::string fl = lemma_pair.second;

        // Apply lemma filter
        if (lemma_filter != nullptr && stofn != lemma_filter) {
            continue;
        }

        // Create entry
        BinEntry entry;
        entry.stofn = stofn;
        entry.utg = raw.bin_id;
        entry.ofl = ofl;
        entry.fl = fl;
        entry.ordmynd = word;
        entry.beyging = beyging;
        result.push_back(entry);
    }

    return result;
}

std::vector<KsnidEntry> BinCompressed::lookup_ksnid(
    const char* word,
    const char* cat,
    const char* lemma_filter,
    int utg
) const {
    std::vector<KsnidEntry> result;
    bool cat_is_no = (cat != nullptr && strcmp(cat, "no") == 0);

    // Get raw entries
    std::vector<RawEntry> raw_entries = raw_lookup(word);

    for (const auto& raw : raw_entries) {
        // Apply utg filter
        if (utg != -1 && raw.bin_id != utg) {
            continue;
        }

        // Get meaning
        std::pair<std::string, std::string> meaning_pair = meaning(raw.meaning_index);
        std::string ofl = meaning_pair.first;
        std::string beyging = meaning_pair.second;

        // Apply category filter
        if (cat != nullptr) {
            // Special case: "no" matches any gender (kk, kvk, hk)
            if (cat_is_no) {
                if (ofl != "kk" && ofl != "kvk" && ofl != "hk") {
                    continue;
                }
            } else if (ofl != cat) {
                continue;
            }
        }

        // Get lemma
        std::pair<std::string, std::string> lemma_pair = lemma(raw.bin_id);
        std::string stofn = lemma_pair.first;
        std::string fl = lemma_pair.second;

        // Apply lemma filter
        if (lemma_filter != nullptr && stofn != lemma_filter) {
            continue;
        }

        // Get ksnid string
        std::string ksnid_str = ksnid_string(raw.ksnid_index);

        // Create entry
        KsnidEntry entry;
        entry.ord = stofn;
        entry.bin_id = raw.bin_id;
        entry.ofl = ofl;
        entry.hluti = fl;
        entry.form = word;
        entry.mark = beyging;
        entry.ksnid = ksnid_str;
        result.push_back(entry);
    }

    return result;
}

std::vector<KsnidEntry> BinCompressed::lookup_id(int bin_id) const {
    // Get all word forms for this lemma
    std::vector<std::string> forms = lemma_forms(bin_id);
    if (forms.empty()) {
        return std::vector<KsnidEntry>();
    }

    // Get the lemma (stofn, fl) once
    std::pair<std::string, std::string> lemma_pair = lemma(bin_id);
    std::string stofn = lemma_pair.first;
    std::string fl = lemma_pair.second;

    // Use an unordered_set for O(1) duplicate detection (same as Python's set)
    std::unordered_set<KsnidEntry, KsnidEntryHash> unique_entries;

    // For each word form, do a raw lookup
    for (const auto& form : forms) {
        std::vector<RawEntry> raw_entries = raw_lookup(form.c_str());

        for (const auto& raw : raw_entries) {
            // Filter to only this bin_id
            if (raw.bin_id != bin_id) {
                continue;
            }

            // Get meaning
            std::pair<std::string, std::string> meaning_pair = meaning(raw.meaning_index);
            std::string ofl = meaning_pair.first;
            std::string beyging = meaning_pair.second;

            // Get ksnid string
            std::string ksnid_str = ksnid_string(raw.ksnid_index);

            // Create entry
            KsnidEntry entry;
            entry.ord = stofn;
            entry.bin_id = bin_id;
            entry.ofl = ofl;
            entry.hluti = fl;
            entry.form = form;
            entry.mark = beyging;
            entry.ksnid = ksnid_str;

            // Insert into set (automatically handles duplicates)
            unique_entries.insert(entry);
        }
    }

    // Convert set to vector for return
    return std::vector<KsnidEntry>(unique_entries.begin(), unique_entries.end());
}

// ============================================================================
// C API implementation
// ============================================================================

BcHandle bin_compressed_init(const BYTE* pbMap) {
    try {
        return new BinCompressed(pbMap);
    } catch (...) {
        return nullptr;
    }
}

void bin_compressed_close(BcHandle handle) {
    if (handle) {
        delete static_cast<BinCompressed*>(handle);
    }
}

bool bin_compressed_contains(BcHandle handle, const char* word) {
    if (!handle || !word) return false;
    return static_cast<BinCompressed*>(handle)->contains(word);
}

/**
 * Append a Latin-1 encoded string to an output stream as UTF-8.
 *
 * This is more efficient than creating a temporary string when the result
 * will be immediately appended to a stream. Latin-1 (ISO-8859-1) maps
 * directly to Unicode code points 0x00-0xFF. For UTF-8 encoding:
 * - 0x00-0x7F: Single byte (ASCII)
 * - 0x80-0xFF: Two bytes (0xC2-0xC3 followed by 0x80-0xBF)
 *
 * @param os Output stream to append to
 * @param latin1 Latin-1 encoded string to convert and append
 */
static void append_latin1_as_utf8(std::ostream& os, const std::string& latin1) {
    for (unsigned char c : latin1) {
        if (c < 0x80) {
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
 * Serialize BinEntry results to JSON format with UTF-8 encoding.
 *
 * Converts all Latin-1 strings to UTF-8 for JSON output, allowing
 * Python's json.loads() to consume the bytes directly without decoding.
 */
static char* serialize_entries(const std::vector<BinEntry>& entries) {
    std::stringstream ss;
    ss << "[";
    for (size_t i = 0; i < entries.size(); ++i) {
        if (i > 0) ss << ",";
        ss << "{\"stofn\":\"";
        append_latin1_as_utf8(ss, entries[i].stofn);
        ss << "\",\"utg\":" << entries[i].utg << ",\"ofl\":\"";
        append_latin1_as_utf8(ss, entries[i].ofl);
        ss << "\",\"fl\":\"";
        append_latin1_as_utf8(ss, entries[i].fl);
        ss << "\",\"ordmynd\":\"";
        append_latin1_as_utf8(ss, entries[i].ordmynd);
        ss << "\",\"beyging\":\"";
        append_latin1_as_utf8(ss, entries[i].beyging);
        ss << "\"}";
    }
    ss << "]";

    std::string s = ss.str();
    char* result = new char[s.length() + 1];
    std::strcpy(result, s.c_str());
    return result;
}

static char* serialize_ksnid_entries(const std::vector<KsnidEntry>& entries) {
    std::stringstream ss;
    ss << "[";
    for (size_t i = 0; i < entries.size(); ++i) {
        if (i > 0) ss << ",";
        ss << "{\"ord\":\"";
        append_latin1_as_utf8(ss, entries[i].ord);
        ss << "\",\"bin_id\":" << entries[i].bin_id << ",\"ofl\":\"";
        append_latin1_as_utf8(ss, entries[i].ofl);
        ss << "\",\"hluti\":\"";
        append_latin1_as_utf8(ss, entries[i].hluti);
        ss << "\",\"form\":\"";
        append_latin1_as_utf8(ss, entries[i].form);
        ss << "\",\"mark\":\"";
        append_latin1_as_utf8(ss, entries[i].mark);
        ss << "\",\"ksnid\":\"";
        append_latin1_as_utf8(ss, entries[i].ksnid);
        ss << "\"}";
    }
    ss << "]";

    std::string s = ss.str();
    char* result = new char[s.length() + 1];
    std::strcpy(result, s.c_str());
    return result;
}

static char* serialize_lemma_forms(const std::vector<std::string>& forms) {
    std::stringstream ss;
    ss << "[";
    for (size_t i = 0; i < forms.size(); ++i) {
        if (i > 0) ss << ",";
        ss << "\"";
        append_latin1_as_utf8(ss, forms[i]);
        ss << "\"";
    }
    ss << "]";

    std::string s = ss.str();
    char* result = new char[s.length() + 1];
    std::strcpy(result, s.c_str());
    return result;
}

char* bin_compressed_lookup(
    BcHandle handle,
    const char* word,
    const char* cat,
    const char* lemma,
    int utg
) {
    if (!handle || !word) return nullptr;

    auto entries = static_cast<BinCompressed*>(handle)->lookup(word, cat, lemma, utg);
    if (entries.empty()) {
        return nullptr;
    }

    return serialize_entries(entries);
}

char* bin_compressed_lookup_ksnid(
    BcHandle handle,
    const char* word,
    const char* cat,
    const char* lemma,
    int utg
) {
    if (!handle || !word) return nullptr;

    auto entries = static_cast<BinCompressed*>(handle)->lookup_ksnid(word, cat, lemma, utg);
    if (entries.empty()) {
        return nullptr;
    }

    return serialize_ksnid_entries(entries);
}

char* bin_compressed_lemma_forms(BcHandle handle, int bin_id) {
    if (!handle) {
        return nullptr;
    }

    auto forms = static_cast<BinCompressed*>(handle)->lemma_forms(bin_id);

    if (forms.empty()) {
        return nullptr;
    }

    return serialize_lemma_forms(forms);
}

char* bin_compressed_lookup_id(BcHandle handle, int bin_id) {
    if (!handle) {
        return nullptr;
    }

    auto entries = static_cast<BinCompressed*>(handle)->lookup_id(bin_id);

    if (entries.empty()) {
        return nullptr;
    }

    return serialize_ksnid_entries(entries);
}

void bin_compressed_free_string(char* str) {
    if (str) {
        delete[] str;
    }
}
