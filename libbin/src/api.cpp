/*

   BinPackage

   libbin: C API

   Copyright © 2026 Miðeind ehf.
   Original author: Vilhjálmur Þorsteinsson

   This software is licensed under the MIT License; see bin.h.

   The C functions declared in bin.h, implemented over the Dawg and Dict
   classes. Result objects are allocated here and returned to the caller
   together with the strings they point into; the *_free functions release
   them. No exception escapes this layer: errors yield NULL or 0.

*/

#include <stdio.h>
#include <string.h>

#include <memory>
#include <new>
#include <string>
#include <vector>

#include "dawg.h"
#include "dict.h"
#include "libbin/bin.h"

using namespace libbin;

// The opaque handle types are the C++ classes
struct BinDawg : public Dawg {
    using Dawg::Dawg;
};

struct BinDict : public Dict {
    using Dict::Dict;
};

namespace {

// Result containers: the public struct first, so that the pointer handed
// out can be cast back to the container

struct ResultBox {
    BinResult pub;
    std::vector<Entry> entries;
    std::vector<BinEntry> view;
    std::string word;
};

struct RawResultBox {
    BinRawResult pub;
    std::vector<BinRawEntry> entries;
};

struct StringsBox {
    BinStrings pub;
    std::vector<std::string> items;
    std::vector<char*> view;
};

struct SplitsBox {
    BinSplits pub;
    std::vector<StringsBox> splits;
    std::vector<BinStrings> view;
};

struct LemmaBox {
    BinLemma pub;
    LemmaRecord rec;
};

void fill_strings(StringsBox& box, std::vector<std::string>&& items) {
    box.items = std::move(items);
    box.view.clear();
    box.view.reserve(box.items.size());
    for (auto& s : box.items) {
        box.view.push_back(&s[0]);
    }
    box.pub.items = box.view.data();
    box.pub.count = (uint32_t)box.items.size();
}

BinStrings* make_strings(std::vector<std::string>&& items) {
    if (items.empty()) {
        return nullptr;
    }
    StringsBox* box = new (std::nothrow) StringsBox;
    if (!box) {
        return nullptr;
    }
    fill_strings(*box, std::move(items));
    return &box->pub;
}

BinSplits* make_splits(std::vector<std::vector<std::string>>&& splits) {
    if (splits.empty()) {
        return nullptr;
    }
    SplitsBox* box = new (std::nothrow) SplitsBox;
    if (!box) {
        return nullptr;
    }
    box->splits.resize(splits.size());
    box->view.reserve(splits.size());
    for (size_t i = 0; i < splits.size(); i++) {
        fill_strings(box->splits[i], std::move(splits[i]));
        box->view.push_back(box->splits[i].pub);
    }
    box->pub.splits = box->view.data();
    box->pub.count = (uint32_t)box->view.size();
    return &box->pub;
}

BinResult* make_result(std::vector<Entry>&& entries, bool restored = false, const std::string& word = "") {
    if (entries.empty()) {
        return nullptr;
    }
    ResultBox* box = new (std::nothrow) ResultBox;
    if (!box) {
        return nullptr;
    }
    box->entries = std::move(entries);
    box->word = word;
    box->pub.restored = restored ? 1 : 0;
    box->pub.word = box->word.c_str();
    box->view.reserve(box->entries.size());
    for (const Entry& e : box->entries) {
        BinEntry v;
        v.ord = e.ord.c_str();
        v.bin_id = e.bin_id;
        v.ofl = e.ofl.c_str();
        v.hluti = e.hluti.c_str();
        v.bmynd = e.bmynd.c_str();
        v.mark = e.mark.c_str();
        v.ksnid = e.ksnid.c_str();
        box->view.push_back(v);
    }
    box->pub.entries = box->view.data();
    box->pub.count = (uint32_t)box->view.size();
    return &box->pub;
}

}  // namespace

