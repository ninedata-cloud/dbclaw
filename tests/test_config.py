from pathlib import Path

import pytest

from backend.config import ENV_FILE, Settings


@pytest.mark.unit
def test_settings_env_file_is_project_root_even_from_child_directory(monkeypatch, tmp_path):
    child_dir = tmp_path / "scripts"
    child_dir.mkdir()
    child_env = child_dir / ".env"
    child_env.write_text(
        "DATABASE_URL=postgresql+asyncpg://wrong:wrong@localhost:5432/wrong\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(child_dir)

    settings = Settings()

    assert Path(Settings.model_config["env_file"]) == ENV_FILE
    assert settings.database_url != "postgresql+asyncpg://wrong:wrong@localhost:5432/wrong"
