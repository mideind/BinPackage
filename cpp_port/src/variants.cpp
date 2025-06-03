/*
   BinPackage C++ Port

   Grammatical variants implementation

   Copyright © 2024 Miðeind ehf.
   
   This software is licensed under the MIT License.
*/

#include "islenska_impl.h"
#include <algorithm>
#include <sstream>

namespace islenska {

// Check if a mark string matches the given requirements
bool BinImpl::mark_matches(const std::string& mark, const std::vector<std::string>& requirements) const {
    for (const auto& req : requirements) {
        if (req == "nogr") {
            // Special case: no definite article
            if (mark.find("gr") != std::string::npos) {
                return false;
            }
        } else {
            // Normal requirement: must contain the string
            if (mark.find(req) == std::string::npos) {
                return false;
            }
        }
    }
    return true;
}

// Apply case transformation to a mark string
std::string BinImpl::apply_case(const std::string& mark, const std::string& case_tag) const {
    std::string result = mark;
    
    // Remove existing case markers
    const std::vector<std::string> cases = {"NF", "ÞF", "ÞGF", "EF"};
    for (const auto& c : cases) {
        size_t pos = result.find(c);
        if (pos != std::string::npos) {
            result.erase(pos, c.length());
        }
    }
    
    // Add new case marker at the beginning
    result = case_tag + result;
    
    return result;
}

// Get grammatical variants of a word
KsnidList BinImpl::lookup_variants(
    const std::string& word,
    const std::string& cat,
    const std::vector<std::string>& to_inflection,
    const std::string& lemma,
    int32_t bin_id,
    BinFilterFunc inflection_filter) const {
    
    KsnidList results;
    
    // First, get all forms of the word
    auto lookup_result = lookup_ksnid(word, false, false);
    
    // Filter by category
    std::vector<Ksnid> candidates;
    for (const auto& entry : lookup_result.second) {
        bool cat_match = false;
        
        if (cat == "no") {
            // Special case: "no" matches any noun category
            cat_match = (entry.ofl == "kk" || entry.ofl == "kvk" || entry.ofl == "hk");
        } else {
            cat_match = (entry.ofl == cat);
        }
        
        // Also filter by lemma if specified
        if (cat_match && (lemma.empty() || entry.ord == lemma)) {
            // And by bin_id if specified
            if (bin_id == 0 || entry.bin_id == bin_id) {
                candidates.push_back(entry);
            }
        }
    }
    
    if (candidates.empty()) {
        return results;
    }
    
    // For each candidate, find all its inflectional forms
    for (const auto& candidate : candidates) {
        // Look up all forms of this lemma
        auto lemma_forms = lookup_ksnid(candidate.ord, false, false);
        
        for (const auto& form : lemma_forms.second) {
            // Check if this form matches the same lemma and category
            if (form.ord != candidate.ord || form.ofl != candidate.ofl) {
                continue;
            }
            
            // Check if the mark matches all requirements
            if (mark_matches(form.mark, to_inflection)) {
                // Apply inflection filter if provided
                if (!inflection_filter || inflection_filter(form.mark)) {
                    results.push_back(form);
                }
            }
        }
    }
    
    // Remove duplicates
    std::sort(results.begin(), results.end(), 
        [](const Ksnid& a, const Ksnid& b) {
            return std::tie(a.bmynd, a.mark) < std::tie(b.bmynd, b.mark);
        });
    
    results.erase(
        std::unique(results.begin(), results.end(),
            [](const Ksnid& a, const Ksnid& b) {
                return a.bmynd == b.bmynd && a.mark == b.mark;
            }),
        results.end()
    );
    
    return results;
}

// Public interface implementations

KsnidList Bin::lookup_variants(
    const std::string& word,
    const std::string& cat,
    const std::string& to_inflection,
    const std::string& lemma,
    int32_t bin_id,
    BinFilterFunc inflection_filter) const {
    
    if (!impl || !impl->is_loaded()) {
        return {};
    }
    
    // Convert single inflection to vector
    std::vector<std::string> inflections = {to_inflection};
    return impl->lookup_variants(word, cat, inflections, lemma, bin_id, inflection_filter);
}

KsnidList Bin::lookup_variants(
    const std::string& word,
    const std::string& cat,
    const std::vector<std::string>& to_inflection,
    const std::string& lemma,
    int32_t bin_id,
    BinFilterFunc inflection_filter) const {
    
    if (!impl || !impl->is_loaded()) {
        return {};
    }
    
    return impl->lookup_variants(word, cat, to_inflection, lemma, bin_id, inflection_filter);
}

} // namespace islenska