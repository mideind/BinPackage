#!/usr/bin/env python3
"""

    BinPackage

    Compact BÍN: selection of redundant compound lemmas

    Copyright © 2026 Miðeind ehf.
    Original author: Vilhjálmur Þorsteinsson

    This software is licensed under the MIT License:

        Permission is hereby granted, free of charge, to any person
        obtaining a copy of this software and associated documentation
        files (the "Software"), to deal in the Software without restriction,
        including without limitation the rights to use, copy, modify, merge,
        publish, distribute, sublicense, and/or sell copies of the Software,
        and to permit persons to whom the Software is furnished to do so,
        subject to the following conditions:

        The above copyright notice and this permission notice shall be
        included in all copies or substantial portions of the Software.

        THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
        EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
        MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
        IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
        CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
        TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
        SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

    This module decides which BÍN lemmas a *compact* compressed.bin can
    leave out of its word-form trie without changing what the runtime
    returns. It is driven by tools/binpack.py --compact and works on the
    in-memory structures of a fully read BinCompressor.

    The idea: BÍN lists a great many compounds ('bókahilla') whose
    inflection is exactly that of their last component ('hilla') with the
    other components ('bóka') glued in front. The runtime compounder can
    already split such a word into 'bóka' + 'hilla', so the trie entries of
    'bókahilla' are redundant *provided* that the runtime, given any form
    of 'bókahilla', splits it the same way and can find its way back to
    the original BÍN lemma. A compact file therefore keeps a small record
    per dropped lemma (its bin_id, subcategory, ksnid string and the head
    lemma(s) that regenerate it) and drops only its word forms; see
    binpack.py, BinCompressor.write_binary(), for the layout. The lookup
    code in bincompress.cpp restores the original entries, bin_id
    included, so the compact file is a lossless variant as far as the
    public API is concerned.

    A lemma X (with category ofl) is dropped iff all of the following hold:

    1. ofl is an open word category (noun, adjective or verb) and X is a
       genuine BÍN lemma (bin_id below the Greynir additions).
    2. All entries of X share one ksnid string (the record stores one).
    3. There is a legal multi-part compound split of X's lemma,
       X = P + Z, such that Z is a kept BÍN lemma of the same category and
       paradigm(X) == P + paradigm(Z), form for form and mark for mark.
    4. For every form f of X:
       a. no kept lemma also has f as a form (a trie hit would otherwise
          short-circuit the compounder), and
       b. the runtime rule applied to f (the first ranked legal split whose
          suffix readings reconstruct *any* dropped lemma) reconstructs X
          itself, i.e. it yields a prefix P' with a kept head Z' such that
          X's lemma is P' + Z's lemma and paradigm(X) == P' + paradigm(Z').
          Z' is added to X's heads (a form may split with a different
          prefix than the lemma does).

    Rule 4 depends on the set of dropped lemmas and their heads, so the
    selection iterates: lemmas that fail are put back and the verification
    repeats until nothing changes. The rules mirror bincompress.cpp
    (BinCompressed::compact_lookup) exactly; tools/parity.py is the
    independent check that they do.

"""

from typing import Dict, FrozenSet, List, Optional, Set, Tuple, TYPE_CHECKING

import sys
import time
from collections import defaultdict
import multiprocessing

from islenska.dawgdictionary import Wordbase

if TYPE_CHECKING:
    from binpack import BinCompressor  # type: ignore[import-not-found]

# Word categories whose lemmas may be dropped
OPEN_CATS: FrozenSet[bytes] = frozenset((b"so", b"kk", b"hk", b"kvk", b"lo"))

Paradigm = FrozenSet[Tuple[bytes, int]]  # (form, meaning index)


class DroppedLemma:
    """What the compact file stores about a dropped lemma"""

    __slots__ = ("bin_id", "kix", "heads", "prefix")

    def __init__(self, bin_id: int, kix: int, head: int, prefix: bytes) -> None:
        self.bin_id = bin_id
        # Index of the ksnid string shared by all entries of the lemma
        self.kix = kix
        # Kept lemmas (bin_ids) whose paradigm, with a prefix, regenerates this one
        self.heads: List[int] = [head]
        # The prefix of the lemma-level split (for the report only)
        self.prefix = prefix


# ---------------------------------------------------------------------------
# Module-level state, shared with the worker processes via fork(). The
# 'fork' start method is requested explicitly: since Python 3.14 the
# default on Linux is 'forkserver', whose workers do not inherit it.

_mp = multiprocessing.get_context("fork")

_b: Optional["BinCompressor"] = None
_lemma_ofl: Dict[int, bytes] = {}
_by_lemma: Dict[Tuple[bytes, bytes], List[int]] = {}
_owners: Dict[int, List[int]] = {}  # form index -> lemma bin_ids
_form_index: Dict[bytes, int] = {}
_paradigms: Dict[int, Paradigm] = {}
_min_greynir: int = 0
# The current removal state
_dropped: Dict[int, DroppedLemma] = {}
_dropped_by_lemma: Dict[bytes, List[int]] = {}


