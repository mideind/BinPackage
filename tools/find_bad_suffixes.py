#!/usr/bin/env python3
"""

    find_bad_suffixes.py

    Copyright © 2025 Miðeind ehf.

    This software is licensed under the MIT License.

    Identify compound-suffix forms that are not modern, accepted words and so
    make poor inflection-template seeds — e.g. 'ingar' (the NFFT of the poetic
    noun 'ingi'), which otherwise lets a word such as 'byggingar' be sliced as
    'bygg|ingar'.

    A suffix form is flagged when it is present in BÍN and *every* one of its
    direct readings carries a non-modern register mark ('malsnid'):

        SKALD  poetic        GAM   old           URE   obsolete
        FORN   archaic       SJALD rare          VILLA error
        STAD   dialectal     BARN  child language OTOK

    Forms with any modern reading are kept, so words that merely happen to be
    outside the DMII Core (birting='V') — e.g. 'gunnur', 'flanni' — are not
    touched. The flagged forms are written, one per line in sorted order, to
    resources/suffix-removals.txt, which dawgbuilder.py feeds as a removal list
    to the 'ordalisti-suffixes' build.

    Run this after (re)building compressed.bin and before building the DAWGs;
    it requires the 'islenska' package to be importable (e.g. `uv run`).

"""

import os
import sys
import time

basepath, _ = os.path.split(os.path.realpath(__file__))
if basepath.endswith(os.sep + "tools"):
    basepath = basepath[0:-6]
    sys.path.append(basepath)

from islenska import Bin

# Register marks ('malsnid') that indicate a form is not part of the modern,
# accepted vocabulary and therefore a poor compound-suffix (inflection
# template) seed.
NON_MODERN_REGISTERS = frozenset(
    ("SKALD", "GAM", "URE", "FORN", "SJALD", "VILLA", "STAD", "BARN", "OTOK")
)


def find_bad_suffixes() -> None:
    """Scan suffixes.txt and write the non-modern forms to suffix-removals.txt."""
    resources_path = os.path.join(basepath, "src", "islenska", "resources")
    src = os.path.join(resources_path, "suffixes.txt")
    out = os.path.join(resources_path, "suffix-removals.txt")

    b = Bin()
    removals: list[str] = []
    scanned = 0
    t0 = time.time()
    with open(src, "r", encoding="utf-8") as f:
        for line in f:
            w = line.strip()
            if not w:
                continue
            scanned += 1
            # Only classify forms that are directly in BÍN; gating on
            # contains() keeps lookup_ksnid from falling back to compound
            # resolution, so we inspect the form's own readings.
            if not b.contains(w):
                continue
            entries = b.lookup_ksnid(w)[1]
            if entries and all(
                k.malsnid in NON_MODERN_REGISTERS for k in entries
            ):
                removals.append(w)
            if scanned % 200000 == 0:
                print(f"  ...{scanned:,} scanned ({time.time() - t0:.0f}s)")

    removals.sort()
    with open(out, "w", encoding="utf-8") as f:
        for w in removals:
            f.write(w + "\n")
    print(f"Scanned {scanned:,} suffix forms in {time.time() - t0:.0f}s")
    print(f"Wrote {len(removals):,} removals to {out}")


if __name__ == "__main__":
    find_bad_suffixes()
