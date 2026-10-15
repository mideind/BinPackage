"""

    wheel_smoke.py

    Smoke test of an installed islenska wheel, run by cibuildwheel for every
    wheel before it is published (CIBW_TEST_COMMAND in wheels.yml), with the
    islenska-data wheel of the same run installed. Not a pytest module.

    Copyright © 2026 Miðeind ehf.

    This software is licensed under the MIT License (see test_bin.py)

"""

import sys
import sysconfig

import islenska_data

from islenska import Bin
from islenska.basics import data_dir

# A wheel has no data files of its own: they come from islenska-data
assert data_dir() == islenska_data.data_dir(), data_dir()
b = Bin()
_, m = b.lookup("hestarnir")
assert [(x.ord, x.mark) for x in m] == [("hestur", "NFFTgr")], m
# A compound that the compact data leave out and libbin restores on lookup
_, m = b.lookup("bókahillum")
assert [(x.ord, x.bin_id, x.mark) for x in m] == [("bókahilla", 154009, "ÞGFFT")], m
# On free-threaded Python the extension must not turn the GIL back on
if sysconfig.get_config_var("Py_GIL_DISABLED"):
    assert not sys._is_gil_enabled()  # type: ignore[attr-defined]
print("islenska wheel smoke test passed")
