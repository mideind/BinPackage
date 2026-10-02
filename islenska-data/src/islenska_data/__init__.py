"""

    islenska-data

    The vocabulary data of the islenska package (BinPackage): the Database
    of Icelandic Morphology (BÍN) in the compressed form that islenska
    reads, plus the word graphs (DAWGs) of its compound word algorithm.

    Copyright © 2026 Miðeind ehf.

    The BÍN data are © The Árni Magnússon Institute for Icelandic Studies
    and are used under the CC BY-SA 4.0 license; see README.md. The code
    of this package is under the MIT license.

    This package has no functionality of its own; install islenska and it
    finds the data here. The files are built in the BinPackage repository
    by tools/binpack.py and tools/dawgbuilder.py and staged into this
    package by tools/data_package.py.

"""

from pathlib import Path

try:
    from importlib.metadata import version as _version

    __version__ = _version("islenska-data")
except Exception:  # Not installed, e.g. imported from a source tree
    __version__ = "0.0.0"

# The data format of compressed.bin (its 16-byte signature); islenska
# uses this package only if the format is the one it reads
FORMAT = "Greynir 05.00.00"

# The data files in this package
FILES = (
    "compressed.bin",
    "ordalisti-all.dawg.bin",
    "ordalisti-prefixes.dawg.bin",
    "ordalisti-suffixes.dawg.bin",
)


def data_dir() -> Path:
    """Return the directory that holds the data files"""
    return Path(__file__).parent.resolve()


__all__ = ["FORMAT", "FILES", "data_dir", "__version__"]