extern "C" {

// ---- DAWGs ----

BinDawg* bin_dawg_open(const uint8_t* map, size_t len) {
    try {
        return new BinDawg(map, len);
    } catch (...) {
        return nullptr;
    }
}

void bin_dawg_close(BinDawg* dawg) { delete dawg; }

int bin_dawg_contains(const BinDawg* dawg, const char* word) {
    if (!dawg || !word) {
        return 0;
    }
    try {
        return dawg->contains(word) ? 1 : 0;
    } catch (...) {
        return 0;
    }
}

BinSplits* bin_dawg_find_combinations(const BinDawg* dawg, const char* word) {
    if (!dawg || !word) {
        return nullptr;
    }
    try {
        return make_splits(dawg->find_combinations(word));
    } catch (...) {
        return nullptr;
    }
}

// ---- Dictionary ----

BinDict* bin_open(const uint8_t* map, size_t len, const BinDawg* dawg_all, const BinDawg* dawg_prefixes,
                  const BinDawg* dawg_suffixes, char* errbuf, size_t errbuf_len) {
    try {
        return new BinDict(map, len, dawg_all, dawg_prefixes, dawg_suffixes);
    } catch (const std::exception& e) {
        if (errbuf && errbuf_len) {
            snprintf(errbuf, errbuf_len, "%s", e.what());
        }
        return nullptr;
    } catch (...) {
        if (errbuf && errbuf_len) {
            snprintf(errbuf, errbuf_len, "Unknown error opening dictionary");
        }
        return nullptr;
    }
}

void bin_close(BinDict* dict) { delete dict; }

int bin_is_compact(const BinDict* dict) { return dict && dict->is_compact() ? 1 : 0; }

int bin_has_dawgs(const BinDict* dict) { return dict && dict->has_dawgs() ? 1 : 0; }

uint32_t bin_begin_greynir_utg(const BinDict* dict) { return dict ? dict->begin_greynir_utg() : 0; }

uint32_t bin_max_bin_id(const BinDict* dict) { return dict ? dict->max_bin_id() : 0; }

int bin_contains(const BinDict* dict, const char* word) {
    if (!dict || !word) {
        return 0;
    }
    try {
        return dict->contains(word) ? 1 : 0;
    } catch (...) {
        return 0;
    }
}

BinResult* bin_lookup(const BinDict* dict, const char* word, const char* cat, const char* lemma,
                      uint32_t bin_id) {
    if (!dict || !word) {
        return nullptr;
    }
    try {
        std::vector<Entry> entries;
        dict->lookup(word, cat, lemma, bin_id, entries);
        bool restored = !entries.empty() && dict->is_compact() && !dict->trie_contains(word);
        return make_result(std::move(entries), restored, word);
    } catch (...) {
        return nullptr;
    }
}

BinRawResult* bin_lookup_raw(const BinDict* dict, const char* word) {
    if (!dict || !word) {
        return nullptr;
    }
    try {
        std::vector<RawEntry> raw;
        dict->raw_lookup(word, raw);
        if (raw.empty()) {
            return nullptr;
        }
        RawResultBox* box = new (std::nothrow) RawResultBox;
        if (!box) {
            return nullptr;
        }
        box->entries.reserve(raw.size());
        for (const RawEntry& r : raw) {
            BinRawEntry e;
            e.bin_id = r.bin_id;
            e.meaning_index = r.meaning_index;
            e.ksnid_index = r.ksnid_index;
            box->entries.push_back(e);
        }
        box->pub.entries = box->entries.data();
        box->pub.count = (uint32_t)box->entries.size();
        return &box->pub;
    } catch (...) {
        return nullptr;
    }
}

BinResult* bin_lookup_id(const BinDict* dict, uint32_t bin_id) {
    if (!dict) {
        return nullptr;
    }
    try {
        std::vector<Entry> entries;
        dict->lookup_id(bin_id, entries);
        return make_result(std::move(entries));
    } catch (...) {
        return nullptr;
    }
}

BinStrings* bin_lemma_forms(const BinDict* dict, uint32_t bin_id) {
    if (!dict) {
        return nullptr;
    }
    try {
        return make_strings(dict->lemma_forms(bin_id));
    } catch (...) {
        return nullptr;
    }
}

BinLemma* bin_lemma(const BinDict* dict, uint32_t bin_id) {
    if (!dict) {
        return nullptr;
    }
    try {
        std::unique_ptr<LemmaBox> box(new LemmaBox);
        if (!dict->lemma(bin_id, box->rec)) {
            return nullptr;
        }
        box->pub.lemma = box->rec.lemma.c_str();
        box->pub.hluti = dict->subcat(box->rec.subcat_index).c_str();
        box->pub.dropped = box->rec.dropped ? 1 : 0;
        box->pub.ksnid_index = box->rec.ksnid_index;
        box->pub.heads = box->rec.heads.empty() ? nullptr : box->rec.heads.data();
        box->pub.num_heads = (uint32_t)box->rec.heads.size();
        return &box.release()->pub;
    } catch (...) {
        return nullptr;
    }
}

void bin_lemma_free(BinLemma* lemma) { delete reinterpret_cast<LemmaBox*>(lemma); }

BinStrings* bin_meaning(const BinDict* dict, uint32_t meaning_index) {
    if (!dict) {
        return nullptr;
    }
    try {
        std::vector<std::string> items(2);
        dict->meaning(meaning_index, items[0], items[1]);
        return make_strings(std::move(items));
    } catch (...) {
        return nullptr;
    }
}

char* bin_ksnid_string(const BinDict* dict, uint32_t ksnid_index) {
    if (!dict) {
        return nullptr;
    }
    try {
        std::string s = dict->ksnid_string(ksnid_index);
        char* result = new (std::nothrow) char[s.size() + 1];
        if (result) {
            memcpy(result, s.c_str(), s.size() + 1);
        }
        return result;
    } catch (...) {
        return nullptr;
    }
}

// ---- Compounds ----

BinSplits* bin_compound_candidates(const BinDict* dict, const char* word) {
    if (!dict || !word) {
        return nullptr;
    }
    try {
        return make_splits(dict->compound_candidates(word));
    } catch (...) {
        return nullptr;
    }
}

BinSplits* bin_compound_split(const BinDict* dict, const char* word) {
    if (!dict || !word) {
        return nullptr;
    }
    try {
        std::vector<std::string> split = dict->compound_split(word);
        if (split.empty()) {
            return nullptr;
        }
        std::vector<std::vector<std::string>> splits;
        splits.push_back(std::move(split));
        return make_splits(std::move(splits));
    } catch (...) {
        return nullptr;
    }
}

BinResult* bin_compound_lookup(const BinDict* dict, const char* word, const BinCompoundOptions* options) {
    if (!dict || !word) {
        return nullptr;
    }
    try {
        BinCompoundOptions opts = {1, 0, 1};
        if (options) {
            opts = *options;
        }
        std::vector<Entry> entries;
        std::string split_word;
        dict->compound_lookup(word, opts.insert_hyphen != 0, opts.nouns_only != 0, opts.try_lowercase != 0, entries,
                              split_word);
        return make_result(std::move(entries), false, split_word);
    } catch (...) {
        return nullptr;
    }
}

// ---- Memory ----

void bin_result_free(BinResult* result) { delete reinterpret_cast<ResultBox*>(result); }

void bin_raw_result_free(BinRawResult* result) { delete reinterpret_cast<RawResultBox*>(result); }

void bin_strings_free(BinStrings* strings) { delete reinterpret_cast<StringsBox*>(strings); }

void bin_splits_free(BinSplits* splits) { delete reinterpret_cast<SplitsBox*>(splits); }

void bin_string_free(char* s) { delete[] s; }

}  // extern "C"
