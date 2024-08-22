"""
    BinPackage

    Compound word analyzer

    Copyright © 2023 Miðeind ehf.

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

    The compound word analyzer takes a word not found in the
    BIN word database and attempts to resolve it into parts
    as a compound word.

    It uses a Directed Acyclic Word Graph (DAWG) internally
    to store a large set of words in an efficient structure in terms
    of storage and speed.

    The graph is pre-built and stored in a file that
    is loaded at run-time by DawgDictionary.

"""

from typing import Dict, List, Optional, Union, Tuple, Iterator, ItemsView, cast

import os
import threading
import struct
import mmap

import importlib.resources as importlib_resources

_PATH = os.path.dirname(__file__) or "."


class Wordbase:
    """Container for a singleton instance of the word database"""

    # All word forms
    _dawg_all: Optional["PackedDawgDictionary"] = None
    # Word forms allowed as former parts of compounds
    _dawg_prefixes: Optional["PackedDawgDictionary"] = None
    # Word forms allowed as last part of compounds
    _dawg_suffixes: Optional["PackedDawgDictionary"] = None

    _lock = threading.Lock()

    @staticmethod
    def _load_resource(resource: str) -> "PackedDawgDictionary":
        """Load a PackedDawgDictionary from a file"""
        # Assumes that the appropriate lock has been acquired
        if __package__:
            # If we're inside a package (which is by far the most common case),
            # obtain the name of a resource file through importlib.
            ref = importlib_resources.files("islenska") / "resources" / f"{resource}.dawg.bin"
            with importlib_resources.as_file(ref) as path:
                pname = str(path)
        else:
            pname = os.path.abspath(os.path.join(_PATH, "resources", resource + ".dawg.bin"))
        dawg = PackedDawgDictionary()
        dawg.load(pname)
        return dawg

    @classmethod
    def dawg(cls) -> "PackedDawgDictionary":
        """Load the combined dictionary"""
        with cls._lock:
            if cls._dawg_all is None:
                cls._dawg_all = Wordbase._load_resource("ordalisti-all")
            assert cls._dawg_all is not None
            return cls._dawg_all

    @classmethod
    def dawg_prefixes(cls) -> "PackedDawgDictionary":
        """Load the dictionary of words allowed as prefixes
        in a compound word (i.e. can occur in any part except
        the last part of the compound word)"""
        with cls._lock:
            if cls._dawg_prefixes is None:
                cls._dawg_prefixes = Wordbase._load_resource("ordalisti-prefixes")
            assert cls._dawg_prefixes is not None
            return cls._dawg_prefixes

    @classmethod
    def dawg_suffixes(cls) -> "PackedDawgDictionary":
        """Load the dictionary of words that are allowed as the last
        part of a compound word"""
        with cls._lock:
            if cls._dawg_suffixes is None:
                cls._dawg_suffixes = Wordbase._load_resource("ordalisti-suffixes")
            assert cls._dawg_suffixes is not None
            return cls._dawg_suffixes

    @classmethod
    def slice_compound_word(cls, word: str) -> List[str]:
        """Get best combination of word parts if such a combination exists"""
        # We get back a list of lists, i.e. all possible compound word combinations
        # where each combination is a list of word parts.
        w = cls.dawg().find_combinations(word)
        if w:
            # Sort by (1) longest last part and (2) the lowest overall number of parts
            w.sort(key=lambda x: (len(x[-1]), -len(x)), reverse=True)
            prefixes = cls.dawg_prefixes()
            suffixes = cls.dawg_suffixes()
            # Loop over the sorted combinations until we find a legal one,
            # i.e. where the suffix is a legal suffix and all prefixes are
            # legal prefixes
            for combination in w:
                if combination[-1] in suffixes and all(c in prefixes for c in combination[0:-1]):
                    # Valid combination: return it
                    return combination
        # No legal combination found
        return []


class FindNavigator:
    """A navigation class to be used with DawgDictionary.navigate()
    to find a particular word in the dictionary by exact match
    """

    def __init__(self, word: str) -> None:
        self._word = word
        self._len = len(word)
        self._index = 0
        self._found = False

    def push_edge(self, firstchar: str) -> bool:
        """Returns True if the edge should be entered or False if not"""
        # Enter the edge if it fits where we are in the word
        return self._word[self._index] == firstchar

    def accepting(self) -> bool:
        """Returns False if the navigator does not want more characters"""
        # Don't go too deep
        return self._index < self._len

    def accepts(self, newchar: str) -> bool:
        """Returns True if the navigator will accept the new character"""
        if newchar != self._word[self._index]:
            return False
        # Match: move to the next index position
        self._index += 1
        return True

    def accept(self, matched: str, final: bool) -> None:
        """Called to inform the navigator of a match and whether it is a final word"""
        if final and self._index == self._len:
            # Yes, this is what we were looking for
            assert matched == self._word
            self._found = True

    # noinspection PyMethodMayBeStatic
    def pop_edge(self) -> bool:
        """Called when leaving an edge that has been navigated"""
        # We only need to visit one outgoing edge, so short-circuit the edge loop
        return False

    def is_found(self) -> bool:
        return self._found


