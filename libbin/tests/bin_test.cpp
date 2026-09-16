/*

   BinPackage

   libbin: smoke test

   Copyright © 2026 Miðeind ehf.

   This software is licensed under the MIT License; see bin.h.

   Usage: bin_test <resource-dir>

   Opens compressed.bin and the three ordalisti-*.dawg.bin files in the
   directory, runs a handful of lookups and checks their results. Works
   with a full or a compact build. Exits nonzero on failure.

*/

#include <stdio.h>
#include <string.h>

#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include "libbin/bin.h"

namespace {

int failures = 0;

#define CHECK(cond)                                                              \
    do {                                                                         \
        if (!(cond)) {                                                           \
            failures++;                                                          \
            std::cerr << "FAIL " << __FILE__ << ":" << __LINE__ << ": " << #cond \
                      << std::endl;                                              \
        }                                                                        \
    } while (0)

bool read_file(const std::string& path, std::vector<uint8_t>& out) {
    std::ifstream f(path, std::ios::binary);
    if (!f) {
        return false;
    }
    out.assign(std::istreambuf_iterator<char>(f), std::istreambuf_iterator<char>());
    return true;
}

// Latin-1 literals for the Icelandic characters used below
const char* BOKAHILLA = "b\xf3kahilla";      // bókahilla
const char* BOKAHILLUM = "b\xf3kahillum";    // bókahillum
const char* HESTUR = "hestur";
const char* HESTARNIR = "hestarnir";

bool has_entry(const BinResult* r, const char* ord, const char* ofl, const char* mark) {
    if (!r) {
        return false;
    }
    for (uint32_t i = 0; i < r->count; i++) {
        const BinEntry& e = r->entries[i];
        if (strcmp(e.ord, ord) == 0 && strcmp(e.ofl, ofl) == 0 && strcmp(e.mark, mark) == 0) {
            return true;
        }
    }
    return false;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "Usage: bin_test <resource-dir>" << std::endl;
        return 2;
    }
    std::string dir = argv[1];
    std::vector<uint8_t> bin, all, prefixes, suffixes;
    if (!read_file(dir + "/compressed.bin", bin) || !read_file(dir + "/ordalisti-all.dawg.bin", all) ||
        !read_file(dir + "/ordalisti-prefixes.dawg.bin", prefixes) ||
        !read_file(dir + "/ordalisti-suffixes.dawg.bin", suffixes)) {
        std::cerr << "Cannot read the data files in " << dir << std::endl;
        return 2;
    }
    BinDawg* d_all = bin_dawg_open(all.data(), all.size());
    BinDawg* d_pre = bin_dawg_open(prefixes.data(), prefixes.size());
    BinDawg* d_suf = bin_dawg_open(suffixes.data(), suffixes.size());
    CHECK(d_all && d_pre && d_suf);
    char err[256] = {0};
    BinDict* dict = bin_open(bin.data(), bin.size(), d_all, d_pre, d_suf, err, sizeof(err));
    if (!dict) {
        std::cerr << "bin_open failed: " << err << std::endl;
        return 1;
    }
    std::cout << (bin_is_compact(dict) ? "compact" : "full") << " build, max bin_id " << bin_max_bin_id(dict)
              << ", Greynir additions from " << bin_begin_greynir_utg(dict) << std::endl;

    // DAWG membership and slicing
    CHECK(bin_dawg_contains(d_all, HESTUR));
    CHECK(!bin_dawg_contains(d_all, "xyzzy"));
    BinSplits* splits = bin_compound_candidates(dict, BOKAHILLA);
    CHECK(splits && splits->count >= 1);
    if (splits) {
        // The best split is b\xf3ka + hilla
        bool found = false;
        for (uint32_t i = 0; i < splits->count; i++) {
            if (splits->splits[i].count == 2 && strcmp(splits->splits[i].items[1], "hilla") == 0) {
                found = true;
            }
        }
        CHECK(found);
        bin_splits_free(splits);
    }

    // Plain lookups
    CHECK(bin_contains(dict, HESTUR));
    CHECK(!bin_contains(dict, "xyzzy"));
    BinResult* r = bin_lookup(dict, HESTARNIR, nullptr, nullptr, 0);
    CHECK(has_entry(r, HESTUR, "kk", "NFFTgr"));
    bin_result_free(r);
    r = bin_lookup(dict, HESTARNIR, "kvk", nullptr, 0);
    CHECK(r == nullptr);
    bin_result_free(r);

    // A compound that a compact build restores: same result either way
    CHECK(bin_contains(dict, BOKAHILLUM));
    r = bin_lookup(dict, BOKAHILLUM, nullptr, nullptr, 0);
    CHECK(has_entry(r, BOKAHILLA, "kvk", "\xdeGFFT"));  // ÞGFFT
    uint32_t bin_id = 0;
    if (r) {
        for (uint32_t i = 0; i < r->count; i++) {
            if (strcmp(r->entries[i].ord, BOKAHILLA) == 0) {
                bin_id = r->entries[i].bin_id;
                CHECK(strcmp(r->entries[i].hluti, "alm") == 0);
                CHECK(strcmp(r->entries[i].bmynd, BOKAHILLUM) == 0);
            }
        }
    }
    bin_result_free(r);
    CHECK(bin_id != 0);

    // The lemma record and the forms of the compound
    BinLemma* lem = bin_lemma(dict, bin_id);
    CHECK(lem && strcmp(lem->lemma, BOKAHILLA) == 0);
    if (lem) {
        CHECK(bin_is_compact(dict) ? (lem->dropped && lem->num_heads >= 1) : !lem->dropped);
        bin_lemma_free(lem);
    }
    BinStrings* forms = bin_lemma_forms(dict, bin_id);
    CHECK(forms && forms->count >= 8);
    if (forms) {
        CHECK(strcmp(forms->items[forms->count - 1], BOKAHILLA) == 0);
        bin_strings_free(forms);
    }
    r = bin_lookup_id(dict, bin_id);
    CHECK(has_entry(r, BOKAHILLA, "kvk", "NFET"));
    CHECK(has_entry(r, BOKAHILLA, "kvk", "\xdeGFFT"));
    if (r) {
        for (uint32_t i = 0; i < r->count; i++) {
            CHECK(r->entries[i].bin_id == bin_id);
        }
    }
    bin_result_free(r);

    // Raw lookup and decoding
    BinRawResult* raw = bin_lookup_raw(dict, HESTUR);
    CHECK(raw && raw->count >= 1);
    if (raw) {
        BinStrings* m = bin_meaning(dict, raw->entries[0].meaning_index);
        CHECK(m && m->count == 2 && strcmp(m->items[0], "kk") == 0);
        bin_strings_free(m);
        char* k = bin_ksnid_string(dict, raw->entries[0].ksnid_index);
        CHECK(k && strlen(k) > 0);
        bin_string_free(k);
        bin_raw_result_free(raw);
    }

    bin_close(dict);
    bin_dawg_close(d_all);
    bin_dawg_close(d_pre);
    bin_dawg_close(d_suf);
    if (failures) {
        std::cerr << failures << " check(s) failed" << std::endl;
        return 1;
    }
    std::cout << "OK" << std::endl;
    return 0;
}
