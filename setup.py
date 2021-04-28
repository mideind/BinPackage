#!/usr/bin/env python
# -*- encoding: utf-8 -*-

"""
    BinPackage

    Setup.py

    Copyright (C) 2021 Miðeind ehf.
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

from __future__ import print_function
from __future__ import unicode_literals

import sys

from glob import glob
from os.path import basename, join, splitext

from setuptools import find_packages  # type: ignore
from setuptools import setup  # type: ignore


if sys.version_info < (3, 6):
    print("BinPackage requires Python >= 3.6")
    sys.exit(1)

# Load version string from file
__version__ = "[missing]"
exec(open(join("src", "islenska", "version.py")).read())

setup(
    name="islenska",
    version=__version__,
    license="MIT",
    description=(
        "The vocabulary of the modern Icelandic language, "
        "packed in a Python package"
    ),
    long_description=(
    """
        BinPackage, published by Miðeind ehf, is a Python package that embeds the
        vocabulary of the Database of Icelandic Morphology (Beygingarlýsing íslensks
        nútímamáls, BÍN) and offers various lookups and queries of the data.

        The database, maintained by Árni Magnússon Institute for Icelandic Studies,
        contains over 6.5 million entries, over 3.1 million unique word forms,
        and about 300,000 distinct lemmas.

        With BinPackage, `pip install islenska` is all you need to have almost all of
        of the commonly used vocabulary of the modern Icelandic language at your
        disposal via Python. Batteries are included; no additional databases,
        downloads or middleware are required.
    """
    ),
    author="Miðeind ehf",
    author_email="mideind@mideind.is",
    url="https://github.com/mideind/BinPackage",
    packages=find_packages("src"),
    package_dir={"": "src"},
    py_modules=[splitext(basename(path))[0] for path in glob("src/*.py")],
    package_data={"islenska": ["py.typed"]},
    include_package_data=True,
    zip_safe=True,
    classifiers=[
        # complete classifier list: http://pypi.python.org/pypi?%3Aaction=list_classifiers
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Unix",
        "Operating System :: POSIX",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: MacOS",
        "Natural Language :: Icelandic",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Utilities",
        "Topic :: Text Processing :: Linguistic",
    ],
    keywords=["nlp", "icelandic", "language", "vocabulary", "dictionary"],
    setup_requires=["cffi>=1.13.0"],
    install_requires=["cffi>=1.13.0", "typing_extensions"],
    cffi_modules=[
        "src/islenska/bin_build.py:ffibuilder"
    ],
)
