/*
   BinPackage C++ Port

   Internal implementation header

   Copyright © 2024 Miðeind ehf.
   
   This software is licensed under the MIT License.
*/

#ifndef ISLENSKA_IMPL_H
#define ISLENSKA_IMPL_H

#include "islenska.h"
#include <unordered_map>
#include <unordered_set>
#include <mutex>
#include <cstring>
#include <list>

namespace islenska {

// Constants
constexpr uint32_t NOT_FOUND = 0xFFFFFFFF;
constexpr size_t SIGNATURE_SIZE = 16;

// Packed structures for binary format
#pragma pack(push, 1)

struct Header {
    uint8_t signature[SIGNATURE_SIZE];
    uint32_t mappings_offset;
    uint32_t forms_offset;
    uint32_t lemmas_offset;
    uint32_t templates_offset;
    uint32_t meanings_offset;
    uint32_t alphabet_offset;
    uint32_t subcats_offset;
    uint32_t ksnid_offset;
};

#pragma pack(pop)

// DAWG node structure
struct DAWGNode {
    uint32_t offset;
    bool is_final;
    uint32_t value;
};

// Memory-mapped file wrapper
class MemoryMap {
public:
    MemoryMap();
    ~MemoryMap();
    
    bool open(const std::string& filename);
    void close();
    
    const uint8_t* data() const { return data_; }
    size_t size() const { return size_; }
    bool is_open() const { return data_ != nullptr; }
    
private:
    const uint8_t* data_;
    size_t size_;
    void* handle_;  // Platform-specific handle
};

// DAWG dictionary for compound words
class DAWGDictionary {
public:
    DAWGDictionary();
    ~DAWGDictionary();
    
    bool load(const std::string& filename);
    bool contains(const std::string& word) const;
    std::vector<std::string> find_splits(const std::string& word) const;
    
private:
    MemoryMap mmap_;
    const uint8_t* data_;
    
    bool navigate(const std::string& word, size_t start_pos = 0) const;
    uint32_t read_uint32(size_t offset) const;
};

// Cache for lookup results
template<typename K, typename V>
class LRUCache {
public:
    explicit LRUCache(size_t capacity) : capacity_(capacity) {}
    
    std::optional<V> get(const K& key) {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = cache_.find(key);
        if (it == cache_.end()) {
            return std::nullopt;
        }
        // Move to front (most recently used)
        usage_.splice(usage_.begin(), usage_, it->second.second);
        return it->second.first;
    }
    
    void put(const K& key, const V& value) {
        std::lock_guard<std::mutex> lock(mutex_);
        
        auto it = cache_.find(key);
        if (it != cache_.end()) {
            // Update existing entry
            it->second.first = value;
            usage_.splice(usage_.begin(), usage_, it->second.second);
            return;
        }
        
        // Add new entry
        if (cache_.size() >= capacity_) {
            // Remove least recently used
            const K& lru_key = usage_.back();
            cache_.erase(lru_key);
            usage_.pop_back();
        }
        
        usage_.push_front(key);
        cache_[key] = {value, usage_.begin()};
    }
    
    void clear() {
        std::lock_guard<std::mutex> lock(mutex_);
        cache_.clear();
        usage_.clear();
    }
    
private:
    size_t capacity_;
    std::list<K> usage_;
    std::unordered_map<K, std::pair<V, typename std::list<K>::iterator>> cache_;
    mutable std::mutex mutex_;
};

// Main implementation class
class BinImpl {
public:
    explicit BinImpl(const Bin::Options& options);
    ~BinImpl();
    
    bool load_data();
    
    // Lookup methods
    LookupResult lookup(const std::string& word, bool at_sentence_start, bool auto_uppercase) const;
    KsnidLookupResult lookup_ksnid(const std::string& word, bool at_sentence_start, bool auto_uppercase) const;
    KsnidList lookup_id(int32_t bin_id) const;
    std::set<std::string> lookup_cats(const std::string& word, bool at_sentence_start) const;
    std::set<std::pair<std::string, std::string>> lookup_lemmas_and_cats(const std::string& word, bool at_sentence_start) const;
    LookupResult lookup_lemmas(const std::string& lemma) const;
    KsnidList lookup_variants(const std::string& word, const std::string& cat,
                             const std::vector<std::string>& to_inflection,
                             const std::string& lemma, int32_t bin_id,
                             BinFilterFunc inflection_filter) const;
    
    bool is_loaded() const { return mmap_.is_open(); }
    
private:
    Bin::Options options_;
    MemoryMap mmap_;
    const Header* header_;
    
    // DAWG dictionaries for compound words
    std::unique_ptr<DAWGDictionary> prefixes_dawg_;
    std::unique_ptr<DAWGDictionary> suffixes_dawg_;
    
    // Caches
    mutable LRUCache<std::string, std::vector<uint32_t>> lookup_cache_;
    mutable LRUCache<std::string, std::vector<std::string>> compound_cache_;
    
    // Alphabet for compressed strings
    std::vector<uint8_t> alphabet_;
    std::unordered_map<uint8_t, size_t> alphabet_index_;
    
    // Internal lookup methods
    uint32_t find_word_offset(const std::string& word) const;
    std::vector<uint32_t> get_meanings(uint32_t offset) const;
    BinEntry decode_meaning(uint32_t packed_entry, int32_t& bin_id) const;
    Ksnid decode_ksnid(uint32_t packed_entry, int32_t& bin_id) const;
    std::pair<std::string, std::string> decode_meaning_data(uint32_t meaning_index) const;
    std::pair<std::string, std::string> decode_lemma_data(int32_t bin_id) const;
    
    // String decompression
    std::string decode_string(uint32_t offset) const;
    std::string decode_compressed_string(const uint8_t* data) const;
    
    // Compound word handling
    std::vector<std::pair<std::string, std::string>> find_compound_splits(const std::string& word) const;
    std::vector<BinEntry> handle_compound(const std::string& word) const;
    std::vector<Ksnid> handle_compound_ksnid(const std::string& word) const;
    
    // Utility methods
    uint32_t read_uint32(size_t offset) const;
    uint16_t read_uint16(size_t offset) const;
    uint8_t read_uint8(size_t offset) const;
    std::string to_latin1(const std::string& utf8) const;
    std::string from_latin1(const std::string& latin1) const;
    std::string replace_z(const std::string& word) const;
    
    // Mark string manipulation
    bool mark_matches(const std::string& mark, const std::vector<std::string>& requirements) const;
    std::string apply_case(const std::string& mark, const std::string& case_tag) const;
};

} // namespace islenska

#endif // ISLENSKA_IMPL_H