#!/usr/bin/env python3
"""
This file is retained for CFFI compilation.
All package metadata is defined in pyproject.toml.
"""

import platform
from setuptools import setup

# The cffi_modules and zip_safe settings are not yet supported in pyproject.toml
# and must be defined here.

# Use stable ABI for CPython to create portable wheels across Python versions
# PyPy doesn't support the stable ABI, so we skip this for PyPy builds
options = {}
if platform.python_implementation() == "CPython":
    options["py_limited_api"] = "cp39"  # Requires Python 3.9+

setup(
    zip_safe=True,
    cffi_modules=["src/islenska/bin_build.py:ffibuilder"],
    options={"bdist_wheel": options},
)
