from pathlib import Path

import pytest

from backend import version


@pytest.mark.unit
def test_load_build_info_missing_file_returns_empty(tmp_path: Path):
    missing = tmp_path / "no-such-build-info"
    assert version.load_build_info(missing) == {}


@pytest.mark.unit
def test_load_build_info_parses_key_value_lines(tmp_path: Path):
    p = tmp_path / ".build-info"
    p.write_text(
        "# comment\n"
        "FOO=bar\n"
        "EMPTY=\n"
        " spaced = trimmed \n"
        "noequalsline\n",
        encoding="utf-8",
    )
    data = version.load_build_info(p)
    assert data["FOO"] == "bar"
    assert data["EMPTY"] == ""
    assert data["spaced"] == "trimmed"
    assert "noequalsline" not in data


@pytest.mark.unit
def test_app_version_is_non_empty_string():
    assert isinstance(version.APP_VERSION, str)
    assert len(version.APP_VERSION) > 0
