/*

   BinPackage

   libbin: the compressed BÍN dictionary

   Copyright © 2026 Miðeind ehf.
   Original author: Vilhjálmur Þorsteinsson

   This software is licensed under the MIT License; see bin.h.

   The file layout is described in tools/binpack.py. In short:

      header       16-byte signature, then uint32 offsets of the mappings,
                   forms, lemmas, templates, meanings, alphabet, subcats
                   and ksnid sections, the first Greynir bin_id, the
                   highest bin_id, and the offset of the compact section
                   (0 unless this is a compact build)
      mappings     for each word form, its readings as packed 32-bit words
      forms        the radix trie (trie.cpp)
      lemmas       a bin_id-indexed table of record offsets; a record is a
                   flag/subcategory word, the lemma string, and either a
                   template offset (kept lemmas with inflected forms) or
                   the ksnid index and the head bin_ids (dropped lemmas)
      templates    differential encodings of sets of inflected forms
      meanings     an index of "ofl mark" strings
      ksnid        an index of the additional KRISTINsnid field strings
      subcats      the subcategory (fl) strings
      compact      the bin_ids of the dropped lemmas, sorted by lemma

   Compact restoration: a word form that is not in the trie is sliced by
   the compounder into prefix + suffix. Each reading of the suffix form
   belongs to a lemma Z; if prefix + Z's lemma is a dropped lemma X that
   lists Z among its heads, the form is a form of X, with the suffix
   reading's inflection and X's own bin_id, subcategory and ksnid string.
   The first split in ranking order that restores anything wins, exactly
   as modelled by tools/compact.py when the file was built.

*/

#include <string.h>

#include <algorithm>
#include <set>
#include <stdexcept>
#include <utility>

#include "dict.h"
#include "trie.h"

