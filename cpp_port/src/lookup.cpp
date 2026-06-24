/*
   BinPackage C++ Port

   Lookup method implementations

   Copyright © 2024 Miðeind ehf.
   
   This software is licensed under the MIT License.
*/

#include "islenska_impl.h"
#include <algorithm>
#include <cctype>
#include <sstream>
#include <iostream>

namespace islenska {

// Constants for packed entry format
constexpr uint32_t BIN_ID_BITS = 20;
constexpr uint32_t BIN_ID_MASK = (1 << BIN_ID_BITS) - 1;
constexpr uint32_t MEANING_BITS = 11;
constexpr uint32_t MEANING_MASK = (1 << MEANING_BITS) - 1;
constexpr uint32_t KSNID_BITS = 19;
constexpr uint32_t KSNID_MASK = (1 << KSNID_BITS) - 1;

// Decode a meaning from the meanings section
std::pair<std::string, std::string> BinImpl::decode_meaning_data(uint32_t meaning_index) const {
    // Read offset from meanings table (meanings_offset + ix * 4)
    uint32_t off = read_uint32(header_->meanings_offset + meaning_index * 4);
    
    // Read 24 bytes from that offset in the main data
    std::string data;
    for (int i = 0; i < 24; i++) {
        uint8_t ch = read_uint8(off + i);
        data += static_cast<char>(ch);
    }
    
    // The Python code uses latin-1 decoding and splits by maxsplit=2
    // Find first space
    size_t first_space = data.find(' ');
    if (first_space == std::string::npos) {
        return {data, ""};
    }
    
    std::string ofl = data.substr(0, first_space);
    
    // Find start of second word (skip spaces)
    size_t mark_start = data.find_first_not_of(' ', first_space);
    if (mark_start == std::string::npos) {
        return {ofl, ""};
    }
    
    // Find end of second word (next space or end)
    size_t mark_end = data.find(' ', mark_start);
    if (mark_end == std::string::npos) {
        mark_end = data.length();
    }
    
    // Trim any trailing spaces from mark
    std::string mark = data.substr(mark_start, mark_end - mark_start);
    
    return {ofl, mark};
}

// Decode lemma data
std::pair<std::string, std::string> BinImpl::decode_lemma_data(int32_t bin_id) const {
    uint32_t off = read_uint32(header_->lemmas_offset + bin_id * 4);
    if (off == 0) {
        return {"", ""};
    }
    
    uint32_t bits = read_uint32(off) & 0x7FFFFFFF;
    uint32_t subcat_idx = bits & 0x1F;  // 5 bits for subcategory
    
    // Read lemma string
    off += 4;
    uint8_t len = read_uint8(off);
    off += 1;
    
    std::string lemma;
    for (uint8_t i = 0; i < len; i++) {
        lemma += static_cast<char>(read_uint8(off + i));
    }
    
    // Get subcategory
    std::string subcat = "alm";  // default
    if (subcat_idx > 0 && subcat_idx < 32) {
        const char* subcats[] = {
            "alm", "föð", "móð", "fyr", "ism", "gæl", "lönd", "örn", "erl",
            "tölv", "málfr", "tón", "íþr", "natt", "mat", "dýr", "gras",
            "efna", "föt", "mælieining", "bíl", "tími", "fjár", "bygg",
            "veð", "við", "líff", "bær", "heimilisfang", "lækn", "bibl", "entity"
        };
        if (subcat_idx < sizeof(subcats)/sizeof(subcats[0])) {
            subcat = subcats[subcat_idx];
        }
    }
    
    return {from_latin1(lemma), subcat};
}

// Decode a BinEntry from binary format
BinEntry BinImpl::decode_meaning(uint32_t packed_entry, int32_t& bin_id) const {
    // Extract fields from packed entry
    uint32_t meaning_index = 0;
    
    if ((packed_entry & 0x60000000) == 0x60000000) {
        // Single 32-bit packed entry
        uint32_t freq_ix = (packed_entry >> BIN_ID_BITS) & 0xFF;  // 8 bits for freq_ix
        meaning_index = freq_ix - 1;
        bin_id = packed_entry & BIN_ID_MASK;
    } else if ((packed_entry & 0x60000000) == 0x40000000) {
        // Uses previous bin_id
        meaning_index = (packed_entry >> KSNID_BITS) & MEANING_MASK;
        // bin_id remains the same
        if (bin_id == -1) {
            // This shouldn't happen - corrupt data
            return BinEntry("", 0, "", "", "", "");
        }
    } else {
        // This is the second word of a two-word entry
        // The bin_id was already set by the caller
        meaning_index = (packed_entry >> KSNID_BITS) & MEANING_MASK;
    }
    
    // Decode meaning data
    auto [ofl, mark] = decode_meaning_data(meaning_index);
    
    // Decode lemma data
    auto [lemma, hluti] = decode_lemma_data(bin_id);
    
    return BinEntry(lemma, bin_id, ofl, hluti, "", mark);
}

// Decode a Ksnid entry with extended attributes
Ksnid BinImpl::decode_ksnid(uint32_t packed_entry, int32_t& bin_id) const {
    // Extract ksnid index from packed entry
    uint32_t ksnid_idx = 0;
    
    if ((packed_entry & 0x60000000) == 0x60000000) {
        // Single 32-bit packed entry - use common ksnid
        ksnid_idx = (packed_entry & 0x10000000) ? 1 : 0;
    } else if ((packed_entry & 0x60000000) == 0x40000000) {
        // ksnid is in lower bits
        ksnid_idx = packed_entry & KSNID_MASK;
    } else {
        // Two-word entry - need to read second word
        // This is handled by the caller
        ksnid_idx = 0;
    }
    
    // First decode as BinEntry
    BinEntry base = decode_meaning(packed_entry, bin_id);
    
    Ksnid result(base.ord, base.bin_id, base.ofl, base.hluti, base.bmynd, base.mark);
    
    if (ksnid_idx > 0) {
        // Decode ksnid string which contains semicolon-separated values
        uint32_t ksnid_offset = header_->ksnid_offset + ksnid_idx * 4;
        uint32_t ksnid_str_offset = read_uint32(ksnid_offset);
        
        // Read length-prefixed string
        uint8_t len = read_uint8(ksnid_str_offset);
        std::string ksnid_str;
        for (uint8_t i = 0; i < len; i++) {
            ksnid_str += static_cast<char>(read_uint8(ksnid_str_offset + 1 + i));
        }
        
        // Parse ksnid string: einkunn;malsnid;malfraedi;millivisun;birting;beinkunn;bmalsnid;bgildi;aukafletta
        std::vector<std::string> parts;
        std::stringstream ss(ksnid_str);
        std::string part;
        
        while (std::getline(ss, part, ';')) {
            parts.push_back(part);
        }
        
        if (parts.size() >= 9) {
            result.einkunn = parts[0].empty() ? 1 : std::stoi(parts[0]);
            result.malsnid = parts[1];
            result.malfraedi = parts[2];
            result.millivisun = parts[3].empty() ? 0 : std::stoi(parts[3]);
            result.birting = parts[4];
            result.beinkunn = parts[5].empty() ? 1 : std::stoi(parts[5]);
            result.bmalsnid = parts[6];
            result.bgildi = parts[7];
            result.aukafletta = parts[8];
        }
    }
    
    return result;
}

// Handle compound words
std::vector<BinEntry> BinImpl::handle_compound(const std::string& word) const {
    std::vector<BinEntry> results;
    
    if (!prefixes_dawg_ || !suffixes_dawg_) {
        return results;
    }
    
    // Try to find optimal split
    auto prefix_splits = prefixes_dawg_->find_splits(word);
    
    if (prefix_splits.size() == 2) {
        const std::string& prefix = prefix_splits[0];
        const std::string& suffix = prefix_splits[1];
        
        // Check if suffix exists in suffix DAWG
        if (suffixes_dawg_->contains(suffix)) {
            // Look up the suffix in BÍN
            uint32_t suffix_offset = find_word_offset(suffix);
            
            if (suffix_offset != NOT_FOUND) {
                // Get all meanings for the suffix
                std::vector<uint32_t> meanings = get_meanings(suffix_offset);
                
                int32_t bin_id = -1;
                for (uint32_t packed_entry : meanings) {
                    BinEntry entry = decode_meaning(packed_entry, bin_id);
                    
                    // Modify entry for compound word
                    entry.ord = prefix + "-" + entry.ord;
                    entry.bmynd = prefix + "-" + suffix;
                    entry.bin_id = 0;  // Compound words have bin_id = 0
                    
                    results.push_back(entry);
                }
            }
        }
    }
    
    return results;
}

std::vector<Ksnid> BinImpl::handle_compound_ksnid(const std::string& word) const {
    std::vector<Ksnid> results;
    
    // Similar to handle_compound but returns Ksnid entries
    auto basic_results = handle_compound(word);
    
    for (const auto& entry : basic_results) {
        Ksnid ksnid(entry.ord, entry.bin_id, entry.ofl, entry.hluti, entry.bmynd, entry.mark);
        results.push_back(ksnid);
    }
    
    return results;
}

// Implement remaining lookup methods

KsnidLookupResult BinImpl::lookup_ksnid(const std::string& word, bool at_sentence_start, bool auto_uppercase) const {
    if (word.empty()) {
        return {"", {}};
    }
    
    std::string search_word = word;
    
    // Handle z replacement
    if (options_.replace_z) {
        search_word = replace_z(search_word);
    }
    
    // Try exact match first
    uint32_t offset = find_word_offset(search_word);
    
    // If at sentence start and not found, try lowercase
    if (offset == NOT_FOUND && at_sentence_start && !search_word.empty() && 
        std::isupper(static_cast<unsigned char>(search_word[0]))) {
        std::string lower_word = search_word;
        lower_word[0] = std::tolower(static_cast<unsigned char>(lower_word[0]));
        offset = find_word_offset(lower_word);
        if (offset != NOT_FOUND) {
            search_word = lower_word;
        }
    }
    
    KsnidList results;
    
    if (offset != NOT_FOUND) {
        // Get all meanings for this word
        std::vector<uint32_t> meanings = get_meanings(offset);
        int32_t bin_id = -1;
        for (uint32_t packed_entry : meanings) {
            Ksnid entry = decode_ksnid(packed_entry, bin_id);
            entry.bmynd = search_word;  // Set the actual word form
            results.push_back(entry);
        }
    } else if (options_.add_compounds) {
        // Try compound word algorithm
        results = handle_compound_ksnid(search_word);
    }
    
    // Handle auto_uppercase
    std::string result_key = search_word;
    if (auto_uppercase && !results.empty()) {
        // Check if any result has uppercase form
        for (const auto& entry : results) {
            if (!entry.bmynd.empty() && std::isupper(static_cast<unsigned char>(entry.bmynd[0]))) {
                result_key[0] = std::toupper(static_cast<unsigned char>(result_key[0]));
                break;
            }
        }
    }
    
    return {result_key, results};
}

KsnidList BinImpl::lookup_id(int32_t bin_id) const {
    KsnidList results;
    
    // Linear search through lemmas section for matching bin_id
    // This is not optimal but matches the Python implementation
    uint32_t lemma_count = (header_->templates_offset - header_->lemmas_offset) / 16;
    
    for (uint32_t i = 0; i < lemma_count; ++i) {
        uint32_t lemma_offset = header_->lemmas_offset + i * 16;
        int32_t curr_bin_id = static_cast<int32_t>(read_uint32(lemma_offset + 4));
        
        if (curr_bin_id == bin_id) {
            // Found matching lemma - get all its forms
            uint32_t lemma_str_offset = read_uint32(lemma_offset);
            std::string lemma = from_latin1(decode_string(lemma_str_offset));
            
            // Look up all forms of this lemma
            auto lookup_result = lookup_ksnid(lemma, false, false);
            
            // Filter to only entries with matching bin_id
            for (const auto& entry : lookup_result.second) {
                if (entry.bin_id == bin_id) {
                    results.push_back(entry);
                }
            }
        }
    }
    
    return results;
}

std::set<std::string> BinImpl::lookup_cats(const std::string& word, bool at_sentence_start) const {
    std::set<std::string> categories;
    
    auto result = lookup(word, at_sentence_start, false);
    
    for (const auto& entry : result.second) {
        categories.insert(entry.ofl);
    }
    
    return categories;
}

std::set<std::pair<std::string, std::string>> BinImpl::lookup_lemmas_and_cats(const std::string& word, bool at_sentence_start) const {
    std::set<std::pair<std::string, std::string>> lemmas_and_cats;
    
    auto result = lookup(word, at_sentence_start, false);
    
    for (const auto& entry : result.second) {
        lemmas_and_cats.insert({entry.ord, entry.ofl});
    }
    
    return lemmas_and_cats;
}

LookupResult BinImpl::lookup_lemmas(const std::string& lemma) const {
    // Find all entries where ord == lemma
    BinEntryList results;
    
    // This requires searching through all word forms
    // For efficiency, we could build an index, but for now we'll search
    
    // Look up the lemma directly
    auto lookup_result = lookup(lemma, false, false);
    
    for (const auto& entry : lookup_result.second) {
        if (entry.ord == lemma) {
            results.push_back(entry);
        }
    }
    
    return {lemma, results};
}

// Public interface methods

std::set<std::string> Bin::lookup_cats(const std::string& word, bool at_sentence_start) const {
    if (!impl || !impl->is_loaded()) {
        return {};
    }
    return impl->lookup_cats(word, at_sentence_start);
}

std::set<std::pair<std::string, std::string>> Bin::lookup_lemmas_and_cats(const std::string& word, bool at_sentence_start) const {
    if (!impl || !impl->is_loaded()) {
        return {};
    }
    return impl->lookup_lemmas_and_cats(word, at_sentence_start);
}

LookupResult Bin::lookup_lemmas(const std::string& lemma) const {
    if (!impl || !impl->is_loaded()) {
        return {"", {}};
    }
    return impl->lookup_lemmas(lemma);
}

} // namespace islenska