/*

   BinPackage

   C++ BÍN lookup module

   Copyright © 2023 Miðeind ehf.
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

   This module implements lookup of words within a compressed, memory-mapped
   byte buffer containing the Database of Modern Icelandic Inflection
   (Beygingarlýsing íslensks nútímamáls, BÍN).

   The memory layout of the compressed buffer is determined by the
   BinCompressor class in tools/binpack.py.

*/

// #define DEBUG

#include <stdio.h>
#include <assert.h>
#include <time.h>

#include "bin.h"


#define TRUE 1
#define FALSE 0

#define NOT_FOUND 0xFFFFFFFF

typedef int INT;
typedef bool BOOL;
typedef uint32_t UINT32;


class BIN_Compressed {

private:

#pragma pack(push, 1)

   struct Header {
      BYTE abSignature[16];
      UINT32 nMappingsOffset;
      UINT32 nFormsOffset;
      UINT32 nLemmasOffset;
      UINT32 nTemplatesOffset;
      UINT32 nMeaningsOffset;
      UINT32 nAlphabetOffset;
      UINT32 nSubcatsOffset;
      UINT32 nKsnidOffset;
   };

#pragma pack(pop)

   const BYTE* m_pbMap;
   const Header* m_pHeader;
   UINT m_nFormsRootHeader;
   UINT m_nWordLen;
   const BYTE* m_pbWordLatin;
   UINT m_nAlphabetLength;
   const BYTE* m_pbAlphabet;

   // Return the UINT32 at the given offset, as a native UINT
   UINT uintAt(UINT nOffset)
      { return (UINT)*(UINT32*)(this->m_pbMap + nOffset); }

   INT matches(UINT nNodeOffset, UINT nHdr, UINT nFragmentIndex);
   UINT lookup(UINT nNodeOffset, UINT nHdr, UINT nFragmentIndex);

public:

   BIN_Compressed(const BYTE* pbMap);
   ~BIN_Compressed();

   // Return the offset of the meanings of the given word within
   // the memory buffer, or 0xFFFFFFFF if not found (note that 0
   // is a valid offset). The word is assumed to be Latin-1 encoded.
   UINT mapping(const BYTE* pbWord);

};


INT BIN_Compressed::matches(UINT nNodeOffset, UINT nHdr, UINT nFragmentIndex)
{
   /* If the lookup fragment word[fragment_index:] matches the node,
      return the number of characters matched. Otherwise,
      return -1 if the node is lexicographically less than the
      lookup fragment, or 0 if the node is greater than the fragment.
      (The lexicographical ordering here is actually a comparison
      between the Latin-1 ordinal numbers of characters.)
   */
   if (nHdr & 0x80000000) {
      // Single-character fragment
      UINT nIx = ((nHdr >> 23) & 0x7F) - 1; // Index of character in alphabet
      BYTE ch = this->m_pbAlphabet[nIx];
      BYTE chWord = this->m_pbWordLatin[nFragmentIndex];
      if (ch == chWord) {
         // Match
         return 1;
      }
      return (ch > chWord) ? 0 : -1;
   }
   UINT nFrag;
   if (nHdr & 0x40000000) {
      // Childless node
      nFrag = nNodeOffset + sizeof(UINT32);
   }
   else {
      UINT nNumChildren = this->uintAt(nNodeOffset + sizeof(UINT32));
      nFrag = nNodeOffset + 2 * sizeof(UINT32) + sizeof(UINT32) * nNumChildren;
   }
   INT iMatched = 0;
   UINT nWordLen = (UINT)this->m_nWordLen;
   BYTE* pFrag = (BYTE*)(this->m_pbMap + nFrag);
   while (*pFrag && (nFragmentIndex + iMatched < nWordLen) &&
      (*pFrag == this->m_pbWordLatin[nFragmentIndex + iMatched])) {
      pFrag++;
      iMatched++;
   }
   if (!*pFrag) {
      // Matched the entire fragment: success
      return iMatched;
   }
   if (nFragmentIndex + iMatched >= nWordLen) {
      // The node is longer and thus greater than the fragment
      return 0;
   }
   return (*pFrag > this->m_pbWordLatin[nFragmentIndex + iMatched]) ? 0 : -1;
}

UINT BIN_Compressed::lookup(UINT nNodeOffset, UINT nHdr, UINT nFragmentIndex)
{
   while (TRUE) {
      if (nFragmentIndex >= (UINT)this->m_nWordLen) {
         // We've arrived at our destination:
         // return the associated value (unless this is an interim node)
         UINT nValue = nHdr & 0x007FFFFF;
         return (nValue == 0x007FFFFF) ? NOT_FOUND : nValue;
      }
      if (nHdr & 0x40000000) {
         // Childless node: nowhere to go
         return NOT_FOUND;
      }
      UINT nNumChildren = this->uintAt(nNodeOffset + sizeof(UINT32));
      UINT nChildOffset = nNodeOffset + 2 * sizeof(UINT32);
      // Binary search for a matching child node
      UINT nLo = 0;
      UINT nHi = nNumChildren;
      BOOL fContinue = TRUE;
      do {
         if (nLo >= nHi) {
            // No child route matches
            return NOT_FOUND;
         }
         UINT nMid = (nLo + nHi) / 2;
         UINT nMidLoc = nChildOffset + nMid * sizeof(UINT32);
         UINT nMidOffset = this->uintAt(nMidLoc);
         nHdr = this->uintAt(nMidOffset);
         INT iMatchLen = this->matches(nMidOffset, nHdr, nFragmentIndex);
         if (iMatchLen > 0) {
             // Set a new starting point and restart from the top
             nNodeOffset = nMidOffset;
             nFragmentIndex += iMatchLen;
             fContinue = FALSE;
         }
         else
         if (iMatchLen < 0) {
            nLo = nMid + 1;
         }
         else {
            nHi = nMid;
         }
      } while (fContinue);
   }
   // Should never get here
   assert(FALSE);
}

BIN_Compressed::BIN_Compressed(const BYTE* pbMap)
   : m_pbMap(pbMap), m_pHeader((const Header*)pbMap),
      m_nFormsRootHeader(this->uintAt(m_pHeader->nFormsOffset)),
      m_nWordLen(0),
      m_pbWordLatin(NULL),
      m_nAlphabetLength(this->uintAt(m_pHeader->nAlphabetOffset)),
      m_pbAlphabet(this->m_pbMap + m_pHeader->nAlphabetOffset + sizeof(UINT32))
{
}

BIN_Compressed::~BIN_Compressed()
{
}

UINT BIN_Compressed::mapping(const BYTE* pbWordLatin)
{
   // Note that calls to mapping() on the same BIN_Compressed instance
   // are not re-entrant. BIN_Compressed is designed to be instantiated
   // on the stack, per-thread, for each sequence of mapping calls.
   if (!pbWordLatin) {
      return NOT_FOUND;
   }
   this->m_pbWordLatin = pbWordLatin;
   this->m_nWordLen = (UINT)strlen((const char*)pbWordLatin);
   return this->lookup(this->m_pHeader->nFormsOffset, this->m_nFormsRootHeader, 0);
}

UINT mapping(const BYTE* pbMap, const BYTE* pbWordLatin)
{
   BIN_Compressed bc(pbMap);
   return bc.mapping(pbWordLatin);
}

