"""Case lookups must iterate in the same order in every process.

A word can have several BÍN forms for one inflection ('instagram' has both 'instagrammi' and
'instagrami' as dative singular). Callers such as GreynirPackage take the first matching entry,
so the iteration order of the result must not depend on the per-process string hash seed.
"""

import os
import subprocess
import sys

from islenska.bincompress import BinCompressed

PROBE = """
from islenska.bincompress import BinCompressed
b = BinCompressed()
print(repr([
    list(b.lookup_case("instagram", "ÞGF")),
    list(b.dative("instagram")),
    list(b.lookup_case("fjarðarins", "NF", cat="kk", all_forms=True)),
    list(b.raw_nominative("fjarðarins")),
]))
"""


def _run(hash_seed: str) -> str:
    env = dict(os.environ, PYTHONHASHSEED=hash_seed)
    return subprocess.run(
        [sys.executable, "-c", PROBE], env=env, check=True, capture_output=True, text=True
    ).stdout


def test_word_with_two_forms_of_one_inflection() -> None:
    forms = {m[4] for m in BinCompressed().lookup_case("instagram", "ÞGF")}
    assert {"instagrammi", "instagrami"} <= forms


def test_case_lookups_do_not_depend_on_hash_seed() -> None:
    outputs = {_run(seed) for seed in ("0", "1", "2", "3", "4", "5")}
    assert len(outputs) == 1


def test_case_lookup_result_is_a_set() -> None:
    b = BinCompressed()
    result = b.lookup_case("fjarðarins", "NF", cat="kk", lemma="fjörður")
    assert result == {("fjörður", 5697, "kk", "alm", "fjörðurinn", "NFETgr")}
    assert ("fjörður", 5697, "kk", "alm", "fjörðurinn", "NFETgr") in result
    assert set(result) == result and len(result & result) == len(result)
