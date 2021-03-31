"""
    BinPackage

    Settings module

    Copyright (C) 2021 Miðeind ehf.

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

    This module reads and interprets the BinPackage.conf
    configuration file. The file can include other files using the $include
    directive, making it easier to arrange configuration sections into logical
    and manageable pieces.

    Sections are identified like so: [ section_name ]

    Comments start with # signs.

    Sections are interpreted by section handlers.

"""

from typing import (
    Optional,
    Dict,
    Tuple,
    Set,
    List,
    Callable,
)

import threading

from collections import defaultdict

from .basics import (
    ConfigError,
    LineReader,
    ALL_GENDERS,
)


# Type for static phrases: ofl, fl, beyging
StaticPhraseTuple = Tuple[str, str, str]
# Type for preference specifications
PreferenceTuple = Tuple[List[str], List[str], int]


class AdjectiveTemplate:

    """ Wrapper around template list of adjective endings """

    # List of tuples: (ending, form_spec)
    ENDINGS: List[Tuple[str, str]] = []

    @classmethod
    def add(cls, ending: str, form: str) -> None:
        """ Add an adjective ending and its associated form. """
        cls.ENDINGS.append((ending, form))


class Preferences:

    """ Wrapper around disambiguation hints, initialized from the config file """

    # Dictionary keyed by word containing a list of tuples (worse, better)
    # where each is a list of terminal prefixes
    DICT: Dict[str, List[PreferenceTuple]] = defaultdict(list)

    @staticmethod
    def add(word: str, worse: List[str], better: List[str], factor: int) -> None:
        """ Add a preference to the dictionary. Called from the config file handler. """
        Preferences.DICT[word].append((worse, better, factor))

    @staticmethod
    def get(word: str) -> Optional[List[PreferenceTuple]]:
        """ Return a list of (worse, better, factor) tuples for the given word """
        return Preferences.DICT.get(word, None)


class StemPreferences:

    """ Wrapper around lemma disambiguation hints, initialized from the config file """

    # Dictionary keyed by word form containing a tuple (worse, better)
    # where each is a list word lemmas
    DICT: Dict[str, Tuple[List[str], List[str]]] = dict()

    @staticmethod
    def add(word: str, worse: List[str], better: List[str]) -> None:
        """ Add a preference to the dictionary. Called from the config file handler. """
        if word in StemPreferences.DICT:
            raise ConfigError(
                "Duplicate lemma preference for word form {0}".format(word)
            )
        StemPreferences.DICT[word] = (worse, better)

    @staticmethod
    def get(word: str) -> Optional[Tuple[List[str], List[str]]]:
        """ Return a (worse, better) tuple for the given word form """
        return StemPreferences.DICT.get(word, None)


class NounPreferences:

    """ Wrapper for noun preferences, i.e. to assign priorities to different
        noun lemmas that can have identical word forms. """

    # This is a dict of noun word forms, giving the relative priorities
    # of different genders
    DICT: Dict[str, Dict[str, int]] = defaultdict(dict)

    @staticmethod
    def add(word: str, worse: str, better: str) -> None:
        """ Add a preference to the dictionary. Called from the config file handler. """
        if worse not in ALL_GENDERS or better not in ALL_GENDERS:
            raise ConfigError("Noun priorities must specify genders (kk, kvk, hk)")
        d = NounPreferences.DICT[word]
        worse_score = d.get(worse)
        better_score = d.get(better)
        if worse_score is not None:
            if better_score is not None:
                raise ConfigError("Conflicting priorities for noun {0}".format(word))
            better_score = worse_score + 4
        elif better_score is not None:
            worse_score = better_score - 4
        else:
            worse_score = -2
            better_score = 2
        d[worse] = worse_score
        d[better] = better_score


class BinErrata:

    """ Wrapper around BÍN errata, initialized from the config file """

    DICT: Dict[Tuple[str, str], str] = dict()

    @staticmethod
    def add(lemma: str, ofl: str, fl: str) -> None:
        """ Add a BÍN fix. Used by bincompress.py when generating a new
            compressed vocabulary file. """
        BinErrata.DICT[(lemma, ofl)] = fl


class BinDeletions:

    """ Wrapper around BÍN deletions, initialized from the config file """

    SET: Set[Tuple[str, str, str]] = set()

    @staticmethod
    def add(lemma: str, ofl: str, fl: str) -> None:
        """ Add a BÍN fix. Used by bincompress.py when generating a new
            compressed vocabulary file. """
        BinDeletions.SET.add((lemma, ofl, fl))


