/*

   BinPackage

   libbin: the compressed BÍN dictionary

   Copyright © 2026 Miðeind ehf.
   Original author: Vilhjálmur Þorsteinsson

   This software is licensed under the MIT License; see bin.h.

   Dict wraps a memory-mapped compressed.bin (see tools/binpack.py for the
   format) and, optionally, the three compounder DAWGs. It decodes the
   mappings, lemma, meaning and ksnid sections, and implements the compact
   build's transparent restoration of dropped compounds.

   A Dict is immutable after construction and safe to share between threads.

*/

#ifndef LIBBIN_DICT_H
#define LIBBIN_DICT_H

#include <stddef.h>
#include <stdint.h>

#include <string>
#include <vector>

#include "dawg.h"

namespace libbin {

// A raw entry, as stored in the mappings section
struct RawEntry {
    uint32_t bin_id;
    uint32_t meaning_index;
    uint32_t ksnid_index;
};

// A decoded lemma record
struct LemmaRecord {
    std::string lemma;
    uint32_t subcat_index = 0;
    bool has_template = false;
    bool dropped = false;
    uint32_t template_offset = 0;
    // Dropped lemmas of a compact build only:
    uint32_t ksnid_index = 0;
    std::vector<uint32_t> heads;
};

// A fully decoded entry
struct Entry {
    std::string ord;
    uint32_t bin_id;
    std::string ofl;
    std::string hluti;
    std::string bmynd;
    std::string mark;
    std::string ksnid;
};

class Dict {
   public:
    // Throws std::runtime_error if the map is not a compressed.bin of the
    // expected version. The DAWGs may be null.
    Dict(const uint8_t* map, size_t len, const Dawg* all, const Dawg* prefixes, const Dawg* suffixes);

    bool is_compact() const { return m_compact_offset != 0; }
    bool has_dawgs() const { return m_all && m_prefixes && m_suffixes; }
    uint32_t begin_greynir_utg() const { return m_begin_greynir_utg; }
    uint32_t max_bin_id() const { return m_max_bin_id; }

    // Decoding of the tables
    bool lemma(uint32_t bin_id, LemmaRecord& out) const;
    void meaning(uint32_t ix, std::string& ofl, std::string& mark) const;
    std::string ksnid_string(uint32_t ix) const;
    const std::string& subcat(uint32_t ix) const { return m_subcats[ix < m_subcats.size() ? ix : 0]; }

    // Word-form trie only
    bool trie_contains(const std::string& word) const;
    void trie_lookup(const std::string& word, std::vector<RawEntry>& out) const;

    // Lookups with compact restoration
    bool contains(const std::string& word) const;
    void raw_lookup(const std::string& word, std::vector<RawEntry>& out) const;
    void lookup(const std::string& word, const char* cat, const char* lemma_filter,
                uint32_t bin_id_filter, std::vector<Entry>& out) const;
    void lookup_id(uint32_t bin_id, std::vector<Entry>& out) const;
    std::vector<std::string> lemma_forms(uint32_t bin_id) const;

    // The legal compound splits of the word in ranking order (see bin.h)
    std::vector<std::vector<std::string>> compound_candidates(const std::string& word) const;
    // The split the compounder settles on, or empty (see bin.h)
    std::vector<std::string> compound_split(const std::string& word) const;
    // Interpret a word as a compound (see bin.h). Returns the word that
    // was split (the query or its lowercase form) in split_word.
    void compound_lookup(const std::string& word, bool insert_hyphen, bool nouns_only, bool try_lowercase,
                         std::vector<Entry>& out, std::string& split_word) const;

    // The standard entry filter of the Bin class: Greynir additions are
    // left out unless they are suffix-only entries ('S'), which are
    // included iff compound is true
    bool standard_filter(const RawEntry& raw, bool compound) const;
    // Latin-1 lowercase
    static std::string lower(const std::string& s);

   private:
    const uint8_t* m_map;
    size_t m_len;
    const uint8_t* m_mappings;
    const uint8_t* m_lemmas;
    const uint8_t* m_templates;
    const uint8_t* m_meanings;
    const uint8_t* m_ksnid;
    uint32_t m_begin_greynir_utg;
    uint32_t m_max_bin_id;
    uint32_t m_compact_offset;
    // Compact section: bin_ids of the dropped lemmas, sorted by lemma
    const uint8_t* m_compact_ids;
    uint32_t m_compact_count;
    std::vector<std::string> m_subcats;
    const Dawg* m_all;
    const Dawg* m_prefixes;
    const Dawg* m_suffixes;

    uint32_t at(uint32_t offset) const;
    uint32_t at(const uint8_t* p) const;
    // Offset of the lemma record, or 0
    uint32_t lemma_offset(uint32_t bin_id) const;
    // The lemma string of a record at the given offset
    void lemma_string(uint32_t offset, std::string& out) const;
    // Decode the mappings starting at the given index
    void decode_mappings(uint32_t index, std::vector<RawEntry>& out) const;
    // The forms of a lemma from its template
    std::vector<std::string> template_forms(const LemmaRecord& rec) const;
    // Compact build: restore the readings of a dropped compound
    void compact_lookup(const std::string& word, std::vector<RawEntry>& out) const;
    // Compact build: the dropped lemmas with the given lemma string
    void compact_find(const std::string& lemma, std::vector<uint32_t>& out) const;
    // Build an entry from a raw one
    void make_entry(const RawEntry& raw, const std::string& form, Entry& out) const;
    // The 'birting' field of a ksnid string
    char birting(uint32_t ksnid_index) const;
    // Is every noun reading of the surface form a defective paradigm?
    bool defective_head(const std::string& surface) const;
};

}  // namespace libbin

#endif  // LIBBIN_DICT_H
