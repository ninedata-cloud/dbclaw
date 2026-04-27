import pytest

from backend.utils.command_safety import (
    command_pattern_matches,
    extract_base_command,
    first_matching_command_pattern,
    looks_clearly_read_only_command,
    split_command_segments,
)


@pytest.mark.unit
def test_split_command_segments_splits_on_operators():
    cmd = "df -h && ps aux | head"
    segs = split_command_segments(cmd)
    assert segs == ["df -h", "ps aux", "head"]


@pytest.mark.unit
def test_extract_base_command_strips_redirection_prefix():
    assert extract_base_command("2>/dev/null df -h") == "df"
    assert extract_base_command("  uptime ") == "uptime"


@pytest.mark.unit
def test_command_pattern_matches_word_boundaries():
    assert command_pattern_matches("sudo rm -rf /tmp", "rm") is True
    assert command_pattern_matches("echo armchair", "rm") is False
    assert command_pattern_matches("echo >> log", ">>") is True


@pytest.mark.unit
def test_looks_clearly_read_only_command_single_and_chained():
    assert looks_clearly_read_only_command("df -h") is True
    assert looks_clearly_read_only_command("df -h && uptime") is True
    assert looks_clearly_read_only_command("df -h && rm x") is False


@pytest.mark.unit
def test_first_matching_command_pattern_returns_first_hit():
    patterns = ["rm", "shutdown"]
    assert first_matching_command_pattern("echo ok", patterns) is None
    assert first_matching_command_pattern("shutdown now", patterns) == "shutdown"
    assert first_matching_command_pattern("rm -rf /", patterns) == "rm"
