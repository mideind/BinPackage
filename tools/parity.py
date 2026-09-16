#!/usr/bin/env python3
"""

    BinPackage

    Parity check between two compressed.bin files

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

    This program checks that a compact compressed.bin (tools/binpack.py
    --compact) answers every query exactly as the full file does. It is
    the independent check of the compactor's model of the runtime
    (tools/compact.py): the compactor decides what to drop, this program
    proves that nothing was lost.

    The checks, for every word form in the source data (or a random sample):

      - BinCompressed.lookup_ksnid(form): the raw entries, with bin_id,
        subcategory and the additional KRISTINsnid fields
      - BinCompressed.contains(form)
      - Bin.lookup(form) and Bin.lookup(form.capitalize()): the public API,
        including the compounder, case handling and the other heuristics

    and, for every bin_id:

      - BinCompressed.lookup_id(bin_id) and lemma_forms(bin_id)

    Usage:

        python tools/parity.py FULL.bin COMPACT.bin [--sample N] [--procs P]
            [--keep-out FILE]

    The exit status is nonzero if any difference is found. --keep-out writes
    the bin_ids involved in the differences to a file that can be passed
    to binpack.py --compact --keep, so that a rebuild keeps those lemmas.

"""

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import argparse
import os
import random
import sys
import time
import multiprocessing

basepath, _ = os.path.split(os.path.realpath(__file__))
if basepath.endswith(os.sep + "tools"):
    basepath = basepath[0:-6]
    sys.path.append(basepath)

from islenska.basics import LFU_Cache, Ksnid  # noqa: E402
from islenska.bincompress import BinCompressed  # noqa: E402
from islenska.bindb import Bin, CACHE_SIZE_MEANINGS  # noqa: E402

RESOURCES = os.path.join(basepath, "src", "islenska", "resources")
SOURCE_FILES = [
    "KRISTINsnid.csv",
    "ord.add.csv",
    "ord.auka.csv",
    "systematic_additions.csv",
    "ord.suffixes.csv",
]

KsnidKey = Tuple[str, int, str, str, str, str, str]


def ksnid_key(k: Ksnid) -> KsnidKey:
    return (k.ord, k.bin_id, k.ofl, k.hluti, k.bmynd, k.mark, k.ksnid_string)


