import os

from src import env_utils


def test_load_dotenv_does_not_override_existing_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SOME_EXISTING_KEY", "already-set")
    fake_root = tmp_path
    (fake_root / ".env").write_text("SOME_EXISTING_KEY=from-dotenv\nNEW_KEY=from-dotenv\n")
    monkeypatch.setattr(env_utils, "ROOT", fake_root)
    env_utils.load_dotenv()
    assert os.environ["SOME_EXISTING_KEY"] == "already-set"
    assert os.environ["NEW_KEY"] == "from-dotenv"
    del os.environ["NEW_KEY"]


def test_load_dotenv_missing_file_is_a_noop(monkeypatch, tmp_path):
    monkeypatch.setattr(env_utils, "ROOT", tmp_path)
    env_utils.load_dotenv()  # should not raise


def test_load_dotenv_ignores_comments_and_blank_lines(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("# a comment\n\nANOTHER_NEW_KEY=value\n")
    monkeypatch.setattr(env_utils, "ROOT", tmp_path)
    env_utils.load_dotenv()
    assert os.environ["ANOTHER_NEW_KEY"] == "value"
    del os.environ["ANOTHER_NEW_KEY"]
