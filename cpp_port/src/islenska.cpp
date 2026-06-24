/*
   BinPackage C++ Port

   Main implementation file

   Copyright © 2024 Miðeind ehf.
   
   This software is licensed under the MIT License.
*/

#include "islenska_impl.h"
#include <algorithm>
#include <cstring>
#include <sstream>
#include <iomanip>
#include <iostream>
#include <vector>

// Platform-specific includes for memory mapping
#ifdef _WIN32
    #include <windows.h>
#else
    #include <sys/mman.h>
    #include <sys/stat.h>
    #include <fcntl.h>
    #include <unistd.h>
#endif

namespace islenska {

// Constants for packed entry format (matching lookup.cpp)
constexpr uint32_t BIN_ID_BITS = 19;
constexpr uint32_t BIN_ID_MASK = (1 << BIN_ID_BITS) - 1;

// Version string
const char* version() {
    return "1.0.0";
}

// ============================================================================
// MemoryMap implementation
// ============================================================================

MemoryMap::MemoryMap() : data_(nullptr), size_(0), handle_(nullptr) {}

MemoryMap::~MemoryMap() {
    close();
}

bool MemoryMap::open(const std::string& filename) {
    close();
    
#ifdef _WIN32
    HANDLE file = CreateFileA(filename.c_str(), GENERIC_READ, FILE_SHARE_READ,
                             nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        return false;
    }
    
    LARGE_INTEGER file_size;
    if (!GetFileSizeEx(file, &file_size)) {
        CloseHandle(file);
        return false;
    }
    
    HANDLE mapping = CreateFileMappingA(file, nullptr, PAGE_READONLY,
                                       file_size.HighPart, file_size.LowPart, nullptr);
    CloseHandle(file);
    
    if (!mapping) {
        return false;
    }
    
    data_ = static_cast<const uint8_t*>(MapViewOfFile(mapping, FILE_MAP_READ, 0, 0, 0));
    CloseHandle(mapping);
    
    if (!data_) {
        return false;
    }
    
    size_ = static_cast<size_t>(file_size.QuadPart);
    handle_ = const_cast<uint8_t*>(data_);
#else
    int fd = ::open(filename.c_str(), O_RDONLY);
    if (fd < 0) {
        return false;
    }
    
    struct stat st;
    if (fstat(fd, &st) < 0) {
        ::close(fd);
        return false;
    }
    
    void* addr = mmap(nullptr, st.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
    ::close(fd);
    
    if (addr == MAP_FAILED) {
        return false;
    }
    
    data_ = static_cast<const uint8_t*>(addr);
    size_ = st.st_size;
    handle_ = addr;
#endif
    
    return true;
}

void MemoryMap::close() {
    if (!data_) {
        return;
    }
    
#ifdef _WIN32
    UnmapViewOfFile(handle_);
#else
    munmap(handle_, size_);
#endif
    
    data_ = nullptr;
    size_ = 0;
    handle_ = nullptr;
}

// ============================================================================
// BinImpl implementation
// ============================================================================

BinImpl::BinImpl(const Bin::Options& options) 
    : options_(options),
      header_(nullptr),
      lookup_cache_(1000),
      compound_cache_(500) {
}

BinImpl::~BinImpl() = default;

bool BinImpl::load_data() {
    // Load main compressed binary
    // Try multiple paths to find the data
    std::vector<std::string> possible_paths = {
        "../../src/islenska/resources/compressed.bin",  // From build directory
        "../src/islenska/resources/compressed.bin",     // From cpp_port directory
        "src/islenska/resources/compressed.bin",        // From project root
        "/Users/sveinbjorn/mideind/BinPackage/src/islenska/resources/compressed.bin"  // Absolute path
    };
    
    std::string bin_path;
    bool found = false;
    
    for (const auto& path : possible_paths) {
        if (mmap_.open(path)) {
            bin_path = path;
            found = true;
            break;
        }
    }
    
    if (!found) {
        std::cerr << "Error: Could not find compressed.bin in any of the expected locations" << std::endl;
        return false;
    }
    
    // Successfully loaded
    
    // Verify signature - the file starts with "Greynir XX.XX.XX"
    header_ = reinterpret_cast<const Header*>(mmap_.data());
    const char expected_prefix[] = "Greynir ";
    if (std::memcmp(header_->signature, expected_prefix, strlen(expected_prefix)) != 0) {
        std::cerr << "Error: Invalid signature in compressed.bin" << std::endl;
        std::cerr << "Expected prefix: " << expected_prefix << std::endl;
        std::cerr << "Got: ";
        for (int i = 0; i < 8; i++) {
            std::cerr << (char)header_->signature[i];
        }
        std::cerr << std::endl;
        mmap_.close();
        return false;
    }
    
    // Load alphabet
    uint32_t alphabet_offset = header_->alphabet_offset;
    uint32_t alphabet_length = read_uint32(alphabet_offset);
    alphabet_.resize(alphabet_length);
    
    for (uint32_t i = 0; i < alphabet_length; ++i) {
        uint8_t ch = read_uint8(alphabet_offset + 4 + i);
        alphabet_[i] = ch;
        alphabet_index_[ch] = i;
    }
    
    // Load DAWG dictionaries for compound words
    if (options_.add_compounds) {
        prefixes_dawg_ = std::make_unique<DAWGDictionary>();
        suffixes_dawg_ = std::make_unique<DAWGDictionary>();
        
        // Extract base directory from bin_path
        size_t pos = bin_path.find("compressed.bin");
        if (pos != std::string::npos) {
            std::string base_dir = bin_path.substr(0, pos);
            prefixes_dawg_->load(base_dir + "ordalisti-prefixes.dawg.bin");
            suffixes_dawg_->load(base_dir + "ordalisti-suffixes.dawg.bin");
        }
    }
    
    return true;
}

uint32_t BinImpl::read_uint32(size_t offset) const {
    if (offset + 4 > mmap_.size()) {
        return 0;
    }
    const uint8_t* p = mmap_.data() + offset;
    return static_cast<uint32_t>(p[0]) |
           (static_cast<uint32_t>(p[1]) << 8) |
           (static_cast<uint32_t>(p[2]) << 16) |
           (static_cast<uint32_t>(p[3]) << 24);
}

uint16_t BinImpl::read_uint16(size_t offset) const {
    if (offset + 2 > mmap_.size()) {
        return 0;
    }
    const uint8_t* p = mmap_.data() + offset;
    return static_cast<uint16_t>(p[0]) |
           (static_cast<uint16_t>(p[1]) << 8);
}

uint8_t BinImpl::read_uint8(size_t offset) const {
    if (offset >= mmap_.size()) {
        return 0;
    }
    return mmap_.data()[offset];
}

// Convert UTF-8 to Latin-1 for internal use
std::string BinImpl::to_latin1(const std::string& utf8) const {
    std::string result;
    result.reserve(utf8.size());
    
    for (size_t i = 0; i < utf8.size(); ++i) {
        unsigned char ch = utf8[i];
        if (ch < 0x80) {
            result.push_back(ch);
        } else if ((ch & 0xE0) == 0xC0 && i + 1 < utf8.size()) {
            // 2-byte UTF-8
            unsigned char ch2 = utf8[++i];
            int codepoint = ((ch & 0x1F) << 6) | (ch2 & 0x3F);
            if (codepoint < 0x100) {
                result.push_back(static_cast<char>(codepoint));
            } else {
                result.push_back('?');  // Can't represent in Latin-1
            }
        } else {
            // Skip other multi-byte sequences
            result.push_back('?');
            while (i + 1 < utf8.size() && (utf8[i + 1] & 0xC0) == 0x80) {
                ++i;
            }
        }
    }
    
    return result;
}

// Convert Latin-1 to UTF-8 for output
std::string BinImpl::from_latin1(const std::string& latin1) const {
    std::string result;
    result.reserve(latin1.size() * 2);  // Worst case
    
    for (unsigned char ch : latin1) {
        if (ch < 0x80) {
            result.push_back(ch);
        } else {
            // 2-byte UTF-8
            result.push_back(0xC0 | (ch >> 6));
            result.push_back(0x80 | (ch & 0x3F));
        }
    }
    
    return result;
}

// Replace z/tzt with s/st if enabled
std::string BinImpl::replace_z(const std::string& word) const {
    if (!options_.replace_z) {
        return word;
    }
    
    std::string result = word;
    
    // Replace "tzt" with "st"
    size_t pos = 0;
    while ((pos = result.find("tzt", pos)) != std::string::npos) {
        result.replace(pos, 3, "st");
        pos += 2;
    }
    
    // Replace "z" with "s"
    pos = 0;
    while ((pos = result.find('z', pos)) != std::string::npos) {
        result[pos] = 's';
        pos++;
    }
    
    return result;
}

// Declare the C function from bin.cpp
extern "C" {
    uint32_t mapping(const uint8_t* pbMap, const uint8_t* pbWordLatin);
}

// Find word offset using the existing C++ trie lookup
uint32_t BinImpl::find_word_offset(const std::string& word) const {
    // Check cache first
    auto cached = lookup_cache_.get(word);
    if (cached.has_value() && !cached.value().empty()) {
        return cached.value()[0];
    }
    
    // Convert to Latin-1 for lookup
    std::string word_latin1 = to_latin1(word);
    
    // Use the existing mapping function from bin.cpp
    uint32_t offset = mapping(mmap_.data(), reinterpret_cast<const uint8_t*>(word_latin1.c_str()));
    
    
    if (offset != NOT_FOUND) {
        lookup_cache_.put(word, {offset});
    }
    
    return offset;
}

// Get all meaning offsets for a word
std::vector<uint32_t> BinImpl::get_meanings(uint32_t offset) const {
    std::vector<uint32_t> meanings;
    
    if (offset == NOT_FOUND) {
        return meanings;
    }
    
    // The offset points to a sequence of packed entries
    uint32_t mapping = offset;
    
    while (true) {
        uint32_t w0 = read_uint32(header_->mappings_offset + mapping * 4);
        mapping++;
        
        // Check if this is a two-word entry
        if ((w0 & 0x60000000) == 0) {
            // Read second word and combine
            uint32_t w1 = read_uint32(header_->mappings_offset + mapping * 4);
            mapping++;
            // Store both words as a pair (w0 contains bin_id, w1 contains meaning/ksnid)
            meanings.push_back(w0);
            meanings.push_back(w1);
        } else {
            // Single word entry
            meanings.push_back(w0);
        }
        
        if (w0 & 0x80000000) {
            // Last mapping indicator: we're done
            break;
        }
    }
    
    return meanings;
}

// Decode a compressed string
std::string BinImpl::decode_compressed_string(const uint8_t* data) const {
    std::string result;
    
    while (*data) {
        uint8_t ch = *data & 0x7F;
        bool is_last = (*data & 0x80) != 0;
        
        if (ch < alphabet_.size()) {
            result.push_back(alphabet_[ch]);
        }
        
        if (is_last) {
            break;
        }
        
        ++data;
    }
    
    return result;
}

// Decode a string from the binary format
std::string BinImpl::decode_string(uint32_t offset) const {
    if (offset >= mmap_.size()) {
        return "";
    }
    
    const char* str = reinterpret_cast<const char*>(mmap_.data() + offset);
    size_t len = std::strlen(str);
    
    if (offset + len >= mmap_.size()) {
        return "";
    }
    
    return std::string(str, len);
}

// Basic lookup implementation
LookupResult BinImpl::lookup(const std::string& word, bool at_sentence_start, bool auto_uppercase) const {
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
    
    BinEntryList results;
    
    if (offset != NOT_FOUND) {
        // Get all meanings for this word
        std::vector<uint32_t> meanings = get_meanings(offset);
        int32_t bin_id = -1;
        
        for (size_t i = 0; i < meanings.size(); ) {
            uint32_t w0 = meanings[i];
            
            if ((w0 & 0x60000000) == 0 && i + 1 < meanings.size()) {
                // Two-word entry
                uint32_t w1 = meanings[i + 1];
                bin_id = w0 & BIN_ID_MASK;
                
                // Create entry from second word which has the meaning data
                BinEntry entry = decode_meaning(w1, bin_id);
                if (!entry.ord.empty()) {
                    entry.bmynd = search_word;
                    results.push_back(entry);
                }
                i += 2;
            } else {
                // Single-word entry
                BinEntry entry = decode_meaning(w0, bin_id);
                if (!entry.ord.empty()) {
                    entry.bmynd = search_word;
                    results.push_back(entry);
                }
                i += 1;
            }
        }
    } else if (options_.add_compounds) {
        // Try compound word algorithm
        results = handle_compound(search_word);
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

// The actual implementations are in lookup.cpp

// ============================================================================
// Bin public interface implementation
// ============================================================================

Bin::Bin() : Bin(Options{}) {}

Bin::Bin(const Options& options) : impl(std::make_unique<BinImpl>(options)) {
    impl->load_data();
}

Bin::~Bin() = default;

bool Bin::is_loaded() const {
    return impl && impl->is_loaded();
}

LookupResult Bin::lookup(const std::string& word, bool at_sentence_start, bool auto_uppercase) const {
    if (!impl || !impl->is_loaded()) {
        return {"", {}};
    }
    return impl->lookup(word, at_sentence_start, auto_uppercase);
}

KsnidLookupResult Bin::lookup_ksnid(const std::string& word, bool at_sentence_start, bool auto_uppercase) const {
    if (!impl || !impl->is_loaded()) {
        return {"", {}};
    }
    return impl->lookup_ksnid(word, at_sentence_start, auto_uppercase);
}

KsnidList Bin::lookup_id(int32_t bin_id) const {
    if (!impl || !impl->is_loaded()) {
        return {};
    }
    return impl->lookup_id(bin_id);
}

// ============================================================================
// Mark string utilities
// ============================================================================

namespace marks {

bool contains(const std::string& mark, const std::string& feature) {
    return mark.find(feature) != std::string::npos;
}

std::string get_case(const std::string& mark) {
    if (contains(mark, "NF")) return "NF";
    if (contains(mark, "ÞF")) return "ÞF";
    if (contains(mark, "ÞGF")) return "ÞGF";
    if (contains(mark, "EF")) return "EF";
    return "";
}

std::string get_number(const std::string& mark) {
    if (contains(mark, "ET")) return "ET";
    if (contains(mark, "FT")) return "FT";
    return "";
}

std::string get_gender(const std::string& mark) {
    if (contains(mark, "KK")) return "KK";
    if (contains(mark, "KVK")) return "KVK";
    if (contains(mark, "HK")) return "HK";
    return "";
}

bool is_definite(const std::string& mark) {
    return contains(mark, "gr");
}

bool is_indefinite(const std::string& mark) {
    return !is_definite(mark);
}

} // namespace marks

} // namespace islenska