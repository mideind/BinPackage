#!/usr/bin/env python3
"""
    BinPackage

    Setup.py

    Copyright © 2024 Miðeind ehf.
    Original Author: Vilhjálmur Þorsteinsson

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


    This module sets up the BinPackage package. It uses the cffi_modules
    parameter, available in recent versions of setuptools, to
    automatically compile the bin.cpp module to bin.*.so/.pyd
    and build the required CFFI Python wrapper via bin_build.py.

"""

from glob import glob
from os.path import basename, splitext

from setuptools import setup, find_packages

setup(
    packages=find_packages("src"),
    package_dir={"": "src"},
    py_modules=[splitext(basename(path))[0] for path in glob("src/*.py")],
    package_data={"islenska": ["py.typed"]},
    include_package_data=True,
    zip_safe=True,
    setup_requires=["cffi>=1.15.1"],
    install_requires=["cffi>=1.15.1", "typing_extensions"],
    cffi_modules=["src/islenska/bin_build.py:ffibuilder"],
)