def _paradigm(bid: int) -> Paradigm:
    p = _paradigms.get(bid)
    if p is None:
        assert _b is not None
        e = _b._lemma_entries[bid]
        forms = _b._form_list
        p = frozenset((forms[e[i]], e[i + 1]) for i in range(0, len(e), 3))
        _paradigms[bid] = p
    return p


def _candidates(word: bytes) -> List[List[bytes]]:
    """Legal multi-part splits of word in the runtime's ranking order"""
    try:
        cands = Wordbase.slice_compound_word_candidates(word.decode("latin-1"))
    except Exception:
        return []
    return [
        [p.encode("latin-1") for p in c] for c in cands if len(c) > 1
    ]


def _same_paradigm_head(bid: int, prefix: bytes) -> int:
    """Return a kept lemma Z of X's category such that
    lemma(X) == prefix + lemma(Z) and paradigm(X) == prefix + paradigm(Z),
    or 0 if there is none"""
    assert _b is not None
    lemma, _ = _b._lemmas[bid]
    if not lemma.startswith(prefix) or len(prefix) >= len(lemma):
        return 0
    zs = _by_lemma.get((lemma[len(prefix) :], _lemma_ofl[bid]))
    if not zs:
        return 0
    lp = len(prefix)
    px = _paradigm(bid)
    if not all(form.startswith(prefix) for form, _ in px):
        return 0
    xs: Paradigm = frozenset((form[lp:], mix) for form, mix in px)
    for z in zs:
        if z != bid and z not in _dropped and z < _min_greynir and xs == _paradigm(z):
            return z
    return 0


def _check_lemma(bid: int) -> Tuple[int, int, bytes]:
    """Rules 1-3: does X = P + Z for some kept Z with an identical paradigm?
    Returns (bid, Z, P) or (bid, 0, b'')."""
    assert _b is not None
    lemma, _ = _b._lemmas[bid]
    for c in _candidates(lemma):
        prefix = b"".join(c[:-1])
        z = _same_paradigm_head(bid, prefix)
        if z:
            return (bid, z, prefix)
    return (bid, 0, b"")


def _runtime_hits(form: bytes) -> Tuple[Set[Tuple[int, int]], Optional[bytes], bool]:
    """Model BinCompressed::compact_lookup(): return the set of
    (dropped bin_id, head bin_id) that the runtime reconstructs for a
    form that is not in the compact trie, from the first ranked legal
    split that reconstructs anything, the prefix of that split, and
    whether the form has a trie reading of its own (a kept owner)."""
    assert _b is not None
    fix = _form_index.get(form)
    if fix is not None and any(o not in _dropped for o in _owners[fix]):
        return set(), None, True
    for c in _candidates(form):
        prefix = b"".join(c[:-1])
        sfix = _form_index.get(c[-1])
        if sfix is None:
            continue
        hits: Set[Tuple[int, int]] = set()
        for z in _owners[sfix]:
            if z in _dropped:
                continue
            zl, _ = _b._lemmas[z]
            for x in _dropped_by_lemma.get(prefix + zl, ()):
                if z in _dropped[x].heads:
                    hits.add((x, z))
        if hits:
            return hits, prefix, False
    return set(), None, False


def _verify_lemma(bid: int) -> Tuple[int, bool, List[int]]:
    """Rule 4 for every form of X, against the current removal state.
    Returns (bid, ok, additional heads found)."""
    assert _b is not None
    e = _b._lemma_entries[bid]
    forms = _b._form_list
    heads = _dropped[bid].heads
    new_heads: List[int] = []
    checked: Set[bytes] = set()
    for i in range(0, len(e), 3):
        f = forms[e[i]]
        if f in checked:
            continue
        checked.add(f)
        hits, prefix, kept_owner = _runtime_hits(f)
        if kept_owner:
            # Rule 4a: a kept lemma owns this form too
            return (bid, False, [])
        if any(x == bid for x, _ in hits):
            # Reconstructed through a head we already know
            continue
        # Not reconstructed with the current heads. The runtime settles on
        # the first split that reconstructs anything, so X must become
        # reconstructible from that very split; if no split reconstructs
        # anything yet, the first split with a valid head for X will win.
        prefixes = [prefix] if prefix is not None else [
            b"".join(c[:-1]) for c in _candidates(f)
        ]
        z = 0
        for p in prefixes:
            z = _same_paradigm_head(bid, p)
            if z:
                break
        if not z:
            return (bid, False, [])
        if z not in heads and z not in new_heads:
            new_heads.append(z)
    return (bid, True, new_heads)


