import pytest

from backend.utils.password_validator import validate_password_strength


@pytest.mark.unit
def test_validate_password_strength_empty_and_short():
    ok, msg = validate_password_strength("")
    assert ok is False and "不能为空" in msg

    ok, msg = validate_password_strength("Ab1!")
    assert ok is False and "8" in msg


@pytest.mark.unit
def test_validate_password_strength_missing_classes():
    ok, msg = validate_password_strength("abcdefgh1!")
    assert ok is False and "大写" in msg

    ok, msg = validate_password_strength("ABCDEFGH1!")
    assert ok is False and "小写" in msg

    ok, msg = validate_password_strength("Abcdefgh!")
    assert ok is False and "数字" in msg

    ok, msg = validate_password_strength("Abcdefgh1")
    assert ok is False and "特殊" in msg


@pytest.mark.unit
def test_validate_password_strength_accepts_strong_password():
    ok, msg = validate_password_strength("Str0ng!Pass")
    assert ok is True and msg == ""