def read_forms(fnames: Iterable[str]) -> List[str]:
    """Collect the distinct word forms from the source CSV files"""
    forms: Set[str] = set()
    for fname in fnames:
        with open(fname, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line[0] == "#":
                    continue
                t = line.split(";")
                if len(t) == 6:
                    forms.add(t[4])
                elif len(t) >= 11:
                    forms.add(t[9])
    return sorted(forms)


# ---------------------------------------------------------------------------
# Worker state (forked)

_full: Optional[BinCompressed] = None
_compact: Optional[BinCompressed] = None
_full_bin: Optional[Bin] = None
_compact_bin: Optional[Bin] = None


def _init(full_path: str, compact_path: str) -> None:
    global _full, _compact, _full_bin, _compact_bin
    _full = BinCompressed(full_path)
    _compact = BinCompressed(compact_path)

    # Two independent Bin instances: each subclass gets its own
    # singleton dictionary and its own cache
    class FullBin(Bin):
        _bc = _full
        _ksnid_cache: LFU_Cache[str, List[Ksnid]] = LFU_Cache(maxsize=CACHE_SIZE_MEANINGS)

    class CompactBin(Bin):
        _bc = _compact
        _ksnid_cache: LFU_Cache[str, List[Ksnid]] = LFU_Cache(maxsize=CACHE_SIZE_MEANINGS)

    _full_bin = FullBin()
    _compact_bin = CompactBin()


# A difference: (key, check, full result, compact result, bin_ids involved)
Diff = Tuple[str, str, str, str, List[int]]


def _check_forms(forms: List[str]) -> List[Diff]:
    """Return the differences found for the given forms"""
    assert _full is not None and _compact is not None
    assert _full_bin is not None and _compact_bin is not None
    diffs: List[Diff] = []
    for form in forms:
        fa = _full.lookup_ksnid(form)
        ids = [k.bin_id for k in fa]
        a = sorted(ksnid_key(k) for k in fa)
        b = sorted(ksnid_key(k) for k in _compact.lookup_ksnid(form))
        if a != b:
            diffs.append((form, "lookup_ksnid", repr(a), repr(b), ids))
        ca = _full.contains(form)
        cb = _compact.contains(form)
        if ca != cb:
            diffs.append((form, "contains", repr(ca), repr(cb), ids))
        for w in (form, form.capitalize()):
            wa, ma = _full_bin.lookup(w)
            wb, mb = _compact_bin.lookup(w)
            if wa != wb or sorted(ma) != sorted(mb):
                diffs.append(
                    (w, "Bin.lookup", repr((wa, sorted(ma))), repr((wb, sorted(mb))),
                     ids + [m.bin_id for m in ma])
                )
    return diffs


def _check_ids(ids: List[int]) -> List[Diff]:
    assert _full is not None and _compact is not None
    diffs: List[Diff] = []
    for bin_id in ids:
        a = sorted(ksnid_key(k) for k in _full.lookup_id(bin_id))
        b = sorted(ksnid_key(k) for k in _compact.lookup_id(bin_id))
        if a != b:
            diffs.append((str(bin_id), "lookup_id", repr(a), repr(b), [bin_id]))
        fa = sorted(_full.lemma_forms(bin_id))
        fb = sorted(_compact.lemma_forms(bin_id))
        if fa != fb:
            diffs.append((str(bin_id), "lemma_forms", repr(fa), repr(fb), [bin_id]))
    return diffs


def chunks(items: List[Any], n: int) -> List[List[Any]]:
    return [items[i : i + n] for i in range(0, len(items), n)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check a compact compressed.bin against the full one")
    parser.add_argument("full", help="the full compressed.bin")
    parser.add_argument("compact", help="the compact compressed.bin")
    parser.add_argument("--sample", type=int, default=0, help="check a random sample of N forms and ids")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--procs", type=int, default=max(1, min(8, os.cpu_count() or 1)))
    parser.add_argument("--forms", metavar="FILE", help="read the forms to check from FILE (one per line)")
    parser.add_argument("--keep-out", metavar="FILE", help="write the bin_ids involved in differences to FILE")
    parser.add_argument("--show", type=int, default=20, help="number of differences to print")
    args = parser.parse_args()

    t0 = time.time()
    if args.forms:
        with open(args.forms, "r", encoding="utf-8") as f:
            forms = [line.rstrip("\n") for line in f if line.strip()]
    else:
        forms = read_forms(os.path.join(RESOURCES, name) for name in SOURCE_FILES)
    full = BinCompressed(args.full)
    compact = BinCompressed(args.compact)
    print(
        f"{args.full}: {os.path.getsize(args.full):,} bytes"
        f"{' (compact)' if full.is_compact else ''}; "
        f"{args.compact}: {os.path.getsize(args.compact):,} bytes"
        f"{' (compact)' if compact.is_compact else ''}"
    )
    ids = list(range(1, full._max_bin_id + 1))
    full.close()
    compact.close()
    if args.sample:
        rnd = random.Random(args.seed)
        forms = rnd.sample(forms, min(args.sample, len(forms)))
        ids = rnd.sample(ids, min(args.sample, len(ids)))
    print(f"Checking {len(forms):,} forms and {len(ids):,} bin_ids with {args.procs} processes")

    diffs: List[Diff] = []
    with multiprocessing.get_context("fork").Pool(
        args.procs, initializer=_init, initargs=(args.full, args.compact)
    ) as pool:
        for d in pool.imap_unordered(_check_forms, chunks(forms, 2000)):
            diffs.extend(d)
        for d in pool.imap_unordered(_check_ids, chunks(ids, 2000)):
            diffs.extend(d)
    print(f"Done in {time.time() - t0:.0f}s: {len(diffs):,} differences")

    by_check: Dict[str, int] = {}
    for _, check, _, _, _ in diffs:
        by_check[check] = by_check.get(check, 0) + 1
    for check, n in sorted(by_check.items()):
        print(f"  {check}: {n:,}")
    for key, check, a, b, _ in diffs[: args.show]:
        print(f"\n{check}({key!r}):\n  full:    {a}\n  compact: {b}")

    if args.keep_out:
        keep: Set[int] = set()
        for _, _, _, _, ids in diffs:
            keep.update(i for i in ids if i)
        with open(args.keep_out, "w", encoding="utf-8") as f:
            for bin_id in sorted(keep):
                f.write(f"{bin_id}\n")
        print(f"Wrote {len(keep)} bin_ids to {args.keep_out}")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