namespace libbin {

namespace {

const char* SIGNATURE = "Greynir 05.00.00";

const uint32_t BIN_ID_BITS = 20;
const uint32_t BIN_ID_MASK = (1u << BIN_ID_BITS) - 1;
const uint32_t MEANING_MASK = (1u << 10) - 1;
const uint32_t KSNID_BITS = 14;
const uint32_t KSNID_MASK = (1u << KSNID_BITS) - 1;
const uint32_t SUBCAT_MASK = (1u << 8) - 1;
const uint32_t COMMON_KIX_0 = 0;
const uint32_t COMMON_KIX_1 = 1;
const uint32_t LEMMA_HAS_TEMPLATE = 0x80000000u;
const uint32_t LEMMA_DROPPED = 0x40000000u;

}  // namespace

uint32_t Dict::at(uint32_t offset) const { return at(m_map + offset); }

uint32_t Dict::at(const uint8_t* p) const {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

Dict::Dict(const uint8_t* map, size_t len, const Dawg* all, const Dawg* prefixes, const Dawg* suffixes)
    : m_map(map),
      m_len(len),
      m_compact_ids(nullptr),
      m_compact_count(0),
      m_all(all),
      m_prefixes(prefixes),
      m_suffixes(suffixes) {
    if (!map || len < 60 || memcmp(map, SIGNATURE, 16) != 0) {
        throw std::runtime_error("Not a BinPackage compressed.bin of version " + std::string(SIGNATURE));
    }
    m_mappings = map + at(16);
    m_lemmas = map + at(24);
    m_templates = map + at(28);
    m_meanings = map + at(32);
    uint32_t subcats_offset = at(40);
    m_ksnid = map + at(44);
    m_begin_greynir_utg = at(48);
    m_max_bin_id = at(52);
    m_compact_offset = at(56);
    if (m_compact_offset) {
        m_compact_count = at(m_compact_offset);
        m_compact_ids = map + m_compact_offset + 4;
    }
    // The subcategory strings, space-separated
    uint32_t n = at(subcats_offset);
    const char* p = (const char*)(map + subcats_offset + 4);
    const char* end = p + n;
    while (p < end) {
        while (p < end && *p == ' ') {
            p++;
        }
        const char* start = p;
        while (p < end && *p != ' ') {
            p++;
        }
        if (p > start) {
            m_subcats.emplace_back(start, p - start);
        }
    }
    if (m_subcats.empty()) {
        m_subcats.emplace_back("");
    }
}

// ---- Tables ----

uint32_t Dict::lemma_offset(uint32_t bin_id) const {
    if (bin_id > m_max_bin_id) {
        return 0;
    }
    return at(m_lemmas + bin_id * 4);
}

void Dict::lemma_string(uint32_t offset, std::string& out) const {
    const uint8_t* p = m_map + offset + 4;
    out.assign((const char*)p + 1, p[0]);
}

bool Dict::lemma(uint32_t bin_id, LemmaRecord& out) const {
    uint32_t off = lemma_offset(bin_id);
    if (!off) {
        return false;
    }
    uint32_t bits = at(off);
    out.subcat_index = bits & SUBCAT_MASK;
    out.has_template = (bits & LEMMA_HAS_TEMPLATE) != 0;
    out.dropped = (bits & LEMMA_DROPPED) != 0;
    out.template_offset = 0;
    out.ksnid_index = 0;
    out.heads.clear();
    // The lemma string is length-prefixed and padded to 32 bits
    uint32_t p = off + 4;
    uint32_t lw = m_map[p];
    out.lemma.assign((const char*)m_map + p + 1, lw);
    p += ((lw + 1) + 3) & ~3u;
    if (out.dropped) {
        uint32_t w = at(p);
        out.ksnid_index = w & 0xFFFF;
        uint32_t num_heads = w >> 16;
        p += 4;
        out.heads.reserve(num_heads);
        for (uint32_t i = 0; i < num_heads; i++, p += 4) {
            out.heads.push_back(at(p));
        }
    } else if (out.has_template) {
        out.template_offset = at(p);
    }
    return true;
}

void Dict::meaning(uint32_t ix, std::string& ofl, std::string& mark) const {
    uint32_t off = at(m_meanings + ix * 4);
    // "ofl mark", space-terminated, within 24 bytes
    const char* p = (const char*)(m_map + off);
    const char* end = p + 24;
    const char* q = p;
    while (q < end && *q != ' ') {
        q++;
    }
    ofl.assign(p, q - p);
    if (q < end) {
        q++;
    }
    const char* r = q;
    while (r < end && *r != ' ') {
        r++;
    }
    mark.assign(q, r - q);
}

std::string Dict::ksnid_string(uint32_t ix) const {
    uint32_t off = at(m_ksnid + ix * 4);
    uint32_t lw = m_map[off];
    return std::string((const char*)m_map + off + 1, lw);
}

std::vector<std::string> Dict::template_forms(const LemmaRecord& rec) const {
    std::vector<std::string> result;
    if (!rec.has_template) {
        result.push_back(rec.lemma);
        return result;
    }
    // Differential decoding, see compress_set() in tools/binpack.py:
    // each form is the previous one with 'cut' characters removed from the
    // end and 'len' characters appended
    std::string last = rec.lemma;
    const uint8_t* p = m_templates + rec.template_offset;
    for (;;) {
        uint8_t b = *p++;
        if (b == 0) {
            break;
        }
        size_t cut;
        size_t n;
        if (b & 0x80) {
            cut = b & 0x7F;
            n = *p++;
        } else {
            int diff = (int)(b & 0x03) - (int)(b & 0x04);
            cut = b >> 3;
            int len_signed = (int)cut + diff;
            if (len_signed < 0) {
                break;  // Corrupt data
            }
            n = (size_t)len_signed;
        }
        if (cut > last.size()) {
            break;  // Corrupt data
        }
        last.resize(last.size() - cut);
        last.append((const char*)p, n);
        p += n;
        result.push_back(last);
    }
    result.push_back(rec.lemma);
    return result;
}

std::vector<std::string> Dict::lemma_forms(uint32_t bin_id) const {
    LemmaRecord rec;
    if (!lemma(bin_id, rec)) {
        return {};
    }
    if (!rec.dropped) {
        return template_forms(rec);
    }
    // A dropped compound: its forms are those of its first head, with the
    // prefix (the lemma minus the head's lemma) in front
    LemmaRecord head;
    if (rec.heads.empty() || !lemma(rec.heads[0], head) || head.lemma.size() >= rec.lemma.size()) {
        return {};
    }
    std::string prefix = rec.lemma.substr(0, rec.lemma.size() - head.lemma.size());
    std::vector<std::string> forms = template_forms(head);
    for (auto& f : forms) {
        f.insert(0, prefix);
    }
    return forms;
}

// ---- Raw lookups ----

void Dict::decode_mappings(uint32_t index, std::vector<RawEntry>& out) const {
    uint32_t bin_id = 0;
    for (;;) {
        uint32_t w0 = at(m_mappings + (size_t)index * 4);
        index++;
        RawEntry e;
        if ((w0 & 0x60000000u) == 0x60000000u) {
            // Single packed word: common ksnid string, 8-bit meaning index
            e.meaning_index = ((w0 >> BIN_ID_BITS) & 0xFF) - 1;
            bin_id = w0 & BIN_ID_MASK;
            e.ksnid_index = (w0 & 0x10000000u) ? COMMON_KIX_1 : COMMON_KIX_0;
        } else if ((w0 & 0x60000000u) == 0x40000000u) {
            // Single word, same bin_id as the previous entry
            e.meaning_index = (w0 >> KSNID_BITS) & MEANING_MASK;
            e.ksnid_index = w0 & KSNID_MASK;
        } else {
            // Two words
            bin_id = w0 & BIN_ID_MASK;
            uint32_t w1 = at(m_mappings + (size_t)index * 4);
            index++;
            e.meaning_index = (w1 >> KSNID_BITS) & MEANING_MASK;
            e.ksnid_index = w1 & KSNID_MASK;
        }
        e.bin_id = bin_id;
        out.push_back(e);
        if (w0 & 0x80000000u) {
            break;
        }
    }
}

bool Dict::trie_contains(const std::string& word) const {
    return libbin::trie_lookup(m_map, (const uint8_t*)word.c_str()) != TRIE_NOT_FOUND;
}

void Dict::trie_lookup(const std::string& word, std::vector<RawEntry>& out) const {
    uint32_t index = libbin::trie_lookup(m_map, (const uint8_t*)word.c_str());
    if (index != TRIE_NOT_FOUND) {
        decode_mappings(index, out);
    }
}

// ---- Compact restoration ----

void Dict::compact_find(const std::string& lemma_str, std::vector<uint32_t>& out) const {
    // Binary search the sorted bin_ids by lemma string (unsigned byte order)
    std::string s;
    uint32_t lo = 0;
    uint32_t hi = m_compact_count;
    while (lo < hi) {
        uint32_t mid = lo + (hi - lo) / 2;
        uint32_t bin_id = at(m_compact_ids + (size_t)mid * 4);
        lemma_string(lemma_offset(bin_id), s);
        if (s < lemma_str) {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }
    for (uint32_t i = lo; i < m_compact_count; i++) {
        uint32_t bin_id = at(m_compact_ids + (size_t)i * 4);
        lemma_string(lemma_offset(bin_id), s);
        if (s != lemma_str) {
            break;
        }
        out.push_back(bin_id);
    }
}

void Dict::compact_lookup(const std::string& word, std::vector<RawEntry>& out) const {
    if (!is_compact() || !has_dawgs()) {
        return;
    }
    std::vector<std::vector<std::string>> cands = compound_candidates(word);
    std::vector<RawEntry> raw;
    std::vector<uint32_t> xs;
    LemmaRecord z_rec;
    LemmaRecord x_rec;
    std::set<std::pair<uint32_t, uint32_t>> seen;
    for (const auto& parts : cands) {
        if (parts.size() < 2) {
            continue;
        }
        std::string prefix;
        for (size_t i = 0; i + 1 < parts.size(); i++) {
            prefix += parts[i];
        }
        raw.clear();
        trie_lookup(parts.back(), raw);
        size_t before = out.size();
        for (const RawEntry& r : raw) {
            if (!lemma(r.bin_id, z_rec)) {
                continue;
            }
            xs.clear();
            compact_find(prefix + z_rec.lemma, xs);
            for (uint32_t x : xs) {
                if (!lemma(x, x_rec) || !x_rec.dropped) {
                    continue;
                }
                if (std::find(x_rec.heads.begin(), x_rec.heads.end(), r.bin_id) == x_rec.heads.end()) {
                    continue;
                }
                if (!seen.insert(std::make_pair(x, r.meaning_index)).second) {
                    continue;
                }
                RawEntry e;
                e.bin_id = x;
                e.meaning_index = r.meaning_index;
                e.ksnid_index = x_rec.ksnid_index;
                out.push_back(e);
            }
        }
        if (out.size() > before) {
            // The first split that restores anything wins
            return;
        }
    }
}

bool Dict::contains(const std::string& word) const {
    if (trie_contains(word)) {
        return true;
    }
    if (!is_compact()) {
        return false;
    }
    std::vector<RawEntry> out;
    compact_lookup(word, out);
    return !out.empty();
}

void Dict::raw_lookup(const std::string& word, std::vector<RawEntry>& out) const {
    trie_lookup(word, out);
    if (out.empty() && is_compact()) {
        compact_lookup(word, out);
    }
}

// ---- Decoded lookups ----

void Dict::make_entry(const RawEntry& raw, const std::string& form, Entry& out) const {
    LemmaRecord rec;
    if (lemma(raw.bin_id, rec)) {
        out.ord = rec.lemma;
        out.hluti = subcat(rec.subcat_index);
    } else {
        out.ord.clear();
        out.hluti.clear();
    }
    out.bin_id = raw.bin_id;
    meaning(raw.meaning_index, out.ofl, out.mark);
    out.bmynd = form;
    out.ksnid = ksnid_string(raw.ksnid_index);
}

void Dict::lookup(const std::string& word, const char* cat, const char* lemma_filter,
                  uint32_t bin_id_filter, std::vector<Entry>& out) const {
    std::vector<RawEntry> raw;
    raw_lookup(word, raw);
    bool cat_is_no = cat && strcmp(cat, "no") == 0;
    Entry e;
    for (const RawEntry& r : raw) {
        if (bin_id_filter && r.bin_id != bin_id_filter) {
            continue;
        }
        make_entry(r, word, e);
        if (cat) {
            if (cat_is_no) {
                if (e.ofl != "kk" && e.ofl != "kvk" && e.ofl != "hk") {
                    continue;
                }
            } else if (e.ofl != cat) {
                continue;
            }
        }
        if (lemma_filter && e.ord != lemma_filter) {
            continue;
        }
        out.push_back(e);
    }
}

void Dict::lookup_id(uint32_t bin_id, std::vector<Entry>& out) const {
    LemmaRecord rec;
    if (!lemma(bin_id, rec)) {
        return;
    }
    std::vector<RawEntry> raw;
    Entry e;
    if (!rec.dropped) {
        // The forms of a lemma are distinct, and so are the readings of a
        // form, so no duplicate elimination is needed here
        for (const std::string& form : template_forms(rec)) {
            raw.clear();
            trie_lookup(form, raw);
            for (const RawEntry& r : raw) {
                if (r.bin_id != bin_id) {
                    continue;
                }
                make_entry(r, form, e);
                out.push_back(e);
            }
        }
        return;
    }
    // A dropped compound: derive its entries from its first head
    LemmaRecord head;
    if (rec.heads.empty() || !lemma(rec.heads[0], head) || head.lemma.size() >= rec.lemma.size()) {
        return;
    }
    uint32_t z = rec.heads[0];
    std::string prefix = rec.lemma.substr(0, rec.lemma.size() - head.lemma.size());
    std::string ksnid = ksnid_string(rec.ksnid_index);
    const std::string& hluti = subcat(rec.subcat_index);
    // The head may have several readings with the same form and mark that
    // differ only in their ksnid strings (e.g. a BÍN row and a Greynir
    // addition); the dropped lemma has a single ksnid string, so those
    // collapse into one entry, exactly as in compact_lookup()
    std::set<std::pair<std::string, uint32_t>> seen;
    for (const std::string& form : template_forms(head)) {
        raw.clear();
        trie_lookup(form, raw);
        for (const RawEntry& r : raw) {
            if (r.bin_id != z) {
                continue;
            }
            if (!seen.insert(std::make_pair(form, r.meaning_index)).second) {
                continue;
            }
            e.ord = rec.lemma;
            e.bin_id = bin_id;
            meaning(r.meaning_index, e.ofl, e.mark);
            e.hluti = hluti;
            e.bmynd = prefix + form;
            e.ksnid = ksnid;
            out.push_back(e);
        }
    }
}

// ---- Compound policy ----

std::string Dict::lower(const std::string& s) {
    std::string r = s;
    for (char& c : r) {
        unsigned char u = (unsigned char)c;
        if ((u >= 'A' && u <= 'Z') || (u >= 0xC0 && u <= 0xDE && u != 0xD7)) {
            c = (char)(u + 0x20);
        }
    }
    return r;
}

char Dict::birting(uint32_t ksnid_index) const {
    // The ksnid string is "einkunn;malsnid;malfraedi;millivisun;birting;..."
    std::string k = ksnid_string(ksnid_index);
    size_t pos = 0;
    for (int field = 0; field < 4; field++) {
        pos = k.find(';', pos);
        if (pos == std::string::npos) {
            return '\0';
        }
        pos++;
    }
    return pos < k.size() && k[pos] != ';' ? k[pos] : '\0';
}

bool Dict::standard_filter(const RawEntry& raw, bool compound) const {
    char b = birting(raw.ksnid_index);
    if (b == 'S') {
        return compound;
    }
    return raw.bin_id < m_begin_greynir_utg && b != 'G';
}

namespace {

inline bool is_noun(const std::string& ofl) { return ofl == "kk" || ofl == "kvk" || ofl == "hk"; }

inline bool is_open_cat(const std::string& ofl) {
    return ofl == "so" || ofl == "kk" || ofl == "hk" || ofl == "kvk" || ofl == "lo";
}

}  // namespace

bool Dict::defective_head(const std::string& surface) const {
    // Mirrors Bin._last_part_is_defective() in bindb.py: true iff every
    // noun reading of the surface form belongs to a lemma that lacks
    // either the singular (no 'ET' mark) or the plural (no 'FT' mark).
    // A surface form without noun readings is not defective.
    std::vector<RawEntry> raw;
    raw_lookup(surface, raw);
    std::vector<uint32_t> noun_ids, sg_ids, pl_ids;
    std::string ofl, mark;
    for (const RawEntry& r : raw) {
        if (!r.bin_id || !standard_filter(r, true)) {
            continue;
        }
        meaning(r.meaning_index, ofl, mark);
        if (!is_noun(ofl)) {
            continue;
        }
        noun_ids.push_back(r.bin_id);
        if (mark.find("ET") != std::string::npos) {
            sg_ids.push_back(r.bin_id);
        }
        if (mark.find("FT") != std::string::npos) {
            pl_ids.push_back(r.bin_id);
        }
    }
    if (noun_ids.empty()) {
        return false;
    }
    for (uint32_t id : sg_ids) {
        if (std::find(pl_ids.begin(), pl_ids.end(), id) != pl_ids.end()) {
            // A lemma whose surface entries span both numbers
            return false;
        }
    }
    // Consult the full paradigms
    std::vector<Entry> entries;
    for (uint32_t id : noun_ids) {
        bool has_sg = std::find(sg_ids.begin(), sg_ids.end(), id) != sg_ids.end();
        bool has_pl = std::find(pl_ids.begin(), pl_ids.end(), id) != pl_ids.end();
        entries.clear();
        lookup_id(id, entries);
        for (const Entry& e : entries) {
            has_sg = has_sg || e.mark.find("ET") != std::string::npos;
            has_pl = has_pl || e.mark.find("FT") != std::string::npos;
            if (has_sg && has_pl) {
                return false;
            }
        }
    }
    return true;
}

std::vector<std::string> Dict::compound_split(const std::string& word) const {
    std::vector<std::vector<std::string>> cands = compound_candidates(word);
    for (const auto& c : cands) {
        if (!defective_head(c.back())) {
            return c;
        }
    }
    return cands.empty() ? std::vector<std::string>() : cands[0];
}

void Dict::compound_lookup(const std::string& word, bool insert_hyphen, bool nouns_only, bool try_lowercase,
                           std::vector<Entry>& out, std::string& split_word) const {
    split_word = word;
    std::vector<std::string> cw = compound_split(word);
    if (cw.empty() && try_lowercase) {
        std::string lw = lower(word);
        if (lw != word) {
            cw = compound_split(lw);
            if (!cw.empty()) {
                split_word = lw;
            }
        }
    }
    if (cw.empty()) {
        return;
    }
    std::string prefix;
    for (size_t i = 0; i + 1 < cw.size(); i++) {
        if (insert_hyphen && i > 0) {
            prefix += '-';
        }
        prefix += cw[i];
    }
    bool compound = !prefix.empty();
    if (compound && insert_hyphen) {
        prefix += '-';
    }
    std::vector<RawEntry> raw;
    raw_lookup(cw.back(), raw);
    Entry e;
    for (const RawEntry& r : raw) {
        if (!standard_filter(r, compound)) {
            continue;
        }
        make_entry(r, cw.back(), e);
        if (nouns_only ? !is_noun(e.ofl) : !is_open_cat(e.ofl)) {
            continue;
        }
        if (compound) {
            e.ord.insert(0, prefix);
            e.bmynd.insert(0, prefix);
            e.bin_id = 0;
        }
        out.push_back(e);
    }
}

// ---- Compounds ----

std::vector<std::vector<std::string>> Dict::compound_candidates(const std::string& word) const {
    std::vector<std::vector<std::string>> result;
    if (!has_dawgs() || word.empty()) {
        return result;
    }
    std::vector<std::vector<std::string>> combos = m_all->find_combinations(word);
    if (combos.empty()) {
        return result;
    }
    // Rank: longest last part first, then fewest parts; ties keep the
    // enumeration order (a stable sort, as Wordbase in dawgdictionary.py)
    std::stable_sort(combos.begin(), combos.end(),
                     [](const std::vector<std::string>& a, const std::vector<std::string>& b) {
                         if (a.back().size() != b.back().size()) {
                             return a.back().size() > b.back().size();
                         }
                         return a.size() < b.size();
                     });
    for (auto& c : combos) {
        if (!m_suffixes->contains(c.back())) {
            continue;
        }
        bool ok = true;
        for (size_t i = 0; ok && i + 1 < c.size(); i++) {
            ok = m_prefixes->contains(c[i]);
        }
        if (ok) {
            result.push_back(std::move(c));
        }
    }
    return result;
}

}  // namespace libbin