class CompoundNavigator:
    """A navigation class to be used with DawgDictionary.navigate()
    to find all possible compositions of shorter words that
    together form a long (compound) word.
    """

    def __init__(self, dawg: "PackedDawgDictionary", word: str) -> None:
        self._dawg = dawg
        self._word = word
        self._len = len(word)
        self._index = 0
        self._parts: List[List[str]] = []

    def push_edge(self, firstchar: str) -> bool:
        """Returns True if the edge should be entered or False if not"""
        # Follow all edges that match a letter in the compound word
        return self._word[self._index] == firstchar

    def accepting(self) -> bool:
        """Returns False if the navigator does not want more characters"""
        # Continue until we have generated all left parts possible from the
        # rack but leaving at least one tile
        return self._index < self._len

    def accepts(self, newchar: str) -> bool:
        """Returns True if the navigator will accept the new character"""
        if newchar != self._word[self._index]:
            return False
        self._index += 1
        return True

    def accept(self, matched: str, final: bool) -> None:
        """Called to inform the navigator of a match and whether it is a final word"""
        if final:
            # We have a valid word so far: attempt to resolve the following text
            if self._index == self._len:
                # Complete match: return a single part
                self._parts = [[matched]]
            else:
                # So far so good: try to match the rest
                nav = CompoundNavigator(self._dawg, self._word[self._index :])
                self._dawg.navigate(nav)
                result = nav.result()
                if result:
                    self._parts.extend([[matched] + tail for tail in result])

    # noinspection PyMethodMayBeStatic
    def pop_edge(self) -> bool:
        """Called when leaving an edge that has been navigated"""
        return False

    def result(self) -> List[List[str]]:
        return self._parts


class PackedDawgDictionary:
    """Encapsulates a DAWG dictionary that is initialized from a packed
    binary file on disk and navigated as a byte buffer."""

    def __init__(self) -> None:
        # The packed byte buffer
        self._b: Optional[mmap.mmap] = None
        self._vocabulary: Optional[str] = None
        self._root_offset = 0
        self._encoding: Dict[int, str] = dict()

    def load(self, fname: str) -> None:
        """Load a packed DAWG from a binary file"""
        if self._b is not None:
            # Already loaded
            return
        # Map the file contents to a memory map, reflected in a byte buffer
        with open(fname, mode="rb") as stream:
            self._b = mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ)
        # Check the signature
        assert self._b[0:12] == b"ReynirDawg!\n"
        # Get the DAWG vocabulary (alphabet)
        (len_voc,) = struct.Struct("<L").unpack_from(self._b, 12)
        self._vocabulary = self._b[16 : 16 + len_voc].decode("utf-8")
        self._root_offset = 16 + len_voc
        # Assemble a decoding dictionary where encoded indices are mapped to
        # characters, eventually with a suffixed vertical bar '|' to denote finality
        self._encoding = {i: c for i, c in enumerate(self._vocabulary)}
        self._encoding.update({i | 0x80: c + "|" for i, c in enumerate(self._vocabulary)})

    def find(self, word: str) -> bool:
        """Look for a word in the graph, returning True
        if it is found or False if not"""
        return self.__contains__(word)

    def __contains__(self, word: str) -> bool:
        """Enable simple lookup syntax: "word" in dawgdict"""
        nav = FindNavigator(word)
        self.navigate(nav)
        return nav.is_found()

    def find_combinations(self, word: str):
        """Attempt to slice an unknown word into parts, where each part is
        a valid word form in itself, and the parts form a valid compound word."""
        nav = CompoundNavigator(self, word)
        self.navigate(nav)
        return nav.result()

    def navigate(self, nav: Union[FindNavigator, CompoundNavigator]) -> None:
        """A generic function to navigate through the DAWG under
        the control of a navigation object.

        The navigation object should implement the following interface:

        def push_edge(firstchar)
            returns True if the edge should be entered or False if not
        def accepting()
            returns False if the navigator does not want more characters
        def accepts(newchar)
            returns True if the navigator will accept and 'eat' the new character
        def accept(matched, final)
            called to inform the navigator of a match and whether
            it is a final word
        def pop_edge()
            called when leaving an edge that has been navigated; returns False
            if there is no need to visit other edges
        """
        assert self._b is not None
        PackedNavigation(nav, self._b, self._root_offset, self._encoding).go()


