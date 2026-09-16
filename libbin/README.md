# libbin

The compressed BÍN dictionary and the compounder of BinPackage as a
self-contained C++17 library with a C API. The Python package (`islenska`)
builds these same sources into its CFFI extension, so there is one
implementation of the lookup logic, shared by Python and by native
consumers such as GreynirKbd.

## Layout

| Path | Contents |
|---|---|
| `include/libbin/bin.h` | The public C API. The section between the `CFFI-BEGIN` and `CFFI-END` markers is read verbatim by `src/islenska/bin_build.py`, so it must stay plain C. |
| `src/trie.cpp` | The packed radix trie of word forms. |
| `src/dawg.cpp` | The packed DAWG reader (`ordalisti-*.dawg.bin`) with the compound-split enumerator. |
| `src/dict.cpp` | The dictionary: decoding of the mappings, lemma, meaning and ksnid sections, compound candidates, and the compact build's restoration of dropped compounds. |
| `src/api.cpp` | The C API over the classes above. |
| `tests/bin_test.cpp` | A smoke test; needs the data files of a BinPackage checkout. |

## Data files

The library reads the files that BinPackage builds and ships:

- `compressed.bin` (format `Greynir 05.00.00`), built by `tools/binpack.py`,
  either in full or with `--compact`.
- `ordalisti-all.dawg.bin`, `ordalisti-prefixes.dawg.bin`,
  `ordalisti-suffixes.dawg.bin`, built by `tools/dawgbuilder.py`.

The caller maps the files into memory and keeps the maps valid for the
lifetime of the handles; the library never copies or owns them. A compact
`compressed.bin` needs the three DAWGs to restore the compounds it left
out; a full one works without them, but then the compound functions
return nothing.

## Threads

Handles are immutable after creation and can be shared between threads
without locking. Navigation state lives on the stack of each call, and
result objects belong to the calling thread.

## Strings

All strings in and out are Latin-1 and NUL-terminated. This is the
encoding of the data files, and every character of Icelandic fits in it.

## Building

```sh
cmake -S libbin -B libbin/build -DCMAKE_BUILD_TYPE=Release
cmake --build libbin/build -j
ctest --test-dir libbin/build     # runs bin_test on ../src/islenska/resources
```

From another CMake project:

```cmake
add_subdirectory(path/to/BinPackage/libbin)   # or FetchContent
target_link_libraries(myapp PRIVATE libbin::bin)
```

A consumer that must ship a single static archive (an iOS xcframework, an
Android JNI library) folds the objects into its own library instead:

```cmake
add_subdirectory(path/to/BinPackage/libbin EXCLUDE_FROM_ALL)
add_library(mycore STATIC mycore.cpp $<TARGET_OBJECTS:libbin_objects>)
target_link_libraries(mycore PRIVATE libbin::objects)   # for the include path
```

`LIBBIN_TESTS` is on when libbin is the top-level project and off when it
is added as a subdirectory.

## Minimal example

```c
#include "libbin/bin.h"

/* map the four files (mmap, or read into memory) ... */
BinDawg* all = bin_dawg_open(all_map, all_len);
BinDawg* pre = bin_dawg_open(pre_map, pre_len);
BinDawg* suf = bin_dawg_open(suf_map, suf_len);
char err[256];
BinDict* dict = bin_open(bin_map, bin_len, all, pre, suf, err, sizeof err);

BinResult* r = bin_lookup(dict, "b\xf3kahillum", NULL, NULL, 0);  /* bókahillum */
for (uint32_t i = 0; r && i < r->count; i++) {
    const BinEntry* e = &r->entries[i];
    /* e->ord "bókahilla", e->bin_id, e->ofl "kvk", e->hluti "alm",
       e->bmynd "bókahillum", e->mark "ÞGFFT", e->ksnid "1;;;;K;1;;;" */
}
bin_result_free(r);

bin_close(dict);
bin_dawg_close(all); bin_dawg_close(pre); bin_dawg_close(suf);
```