def select(
    b: "BinCompressor", procs: int = 4, keep: Optional[Set[int]] = None
) -> Dict[int, DroppedLemma]:
    """Select the lemmas to drop from a compact build of the given,
    fully read, BinCompressor. Returns a dictionary of bin_id -> DroppedLemma.
    Lemmas in the keep set are never dropped."""
    global _b, _lemma_ofl, _by_lemma, _owners, _form_index, _paradigms
    global _min_greynir, _dropped, _dropped_by_lemma
    _b = b
    keep = keep or set()
    t0 = time.time()
    _min_greynir = b._begin_greynir_utg or (b._max_bin_id + 1)
    _form_index = {f: ix for ix, f in enumerate(b._form_list)}
    _owners = {
        fix: sorted({wix for wix, _, _ in entries})
        for fix, entries in b._lookup_form.items()
    }
    _lemma_ofl = {}
    _by_lemma = defaultdict(list)
    for bid, (lemma, _) in b._lemmas.items():
        e = b._lemma_entries[bid]
        ofl = b._meanings[e[1]][0]
        _lemma_ofl[bid] = ofl
        _by_lemma[(lemma, ofl)].append(bid)
    _paradigms = {}
    print(f"compact: indexed {len(b._lemmas):,} lemmas ({time.time() - t0:.0f}s)")

    # Candidate lemmas: rules 1 and 2
    t0 = time.time()
    cands: List[int] = []
    for bid in b._lemmas:
        if bid >= _min_greynir or bid in keep or _lemma_ofl[bid] not in OPEN_CATS:
            continue
        e = b._lemma_entries[bid]
        kix = e[2]
        if any(e[i] != kix for i in range(5, len(e), 3)):
            # Rule 2: not a single ksnid string
            continue
        cands.append(bid)
    # Round 1: rule 3
    _dropped = {}
    _dropped_by_lemma = {}
    with _mp.Pool(procs) as pool:
        r1 = pool.map(_check_lemma, cands, chunksize=2000)
    for bid, z, prefix in r1:
        if z:
            _dropped[bid] = DroppedLemma(bid, b._lemma_entries[bid][2], z, prefix)
    _rebuild_lemma_index()
    print(
        f"compact: round 1: {len(cands):,} candidates, {len(_dropped):,} have an "
        f"identical-paradigm head ({time.time() - t0:.0f}s)"
    )
    # Rounds 2+: rule 4, to a fixpoint
    rnd = 1
    while True:
        rnd += 1
        t0 = time.time()
        with _mp.Pool(procs) as pool:
            ver = pool.map(_verify_lemma, sorted(_dropped), chunksize=1000)
        failed = 0
        added = 0
        for bid, ok, new_heads in ver:
            if not ok:
                del _dropped[bid]
                failed += 1
            elif new_heads:
                _dropped[bid].heads.extend(new_heads)
                added += len(new_heads)
        _rebuild_lemma_index()
        print(
            f"compact: round {rnd}: {failed:,} lemmas put back, {added:,} heads added, "
            f"{len(_dropped):,} remain ({time.time() - t0:.0f}s)"
        )
        if not failed and not added:
            break
    # Heads recorded in round 1 may themselves have been dropped since;
    # the runtime never sees readings of dropped lemmas, so prune them.
    # The verification guarantees at least one kept head per lemma.
    for d in _dropped.values():
        d.heads = [z for z in d.heads if z not in _dropped]
        assert d.heads, f"dropped lemma {d.bin_id} has no kept head"
    return _dropped


def _rebuild_lemma_index() -> None:
    global _dropped_by_lemma
    assert _b is not None
    d: Dict[bytes, List[int]] = defaultdict(list)
    for bid in _dropped:
        d[_b._lemmas[bid][0]].append(bid)
    _dropped_by_lemma = dict(d)


def write_report(b: "BinCompressor", dropped: Dict[int, DroppedLemma], fname: str) -> None:
    """Write a tab-separated listing of the dropped lemmas"""
    with open(fname, "w", encoding="utf-8") as f:
        f.write("bin_id\tlemma\tofl\tprefix\thead_bin_ids\thead_lemmas\n")
        for bid in sorted(dropped, key=lambda x: b._lemmas[x][0]):
            d = dropped[bid]
            lemma = b._lemmas[bid][0].decode("latin-1")
            heads = ",".join(str(z) for z in d.heads)
            head_lemmas = ",".join(b._lemmas[z][0].decode("latin-1") for z in d.heads)
            f.write(
                f"{bid}\t{lemma}\t{_lemma_ofl[bid].decode('latin-1')}\t"
                f"{d.prefix.decode('latin-1')}\t{heads}\t{head_lemmas}\n"
            )


def read_keep_list(fname: str) -> Set[int]:
    """Read a file of bin_ids (one per line, '#' comments allowed)
    that must never be dropped"""
    keep: Set[int] = set()
    with open(fname, "r", encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if line:
                keep.add(int(line.split()[0]))
    return keep


if __name__ == "__main__":
    print("This module is used by tools/binpack.py --compact", file=sys.stderr)
    sys.exit(1)
