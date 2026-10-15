#!/usr/bin/env python3
"""
This file is retained for CFFI compilation.
All package metadata is defined in pyproject.toml.
"""

import platform
import sysconfig
from setuptools import setup

# The cffi_modules and zip_safe settings are not yet supported in pyproject.toml
# and must be defined here.

# Use stable ABI for CPython to create portable wheels across Python versions
# PyPy and free-threaded CPython don't support the stable ABI
options: dict[str, str] = {}
if platform.python_implementation() == "CPython" and not sysconfig.get_config_var("Py_GIL_DISABLED"):
    options["py_limited_api"] = "cp310"  # Requires Python 3.10+

setup(
    zip_safe=True,
    cffi_modules=["src/islenska/bin_build.py:ffibuilder"],
    options={"bdist_wheel": options},
)
