/*
   BinPackage C++ Port

   Basic lookup test program

   Copyright © 2024 Miðeind ehf.
   
   This software is licensed under the MIT License.
*/

#include <iostream>
#include <iomanip>
#include "islenska.h"

using namespace islenska;

void print_entry(const BinEntry& entry) {
    std::cout << "  ord: " << entry.ord 
              << ", ofl: " << entry.ofl
              << ", hluti: " << entry.hluti
              << ", bmynd: " << entry.bmynd
              << ", mark: " << entry.mark
              << ", bin_id: " << entry.bin_id << std::endl;
}

void test_basic_lookup() {
    std::cout << "\n=== Basic Lookup Test ===" << std::endl;
    
    Bin bin;
    if (!bin.is_loaded()) {
        std::cerr << "Failed to load BÍN database!" << std::endl;
        return;
    }
    
    // Test simple word lookup
    std::vector<std::string> test_words = {"hestur", "fara", "fallegur", "ekki"};
    
    for (const auto& word : test_words) {
        std::cout << "\nLooking up: " << word << std::endl;
        auto [search_key, results] = bin.lookup(word);
        std::cout << "Search key: " << search_key << std::endl;
        std::cout << "Found " << results.size() << " entries:" << std::endl;
        
        for (const auto& entry : results) {
            print_entry(entry);
        }
    }
}

void test_sentence_start() {
    std::cout << "\n=== Sentence Start Test ===" << std::endl;
    
    Bin bin;
    
    // Test uppercase at sentence start
    auto [key1, results1] = bin.lookup("Hestur", false, false);
    std::cout << "Lookup 'Hestur' (not at sentence start): " << results1.size() << " results" << std::endl;
    
    auto [key2, results2] = bin.lookup("Hestur", true, false);
    std::cout << "Lookup 'Hestur' (at sentence start): " << results2.size() << " results" << std::endl;
}

void test_z_replacement() {
    std::cout << "\n=== Z Replacement Test ===" << std::endl;
    
    Bin bin;
    
    // Test z replacement
    auto [key, results] = bin.lookup("þýzk");
    std::cout << "Lookup 'þýzk' returned key: " << key << std::endl;
    std::cout << "Found " << results.size() << " entries" << std::endl;
}

void test_compound_words() {
    std::cout << "\n=== Compound Word Test ===" << std::endl;
    
    Bin bin;
    
    // Test compound word
    std::vector<std::string> compounds = {"síamskattarkjóll", "sólarolíulegur"};
    
    for (const auto& word : compounds) {
        auto [key, results] = bin.lookup(word);
        std::cout << "\nCompound word: " << word << std::endl;
        std::cout << "Found " << results.size() << " entries:" << std::endl;
        
        for (const auto& entry : results) {
            print_entry(entry);
            // Note hyphen in compound lemma and form
            if (entry.ord.find('-') != std::string::npos) {
                std::cout << "  -> Recognized as compound word" << std::endl;
            }
        }
    }
}

void test_categories() {
    std::cout << "\n=== Word Categories Test ===" << std::endl;
    
    Bin bin;
    
    // Test getting word categories
    std::string word = "laga";
    auto cats = bin.lookup_cats(word);
    
    std::cout << "Categories for '" << word << "': ";
    for (const auto& cat : cats) {
        std::cout << cat << " ";
    }
    std::cout << std::endl;
    
    // Test lemmas and categories
    auto lemmas_cats = bin.lookup_lemmas_and_cats(word);
    std::cout << "\nLemmas and categories:" << std::endl;
    for (const auto& [lemma, cat] : lemmas_cats) {
        std::cout << "  " << lemma << " (" << cat << ")" << std::endl;
    }
}

void test_lookup_by_id() {
    std::cout << "\n=== Lookup by ID Test ===" << std::endl;
    
    Bin bin;
    
    // Test lookup by BÍN ID
    int32_t test_id = 495410;  // ID for "sko" (interjection)
    auto results = bin.lookup_id(test_id);
    
    std::cout << "Lookup by ID " << test_id << ":" << std::endl;
    std::cout << "Found " << results.size() << " entries" << std::endl;
    
    if (!results.empty()) {
        std::cout << "Word: " << results[0].ord << std::endl;
        std::cout << "Category: " << results[0].ofl << std::endl;
    }
}

int main() {
    std::cout << "Íslenska C++ Library Test Program" << std::endl;
    std::cout << "Version: " << version() << std::endl;
    
    try {
        test_basic_lookup();
        test_sentence_start();
        test_z_replacement();
        test_compound_words();
        test_categories();
        test_lookup_by_id();
        
        std::cout << "\n=== All tests completed ===" << std::endl;
    }
    catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
    
    return 0;
}