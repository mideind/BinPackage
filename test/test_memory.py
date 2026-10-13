"""

    test_memory.py

    Tests that opening the compressed dictionary does not copy it
    into process memory

    Copyright © 2026 Miðeind ehf.

    This software is licensed under the MIT License (see test_bin.py)

    BinCompressed memory-maps compressed.bin so that the data stays in
    the page cache, shared between processes. Slicing the mmap object
    (self._b[offset:]) returns a bytes copy instead of a view: taken from
    the mappings offset, it copied about 90 MB of the file into private
    heap memory of every process that opened the dictionary, and reading
    the whole file to make the copy also faulted every mapped page in.
    No lookup reads the copy (libbin works on the mapped pointer).

    The test traces Python allocations while the dictionary is opened.
    A copy of any sizeable part of the file shows up there; the views
    over the memory map do not.

"""

import gc
import os

import pytest

from islenska.bincompress import BinCompressed

try:
    import tracemalloc
except ImportError:  # PyPy has no _tracemalloc; the check on CPython is enough
    tracemalloc = None

# Opening the dictionary allocates a little (the subcategory list, the
# alphabet, the DAWG wrappers). A tenth of the data file is far above
# that and far below the copy that this test guards against.
_ALLOWED_FRACTION = 0.1


@pytest.mark.skipif(tracemalloc is None, reason="tracemalloc is not available (PyPy)")
def test_opening_does_not_copy_the_data_file() -> None:
    assert tracemalloc is not None
    gc.collect()
    tracemalloc.start()
    try:
        before, _ = tracemalloc.get_traced_memory()
        bc = BinCompressed()
        after, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    try:
        file_size = os.path.getsize(bc.fname)
        limit = file_size * _ALLOWED_FRACTION
        assert peak - before < limit, (
            f"Opening the dictionary allocated {(peak - before) / 2**20:.1f} MiB "
            f"at peak ({(after - before) / 2**20:.1f} MiB retained) for a "
            f"{file_size / 2**20:.1f} MiB data file: a slice of the memory map "
            "is being copied instead of viewed (use memoryview)"
        )
        # The views still serve lookups
        assert bc.lookup_id(bc.lookup("hestur")[0][1])
    finally:
        bc.close()


def test_close_releases_the_memory_map() -> None:
    bc = BinCompressed()
    assert bc.lookup("hestur")
    # An mmap with exported buffers (live memoryviews) cannot be closed
    bc.close()
    bc.close()  # A second close is a no-op
