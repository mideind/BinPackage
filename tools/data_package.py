#!/usr/bin/env python3
"""

    BinPackage

    Stage the data files into the islenska-data package

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

    The data files (compressed.bin from tools/binpack.py and the three
    DAWGs from tools/dawgbuilder.py) are built into src/islenska/resources.
    This program checks them and copies them into the islenska-data package
    (islenska-data/src/islenska_data), whose wheel can then be built with

        uv build --wheel islenska-data -o dist-data

    The checks: every file is present, and compressed.bin is a compact
    build with the data format that both islenska (basics.py) and
    islenska-data (its FORMAT) declare.

    Usage:

        python tools/data_package.py [--src DIR] [--clean]

"""

from types import ModuleType
from typing import List, Tuple

import argparse
import importlib.util
import os
import shutil
import struct
import sys

basepath = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
PKG_DIR = os.path.join(basepath, "islenska-data", "src", "islenska_data")
RESOURCES = os.path.join(basepath, "src", "islenska", "resources")


def load_module(name: str, fname: str) -> ModuleType:
    """Import a module from a file in the source tree, without importing
    its package (islenska's would load the compiled extension)"""
    spec = importlib.util.spec_from_file_location(name, fname)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_basics = load_module("islenska_basics", os.path.join(basepath, "src", "islenska", "basics.py"))
BIN_COMPRESSOR_VERSION: bytes = _basics.BIN_COMPRESSOR_VERSION
DATA_FILES: Tuple[str, ...] = _basics.DATA_FILES


def load_data_package() -> ModuleType:
    """Import islenska_data from the source tree, whether installed or not"""
    return load_module("islenska_data", os.path.join(PKG_DIR, "__init__.py"))


def check(src: str, pkg: ModuleType) -> List[str]:
    """Return a list of problems with the data files in src"""
    problems: List[str] = []
    if tuple(pkg.FILES) != DATA_FILES:
        problems.append(f"islenska_data.FILES {pkg.FILES} != islenska DATA_FILES {DATA_FILES}")
    if pkg.FORMAT.encode("ascii") != BIN_COMPRESSOR_VERSION:
        problems.append(
            f"islenska_data.FORMAT {pkg.FORMAT!r} != islenska's "
            f"{BIN_COMPRESSOR_VERSION.decode('ascii')!r}"
        )
    for name in DATA_FILES:
        if not os.path.isfile(os.path.join(src, name)):
            problems.append(f"{name} is missing from {src}")
    fname = os.path.join(src, DATA_FILES[0])
    if os.path.isfile(fname):
        with open(fname, "rb") as f:
            header = f.read(60)
        if header[0:16] != BIN_COMPRESSOR_VERSION:
            problems.append(f"{fname} has the signature {header[0:16]!r}")
        elif struct.unpack("<IIIIIIIIIII", header[16:60])[-1] == 0:
            problems.append(f"{fname} is not a compact build")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage the data files into the islenska-data package"
    )
    parser.add_argument("--src", default=RESOURCES, help="directory of the built data files")
    parser.add_argument("--clean", action="store_true", help="remove the staged data files")
    args = parser.parse_args()
    if args.clean:
        for name in DATA_FILES:
            path = os.path.join(PKG_DIR, name)
            if os.path.exists(path):
                os.remove(path)
        print(f"Removed the data files from {PKG_DIR}")
        return 0
    pkg = load_data_package()
    problems = check(args.src, pkg)
    if problems:
        for p in problems:
            print(f"Error: {p}", file=sys.stderr)
        return 1
    for name in DATA_FILES:
        shutil.copyfile(os.path.join(args.src, name), os.path.join(PKG_DIR, name))
        size = os.path.getsize(os.path.join(PKG_DIR, name))
        print(f"{name:30} {size:>12,} bytes")
    print(f"Staged into {PKG_DIR} (data format {pkg.FORMAT}).")
    print("Build the wheel with: uv build --wheel islenska-data -o dist-data")
    return 0


if __name__ == "__main__":
    sys.exit(main())
