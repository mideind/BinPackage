"""

    BinPackage

    CFFI builder for the _bin module

    Copyright © 2025 Miðeind ehf.
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

    This module only runs at setup/installation time. It is invoked
    from setup.py as requested by the cffi_modules=[] parameter of the
    setup() function. It causes the _bin.*.so CFFI wrapper library
    to be built from the libbin sources (see libbin/ at the root of the
    repository). The C declarations are read from libbin/include/libbin/bin.h,
    between the CFFI-BEGIN and CFFI-END markers, so the header is the
    single source of truth for the interface.

"""

from typing import cast, Any

import os
import platform

import cffi  # type: ignore

ffibuilder = cast(Any, cffi).FFI()

WINDOWS = platform.system() == "Windows"
MACOS = platform.system() == "Darwin"
IMPLEMENTATION = platform.python_implementation()

# The repository root, i.e. the parent of src/
_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.abspath(os.path.join(_here, "..", ".."))
_libbin = os.path.join(_root, "libbin")
_header = os.path.join(_libbin, "include", "libbin", "bin.h")

with open(_header, "r", encoding="utf-8") as f:
    _header_text = f.read()
_begin = _header_text.index("/* CFFI-BEGIN */") + len("/* CFFI-BEGIN */")
_end = _header_text.index("/* CFFI-END */")
declarations = _header_text[_begin:_end]

if WINDOWS:
    extra_compile_args = ["/std:c++17", "/Zc:offsetof-"]
else:
    extra_compile_args = ["-std=c++17"]

extra_link_args = []
if MACOS:
    extra_link_args = ["-stdlib=libc++", "-mmacosx-version-min=10.13"]
    os.environ["MACOSX_DEPLOYMENT_TARGET"] = "10.13"

if IMPLEMENTATION == "PyPy":
    os.environ["LDCXXSHARED"] = "c++ -shared"

ffibuilder.cdef(declarations)  # type: ignore

py_limited_api = "cp39" if IMPLEMENTATION == "CPython" else False

ffibuilder.set_source(  # type: ignore
    "islenska._bin",
    '#include "libbin/bin.h"\n',
    source_extension=".cpp",
    sources=[
        os.path.relpath(os.path.join(_libbin, "src", name), _root)
        for name in ("trie.cpp", "dawg.cpp", "dict.cpp", "api.cpp")
    ],
    include_dirs=[
        os.path.relpath(os.path.join(_libbin, "include"), _root),
        os.path.relpath(os.path.join(_libbin, "src"), _root),
    ],
    extra_compile_args=extra_compile_args,
    extra_link_args=extra_link_args,
    py_limited_api=py_limited_api,
)

if __name__ == "__main__":
    ffibuilder.compile(verbose=False)  # type: ignore
