from backend.utils.command_safety import command_pattern_matches, first_matching_command_pattern


def test_dangerous_command_pattern_matches_full_token_only():
    command = 'cat /proc/cpuinfo | grep "model name" | head -1'

    assert command_pattern_matches(command.lower(), "del") is False
    assert command_pattern_matches(command.lower(), "rm") is False


def test_dangerous_command_pattern_matches_real_dangerous_phrase():
    command = "systemctl restart mysqld"

    assert command_pattern_matches(command.lower(), "systemctl restart") is True


def test_first_matching_command_pattern_finds_context_builder_block_rule():
    command = "echo test ; cp /tmp/a /tmp/b"

    assert first_matching_command_pattern(command, ["kill -9", "cp", "chmod"]) == "cp"
