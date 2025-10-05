/*

   BinPackage

   C++ DAWG dictionary module

   Copyright © 2025 Miðeind ehf.
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

*/

#include <stdint.h>

// C99 bool support (C++ has bool built-in)
#ifndef __cplusplus
#include <stdbool.h>
#endif

typedef uint8_t BYTE;

// Opaque handle for the DAWG dictionary
typedef void* DawgHandle;

#ifdef __cplusplus
extern "C" {
#endif

// Load a DAWG from a memory map. Returns a handle.
DawgHandle dawg_load(const BYTE* pbMap);

// Unload a DAWG and free resources.
void dawg_unload(DawgHandle handle);

// Check if a word exists in the DAWG. Returns true if found, false otherwise.
bool dawg_contains(DawgHandle handle, const char* word);

// Find compound word combinations.
// Returns a result string that needs to be freed with dawg_free_string().
char* dawg_find_combinations(DawgHandle handle, const char* word);

// Free the string returned by dawg_find_combinations.
void dawg_free_string(char* str);

#ifdef __cplusplus
}
#endif
