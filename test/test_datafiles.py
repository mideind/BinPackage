"""Where islenska finds its data files (basics.resolve_data_dir()).

The data files come from islenska's own resources directory if it holds
any of them, as in a source checkout where they were built, and otherwise from the
islenska-data package, which must have the data format that this version of
islenska reads.
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


def test_own_data_preferred(tmp_path: Path) -> None:
    own = _dir_with_data(tmp_path / "own")
    pkg = _dir_with_data(tmp_path / "pkg")
    assert resolve_data_dir(own, _package(pkg)) == own
    assert resolve_data_dir(own, None) == own
    # Even if the data package has another format: it is not used
    assert resolve_data_dir(own, _package(pkg, "Greynir 06.00.00")) == own


def test_own_dawgs_suffice(tmp_path: Path) -> None:
    # As while tools/binpack.py runs: the DAWGs are built, compressed.bin
    # is not yet, and the compounder must read the new DAWGs
    own = tmp_path / "own"
    own.mkdir()
    (own / DATA_FILES[1]).write_bytes(b"")
    assert resolve_data_dir(own, None) == own
    assert resolve_data_dir(own, _package(_dir_with_data(tmp_path / "pkg"))) == own


def test_data_package_used_without_own_data(tmp_path: Path) -> None:
    # As in an installed wheel, whose resources directory has no data files
    own = tmp_path / "own"
    own.mkdir()
    pkg = _dir_with_data(tmp_path / "pkg")
    assert resolve_data_dir(own, _package(pkg)) == pkg


def test_missing_data_is_an_error(tmp_path: Path) -> None:
    own = tmp_path / "own"
    own.mkdir()
    pkg = _dir_with_data(tmp_path / "pkg")
    empty = tmp_path / "empty"
    empty.mkdir()
    # No data package
    with pytest.raises(RuntimeError, match="install the islenska-data package"):
        resolve_data_dir(own, None)
    # A data package in another format
    with pytest.raises(RuntimeError, match="data format 'Greynir 06.00.00'"):
        resolve_data_dir(own, _package(pkg, "Greynir 06.00.00"))
    # A data package without files (an editable install with nothing staged)
    with pytest.raises(RuntimeError, match="holds no data files"):
        resolve_data_dir(own, _package(empty))


def test_data_dir_is_cached() -> None:
    assert data_dir() is data_dir()
