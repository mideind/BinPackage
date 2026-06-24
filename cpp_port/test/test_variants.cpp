/*
   BinPackage C++ Port

   Grammatical variants test program

   Copyright © 2024 Miðeind ehf.
   
   This software is licensed under the MIT License.
*/

#include <iostream>
#include <vector>
#include "islenska.h"

using namespace islenska;

void test_case_conversion() {
    std::cout << "=== Case Conversion Test ===" << std::endl;
    
    Bin bin;
    
    // Convert "Laugavegur" to dative case
    std::cout << "\nConverting 'Laugavegur' to dative case (ÞGF):" << std::endl;
    auto variants = bin.lookup_variants("Laugavegur", "kk", "ÞGF");
    
    if (!variants.empty()) {
        std::cout << "Result: " << variants[0].bmynd << std::endl;
        std::cout << "Mark: " << variants[0].mark << std::endl;
    }
    
    // Convert "heftaranum" to nominative
    std::cout << "\nConverting 'heftaranum' (ÞGFETgr) to nominative (NF):" << std::endl;
    variants = bin.lookup_variants("heftaranum", "kk", "NF");
    
    if (!variants.empty()) {
        std::cout << "Result: " << variants[0].bmynd << std::endl;
    }
}

void test_number_conversion() {
    std::cout << "\n=== Number Conversion Test ===" << std::endl;
    
    Bin bin;
    
    // Convert singular to plural
    std::cout << "\nConverting 'heftarinn' to plural:" << std::endl;
    std::vector<std::string> reqs = {"NF", "FT"};
    auto variants = bin.lookup_variants("heftarinn", "kk", reqs);
    
    if (!variants.empty()) {
        std::cout << "Result: " << variants[0].bmynd << std::endl;
    }
    
    // Convert to indefinite plural
    std::cout << "\nConverting 'heftarinn' to indefinite plural:" << std::endl;
    std::vector<std::string> reqs2 = {"NF", "FT", "nogr"};
    variants = bin.lookup_variants("heftarinn", "kk", reqs2);
    
    if (!variants.empty()) {
        std::cout << "Result: " << variants[0].bmynd << std::endl;
    }
}

void test_adjective_degrees() {
    std::cout << "\n=== Adjective Degrees Test ===" << std::endl;
    
    Bin bin;
    
    // Convert adjective to superlative
    std::cout << "\nConverting 'fallegur' to superlative (EVB, HK, NF, FT):" << std::endl;
    std::vector<std::string> adjReqs = {"EVB", "HK", "NF", "FT"};
    auto variants = bin.lookup_variants("fallegur", "lo", adjReqs);
    
    if (!variants.empty()) {
        std::cout << "Result: " << variants[0].bmynd << std::endl;
        std::cout << "Usage: Ég sá " << variants[0].bmynd << " norðurljósin" << std::endl;
    }
    
    // Convert to comparative
    std::cout << "\nConverting 'frábær' to comparative (MST, KVK):" << std::endl;
    std::vector<std::string> compReqs = {"MST", "KVK"};
    variants = bin.lookup_variants("frábær", "lo", compReqs);
    
    if (!variants.empty()) {
        std::cout << "Result: " << variants[0].bmynd << std::endl;
        std::cout << "Usage: Þessi virkni er " << variants[0].bmynd << " en allt annað" << std::endl;
    }
}

void test_verb_moods() {
    std::cout << "\n=== Verb Mood Conversion Test ===" << std::endl;
    
    Bin bin;
    
    // Convert from subjunctive to indicative
    std::cout << "\nConverting 'hraðlæsi' (subjunctive) to indicative (FH, NT):" << std::endl;
    std::vector<std::string> verbReqs = {"FH", "NT"};
    auto variants = bin.lookup_variants("hraðlæsi", "so", verbReqs);
    
    std::cout << "Results:" << std::endl;
    for (const auto& v : variants) {
        std::cout << "  " << v.ord << " | " << v.bmynd << " | " << v.mark << std::endl;
    }
}

void test_inflection_filter() {
    std::cout << "\n=== Inflection Filter Test ===" << std::endl;
    
    Bin bin;
    
    // Get only feminine forms of an adjective
    std::cout << "\nGetting only feminine plural forms of 'breiður':" << std::endl;
    
    auto filter = [](const std::string& mark) {
        return marks::contains(mark, "KVK") && marks::contains(mark, "FT");
    };
    
    std::vector<std::string> filterReqs = {"NF"};
    auto variants = bin.lookup_variants("breiður", "lo", filterReqs, "", 0, filter);
    
    for (const auto& v : variants) {
        std::cout << "  " << v.bmynd << " (" << v.mark << ")" << std::endl;
    }
}

void test_noun_declension() {
    std::cout << "\n=== Full Noun Declension Test ===" << std::endl;
    
    Bin bin;
    
    std::string noun = "hestur";
    std::cout << "\nDeclension of '" << noun << "' (masculine, singular, indefinite):" << std::endl;
    
    const std::vector<std::string> cases = {"NF", "ÞF", "ÞGF", "EF"};
    const std::vector<std::string> case_names = {"Nominative", "Accusative", "Dative", "Genitive"};
    
    for (size_t i = 0; i < cases.size(); ++i) {
        std::vector<std::string> nounReqs = {cases[i], "ET", "nogr"};
        auto variants = bin.lookup_variants(noun, "kk", nounReqs);
        if (!variants.empty()) {
            std::cout << "  " << case_names[i] << ": " << variants[0].bmynd << std::endl;
        }
    }
    
    std::cout << "\nSame noun, plural with definite article:" << std::endl;
    for (size_t i = 0; i < cases.size(); ++i) {
        std::vector<std::string> nounReqsPlural = {cases[i], "FT", "gr"};
        auto variants = bin.lookup_variants(noun, "kk", nounReqsPlural);
        if (!variants.empty()) {
            std::cout << "  " << case_names[i] << ": " << variants[0].bmynd << std::endl;
        }
    }
}

int main() {
    std::cout << "Íslenska C++ Library - Grammatical Variants Test" << std::endl;
    std::cout << "================================================\n" << std::endl;
    
    try {
        test_case_conversion();
        test_number_conversion();
        test_adjective_degrees();
        test_verb_moods();
        test_inflection_filter();
        test_noun_declension();
        
        std::cout << "\n=== All variant tests completed ===" << std::endl;
    }
    catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
    
    return 0;
}