class Settings:

    """ Global settings """

    _lock = threading.Lock()
    loaded: bool = False
    
    # Configuration settings from the GreynirPackage.conf file

    @staticmethod
    def _handle_preferences(s: str) -> None:
        """ Handle ambiguity preference hints in the settings section """
        # Format: word worse1 worse2... < better
        # If two less-than signs are used, the preference is even stronger (tripled)
        # If three less-than signs are used, the preference is super strong (nine-fold)
        factor = 9
        a = s.lower().split("<<<", maxsplit=1)
        if len(a) != 2:
            factor = 3
            a = s.lower().split("<<", maxsplit=1)
            if len(a) != 2:
                # Not doubled preference: try a normal one
                a = s.lower().split("<", maxsplit=1)
                factor = 1
        if len(a) != 2:
            raise ConfigError("Ambiguity preference missing less-than sign '<'")
        w = a[0].split()
        if len(w) < 2:
            raise ConfigError(
                "Ambiguity preference must have at least one 'worse' category"
            )
        b = a[1].split()
        if len(b) < 1:
            raise ConfigError(
                "Ambiguity preference must have at least one 'better' category"
            )
        Preferences.add(w[0], w[1:], b, factor)

    @staticmethod
    def _handle_stem_preferences(s: str) -> None:
        """ Handle lemma ambiguity preference hints in the settings section """
        # Format: word worse1 worse2... < better
        a = s.lower().split("<", maxsplit=1)
        if len(a) != 2:
            raise ConfigError("Ambiguity preference missing less-than sign '<'")
        w = a[0].split()
        if len(w) < 2:
            raise ConfigError(
                "Ambiguity preference must have at least one 'worse' category"
            )
        b = a[1].split()
        if len(b) < 1:
            raise ConfigError(
                "Ambiguity preference must have at least one 'better' category"
            )
        StemPreferences.add(w[0], w[1:], b)

    @staticmethod
    def _handle_noun_preferences(s: str) -> None:
        """ Handle noun preference hints in the settings section """
        # Format: noun worse1 worse2... < better
        # The worse and better specifiers are gender names (kk, kvk, hk)
        a = s.lower().split("<", maxsplit=1)
        if len(a) != 2:
            raise ConfigError("Noun preference missing less-than sign '<'")
        w = a[0].split()
        if len(w) != 2:
            raise ConfigError("Noun preference must have exactly one 'worse' gender")
        b = a[1].split()
        if len(b) != 1:
            raise ConfigError("Noun preference must have exactly one 'better' gender")
        NounPreferences.add(w[0], w[1], b[0])

    @staticmethod
    def _handle_bin_errata(s: str) -> None:
        """ Handle changes to BÍN categories ('fl') """
        a = s.split()
        if len(a) != 3:
            raise ConfigError("Expected 'lemma ofl fl' fields in bin_errata section")
        lemma, ofl, fl = a
        if not ofl.islower() or not fl.islower():
            raise ConfigError(
                "Expected lowercase ofl and fl fields in bin_errata section"
            )
        BinErrata.add(lemma, ofl, fl)

    @staticmethod
    def _handle_bin_deletions(s: str) -> None:
        """ Handle deletions from BÍN, given as lemma/ofl/fl triples """
        a = s.split()
        if len(a) != 3:
            raise ConfigError(
                "Expected 'lemma ofl fl' fields in bin_deletions section"
            )
        lemma, ofl, fl = a
        if not ofl.islower() or not fl.islower():
            raise ConfigError(
                "Expected lowercase ofl and fl fields in bin_deletions section"
            )
        BinDeletions.add(lemma, ofl, fl)

    @staticmethod
    def _handle_adjective_template(s: str) -> None:
        """ Handle the template for new adjectives in the settings section """
        # Format: adjective-ending bin-meaning
        a = s.split()
        if len(a) != 2:
            raise ConfigError(
                "Adjective template should have an ending and a form specifier"
            )
        AdjectiveTemplate.add(a[0], a[1])

    @staticmethod
    def read(fname: str, force: bool=False) -> None:
        """ Read configuration file """

        with Settings._lock:

            if Settings.loaded and not force:
                return

            CONFIG_HANDLERS: Dict[str, Callable[[str], None]] = {
                "preferences": Settings._handle_preferences,
                "noun_preferences": Settings._handle_noun_preferences,
                "stem_preferences": Settings._handle_stem_preferences,
                "adjective_template": Settings._handle_adjective_template,
                "undeclinable_adjectives": lambda _: None,  # Not required
                "bin_errata": Settings._handle_bin_errata,
                "bin_deletions": Settings._handle_bin_deletions,
            }
            handler: Optional[Callable[[str], None]] = None  # Current section handler

            rdr: Optional[LineReader] = None
            try:
                rdr = LineReader(fname, package_name=__name__)
                for s in rdr.lines():
                    # Ignore comments
                    ix = s.find("#")
                    if ix >= 0:
                        s = s[0:ix]
                    s = s.strip()
                    if not s:
                        # Blank line: ignore
                        continue
                    if s[0] == "[" and s[-1] == "]":
                        # New section
                        section = s[1:-1].strip().lower()
                        if section in CONFIG_HANDLERS:
                            handler = CONFIG_HANDLERS[section]
                            continue
                        raise ConfigError("Unknown section name '{0}'".format(section))
                    if handler is None:
                        raise ConfigError("No handler for config line '{0}'".format(s))
                    # Call the correct handler depending on the section
                    try:
                        handler(s)
                    except ConfigError as e:
                        # Add file name and line number information to the exception
                        # if it's not already there
                        e.set_pos(rdr.fname(), rdr.line())
                        raise e

            except ConfigError as e:
                # Add file name and line number information to the exception
                # if it's not already there
                if rdr:
                    e.set_pos(rdr.fname(), rdr.line())
                raise e

            Settings.loaded = True
