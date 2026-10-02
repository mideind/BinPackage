"""Where islenska finds its data files (basics.resolve_data_dir()).

The data files come from the islenska-data package when it is installed and
has the data format that this version of islenska reads, and otherwise from
islenska's own resources directory.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from islenska.basics import (
    BIN_COMPRESSED_FILE,
    BIN_COMPRESSOR_VERSION,
    DATA_FILES,
    data_dir,
    data_file,
    resolve_data_dir,
)

FORMAT = BIN_COMPRESSOR_VERSION.decode("ascii")


def _dir_with_data(path: Path) -> Path:
    path.mkdir()
    (path / BIN_COMPRESSED_FILE).write_bytes(BIN_COMPRESSOR_VERSION)
    return path


def _package(path: Path, fmt: str = FORMAT) -> SimpleNamespace:
    return SimpleNamespace(FORMAT=fmt, data_dir=lambda: path)


def test_the_data_files_are_found() -> None:
    for name in DATA_FILES:
        assert Path(data_file(name)).is_file(), name
    assert Path(data_file(BIN_COMPRESSED_FILE)).read_bytes()[0:16] == BIN_COMPRESSOR_VERSION


def test_data_package_preferred(tmp_path: Path) -> None:
    own = _dir_with_data(tmp_path / "own")
    pkg = _dir_with_data(tmp_path / "pkg")
    assert resolve_data_dir(own, _package(pkg)) == pkg
    # Without the data package, islenska's own files are used
    assert resolve_data_dir(own, None) == own


def test_data_package_without_files_is_skipped(tmp_path: Path) -> None:
    # E.g. an editable install of islenska-data with nothing staged into it
    own = _dir_with_data(tmp_path / "own")
    empty = tmp_path / "pkg"
    empty.mkdir()
    assert resolve_data_dir(own, _package(empty)) == own


def test_data_package_with_another_format(tmp_path: Path) -> None:
    own = _dir_with_data(tmp_path / "own")
    pkg = _dir_with_data(tmp_path / "pkg")
    # islenska's own files, if any, are used instead
    assert resolve_data_dir(own, _package(pkg, "Greynir 06.00.00")) == own
    # and if there are none, the mismatch is an error
    nothing = tmp_path / "nothing"
    nothing.mkdir()
    with pytest.raises(RuntimeError, match="islenska-data"):
        resolve_data_dir(nothing, _package(pkg, "Greynir 06.00.00"))


def test_data_dir_is_cached() -> None:
    assert data_dir() is data_dir()
