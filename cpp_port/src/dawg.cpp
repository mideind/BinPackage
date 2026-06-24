/*
   BinPackage C++ Port

   DAWG (Directed Acyclic Word Graph) implementation

   Copyright © 2024 Miðeind ehf.
   
   This software is licensed under the MIT License.
*/

#include "islenska_impl.h"
#include <algorithm>
#include <queue>

namespace islenska {

// DAWG binary format constants
constexpr uint32_t DAWG_SIGNATURE = 0x44415747;  // "DAWG"
constexpr uint32_t DAWG_VERSION = 1;

// Node format flags
constexpr uint32_t NODE_END_OF_WORD = 0x80000000;
constexpr uint32_t NODE_END_OF_LIST = 0x40000000;
constexpr uint32_t NODE_LETTER_MASK = 0x000000FF;
constexpr uint32_t NODE_OFFSET_MASK = 0x3FFFFF00;
constexpr uint32_t NODE_OFFSET_SHIFT = 8;

struct DAWGHeader {
    uint32_t signature;
    uint32_t version;
    uint32_t node_count;
    uint32_t root_offset;
};

DAWGDictionary::DAWGDictionary() : data_(nullptr) {}

DAWGDictionary::~DAWGDictionary() = default;

bool DAWGDictionary::load(const std::string& filename) {
    if (!mmap_.open(filename)) {
        return false;
    }
    
    data_ = mmap_.data();
    
    // Verify header
    if (mmap_.size() < sizeof(DAWGHeader)) {
        mmap_.close();
        return false;
    }
    
    const DAWGHeader* header = reinterpret_cast<const DAWGHeader*>(data_);
    if (header->signature != DAWG_SIGNATURE || header->version != DAWG_VERSION) {
        mmap_.close();
        return false;
    }
    
    return true;
}

uint32_t DAWGDictionary::read_uint32(size_t offset) const {
    if (offset + 4 > mmap_.size()) {
        return 0;
    }
    const uint8_t* p = data_ + offset;
    return static_cast<uint32_t>(p[0]) |
           (static_cast<uint32_t>(p[1]) << 8) |
           (static_cast<uint32_t>(p[2]) << 16) |
           (static_cast<uint32_t>(p[3]) << 24);
}

bool DAWGDictionary::contains(const std::string& word) const {
    if (!data_ || word.empty()) {
        return false;
    }
    
    return navigate(word, 0);
}

bool DAWGDictionary::navigate(const std::string& word, size_t start_pos) const {
    const DAWGHeader* header = reinterpret_cast<const DAWGHeader*>(data_);
    uint32_t node_offset = header->root_offset;
    
    for (size_t i = start_pos; i < word.length(); ++i) {
        uint8_t target_letter = static_cast<uint8_t>(word[i]);
        bool found = false;
        
        while (true) {
            uint32_t node = read_uint32(node_offset);
            uint8_t node_letter = node & NODE_LETTER_MASK;
            
            if (node_letter == target_letter) {
                // Found matching letter
                found = true;
                
                if (i == word.length() - 1) {
                    // Last letter - check if it's end of word
                    return (node & NODE_END_OF_WORD) != 0;
                }
                
                // Move to child nodes
                uint32_t child_offset = (node & NODE_OFFSET_MASK) >> NODE_OFFSET_SHIFT;
                if (child_offset == 0) {
                    return false;  // No children
                }
                node_offset = child_offset * 4;  // Convert to byte offset
                break;
            }
            
            if (node & NODE_END_OF_LIST) {
                // End of sibling list, letter not found
                break;
            }
            
            // Move to next sibling
            node_offset += 4;
        }
        
        if (!found) {
            return false;
        }
    }
    
    return false;
}

std::vector<std::string> DAWGDictionary::find_splits(const std::string& word) const {
    std::vector<std::string> results;
    
    if (!data_ || word.empty()) {
        return results;
    }
    
    // Find all possible prefix positions where the word can be split
    std::vector<size_t> split_positions;
    
    for (size_t i = 1; i < word.length(); ++i) {
        std::string prefix = word.substr(0, i);
        std::string suffix = word.substr(i);
        
        // Check if prefix exists in this DAWG
        if (contains(prefix)) {
            split_positions.push_back(i);
        }
    }
    
    // For compound word analysis, we want the split with:
    // 1. Fewest components (prefer 2 parts over 3+)
    // 2. Longest suffix (for better inflection matching)
    
    if (!split_positions.empty()) {
        // Sort by suffix length (descending)
        std::sort(split_positions.begin(), split_positions.end(),
                  [&word](size_t a, size_t b) {
                      return (word.length() - a) > (word.length() - b);
                  });
        
        // Return the split position with longest suffix
        size_t best_split = split_positions[0];
        results.push_back(word.substr(0, best_split));
        results.push_back(word.substr(best_split));
    }
    
    return results;
}

} // namespace islenska