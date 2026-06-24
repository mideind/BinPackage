/*
   BinPackage C++ Port

   Main header file for the Icelandic morphology library

   Copyright © 2024 Miðeind ehf.
   
   This software is licensed under the MIT License.
*/

#ifndef ISLENSKA_H
#define ISLENSKA_H

#include <string>
#include <vector>
#include <set>
#include <map>
#include <memory>
#include <functional>
#include <cstdint>
#include <optional>

namespace islenska {

// Forward declarations
class BinImpl;
class DAWGDictionary;

// Basic data structure representing a word entry (Sigrúnarsnið)
struct BinEntry {
    std::string ord;      // Lemma (headword)
    int32_t bin_id;       // Unique identifier for lemma/class combination
    std::string ofl;      // Word class/category (kk, kvk, hk, lo, so, ao, etc.)
    std::string hluti;    // Semantic classification (alm, ism, örn, etc.)
    std::string bmynd;    // Inflectional form
    std::string mark;     // Inflectional tag (e.g. ÞGFETgr)
    
    // Constructor
    BinEntry(const std::string& ord, int32_t bin_id, const std::string& ofl,
             const std::string& hluti, const std::string& bmynd, const std::string& mark)
        : ord(ord), bin_id(bin_id), ofl(ofl), hluti(hluti), bmynd(bmynd), mark(mark) {}
    
    // Equality operator
    bool operator==(const BinEntry& other) const {
        return ord == other.ord && bin_id == other.bin_id && 
               ofl == other.ofl && hluti == other.hluti &&
               bmynd == other.bmynd && mark == other.mark;
    }
};

// Extended data structure with additional attributes (Kristínarsnið)
struct Ksnid : public BinEntry {
    int einkunn;              // Correctness grade (0-5)
    std::string malsnid;      // Genre/register indicator
    std::string malfraedi;    // Grammatical marking
    int millivisun;           // Cross-reference ID
    std::string birting;      // K for core, V for other
    int beinkunn;             // Form correctness grade
    std::string bmalsnid;     // Form genre/register
    std::string bgildi;       // Special form indicator
    std::string aukafletta;   // Alternative headword
    
    // Constructor
    Ksnid(const std::string& ord, int32_t bin_id, const std::string& ofl,
          const std::string& hluti, const std::string& bmynd, const std::string& mark)
        : BinEntry(ord, bin_id, ofl, hluti, bmynd, mark),
          einkunn(1), millivisun(0), beinkunn(1) {}
};

// Filter function type for inflection filtering
using BinFilterFunc = std::function<bool(const std::string&)>;

// Result types
using BinEntryList = std::vector<BinEntry>;
using KsnidList = std::vector<Ksnid>;
using LookupResult = std::pair<std::string, BinEntryList>;
using KsnidLookupResult = std::pair<std::string, KsnidList>;

// Main BÍN database interface
class Bin {
public:
    // Constructor flags
    struct Options {
        bool add_negation = true;     // Add ó- prefixed adjectives
        bool add_legur = true;        // Add -legur suffixed adjectives  
        bool add_compounds = true;    // Use compound word algorithm
        bool replace_z = true;        // Replace z/tzt with s/st
        bool only_bin = false;        // Only return original BÍN entries
        
        Options() = default;
    };
    
    // Constructors
    Bin();
    explicit Bin(const Options& options);
    Bin(const Bin&) = delete;  // Non-copyable
    Bin& operator=(const Bin&) = delete;
    Bin(Bin&&) = default;  // Movable
    Bin& operator=(Bin&&) = default;
    ~Bin();
    
    // Basic lookup - returns (search_key, list of matches)
    LookupResult lookup(const std::string& word, 
                       bool at_sentence_start = false,
                       bool auto_uppercase = false) const;
    
    // Lookup with full Kristínarsnið data
    KsnidLookupResult lookup_ksnid(const std::string& word,
                                   bool at_sentence_start = false,
                                   bool auto_uppercase = false) const;
    
    // Lookup by BÍN ID
    KsnidList lookup_id(int32_t bin_id) const;
    
    // Get possible word classes for a word form
    std::set<std::string> lookup_cats(const std::string& word,
                                      bool at_sentence_start = false) const;
    
    // Get possible lemmas and categories
    std::set<std::pair<std::string, std::string>> lookup_lemmas_and_cats(
        const std::string& word,
        bool at_sentence_start = false) const;
    
    // Get lemmas only
    LookupResult lookup_lemmas(const std::string& lemma) const;
    
    // Get grammatical variants
    KsnidList lookup_variants(const std::string& word,
                             const std::string& cat,
                             const std::string& to_inflection,
                             const std::string& lemma = "",
                             int32_t bin_id = 0,
                             BinFilterFunc inflection_filter = nullptr) const;
    
    // Overload for multiple inflection requirements
    KsnidList lookup_variants(const std::string& word,
                             const std::string& cat,
                             const std::vector<std::string>& to_inflection,
                             const std::string& lemma = "",
                             int32_t bin_id = 0,
                             BinFilterFunc inflection_filter = nullptr) const;

    // Check if data is loaded
    bool is_loaded() const;
    
private:
    std::unique_ptr<BinImpl> impl;
};

// Utility functions for mark string manipulation
namespace marks {
    // Check if a mark string contains a specific feature
    bool contains(const std::string& mark, const std::string& feature);
    
    // Extract case from mark string (NF, ÞF, ÞGF, EF)
    std::string get_case(const std::string& mark);
    
    // Extract number from mark string (ET, FT)
    std::string get_number(const std::string& mark);
    
    // Extract gender from mark string (KK, KVK, HK)
    std::string get_gender(const std::string& mark);
    
    // Check if mark indicates definite form (gr)
    bool is_definite(const std::string& mark);
    
    // Check if mark indicates indefinite form (no gr)
    bool is_indefinite(const std::string& mark);
}

// Version information
extern const char* version();

} // namespace islenska

#endif // ISLENSKA_H