class PackedNavigation:
    """Manages the state for a navigation while it is in progress"""

    # The structure used to decode an edge offset from bytes
    _UINT32 = struct.Struct("<L")

    # Dictionary of edge iteration caches, keyed by byte buffer
    _iter_caches: Dict[int, Dict[int, Dict[str, int]]] = dict()

    def __init__(
        self,
        nav: Union[FindNavigator, CompoundNavigator],
        b: mmap.mmap,
        root_offset: int,
        encoding: Dict[int, str],
    ) -> None:
        # Store the associated navigator
        self._nav = nav
        # The DAWG bytearray
        self._b = b
        self._root_offset = root_offset
        self._encoding = encoding
        self._iter_cache: Dict[int, Dict[str, int]]
        if id(b) in self._iter_caches:
            # We already have a cache associated with this byte buffer
            self._iter_cache = self._iter_caches[id(b)]
        else:
            # Create a fresh cache for this byte buffer
            self._iter_cache = self._iter_caches[id(b)] = cast(Dict[int, Dict[str, int]], dict())

    def _iter_from_node(self, offset: int) -> Iterator[Tuple[str, int]]:
        """A generator for yielding prefixes and next node offset along an edge
        starting at the given offset in the DAWG bytearray"""
        b = self._b
        encoding = self._encoding
        num_edges = b[offset] & 0x7F
        offset += 1
        for _ in range(num_edges):
            len_byte = b[offset] & 0x7F
            offset += 1
            prefix = "".join(encoding[b[offset + j]] for j in range(len_byte))
            offset += len_byte
            if b[offset - 1] & 0x80:
                # The last character of the prefix had a final marker: nextnode is 0
                nextnode = 0
            else:
                # Read the next node offset
                (nextnode,) = self._UINT32.unpack_from(b, offset)  # Tuple of length 1, i.e. (n, )
                offset += 4
            yield prefix, nextnode

    def _make_iter_from_node(self, offset: int) -> ItemsView[str, int]:
        """Return an iterator over the prefixes and next node pointers
        of the edge at the given offset. If this is the first time
        that the edge is iterated, cache its unpacked contents
        in a dictionary for quicker subsequent iteration."""
        d: Dict[str, int]
        try:
            d = self._iter_cache[offset]
        except KeyError:
            d = {prefix: nextnode for prefix, nextnode in self._iter_from_node(offset)}
            self._iter_cache[offset] = d
        return d.items()

    def _navigate_from_node(self, offset: int, matched: str) -> None:
        """Starting from a given node, navigate outgoing edges"""
        # Go through the edges of this node and follow the ones
        # okayed by the navigator
        nav = self._nav
        for prefix, nextnode in self._make_iter_from_node(offset):
            if nav.push_edge(prefix[0]):
                # This edge is a candidate: navigate through it
                self._navigate_from_edge(prefix, nextnode, matched)
                if not nav.pop_edge():
                    # Short-circuit and finish the loop if pop_edge() returns False
                    break

    def _navigate_from_edge(self, prefix: str, nextnode: int, matched: str) -> None:
        """Navigate along an edge, accepting partial and full matches"""
        # Go along the edge as long as the navigator is accepting
        b = self._b
        lenp = len(prefix)
        j = 0
        nav = self._nav
        while j < lenp and nav.accepting():
            # See if the navigator is OK with accepting the current character
            if not nav.accepts(prefix[j]):
                # Nope: we're done with this edge
                return
            # So far, we have a match: add a letter to the matched path
            matched += prefix[j]
            j += 1
            # Check whether the next prefix character is a vertical bar,
            # denoting finality
            final = False
            if j < lenp:
                if prefix[j] == "|":
                    final = True
                    j += 1
            elif nextnode == 0 or b[nextnode] & 0x80:
                # If we're at the final char of the prefix and the next node is final,
                # set the final flag as well (there is no trailing
                # vertical bar in this case)
                final = True
            # Tell the navigator where we are
            nav.accept(matched, final)
        # We're done following the prefix for as long as it goes and
        # as long as the navigator was accepting
        if j < lenp:
            # We didn't complete the prefix, so the navigator must no longer
            # be interested (accepting): we're done
            return
        if nextnode != 0 and nav.accepting():
            # Gone through the entire edge and still have rack letters left:
            # continue with the next node
            self._navigate_from_node(nextnode, matched)

    def go(self) -> None:
        """Perform the navigation using the given navigator"""
        # The ship is ready to go
        if self._nav.accepting():
            # Leave shore and navigate the open seas
            self._navigate_from_node(self._root_offset, "")
