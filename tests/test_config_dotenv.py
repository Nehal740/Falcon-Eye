"""The .env file is read when the backend runs directly (and never during tests)."""

import os

import config


def test_dotenv_values_are_loaded_but_real_environment_wins(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('﻿# comment\nFE_TEST_A=1\nFE_TEST_B="quoted value"\n'
                   "FE_TEST_C=Falcon Eye <a@b.com>\nFE_TEST_D=ab#cd=ef\n FE_TEST_E = spaced \n"
                   "FE_TEST_F=from-file\nnot a setting line\n", encoding="utf-8")
    for name in "ABCDEF":
        monkeypatch.delenv(f"FE_TEST_{name}", raising=False)
    monkeypatch.setenv("FE_TEST_F", "from-server")
    monkeypatch.delenv("FALCON_EYE_NO_DOTENV", raising=False)
    config._load_dotenv(str(env))
    try:
        assert os.environ["FE_TEST_A"] == "1"
        assert os.environ["FE_TEST_B"] == "quoted value"
        assert os.environ["FE_TEST_C"] == "Falcon Eye <a@b.com>"
        assert os.environ["FE_TEST_D"] == "ab#cd=ef"
        assert os.environ["FE_TEST_E"] == "spaced"
        assert os.environ["FE_TEST_F"] == "from-server"
    finally:
        for name in "ABCDE":
            os.environ.pop(f"FE_TEST_{name}", None)


def test_the_switch_turns_loading_off(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("FE_TEST_OFF=1\n", encoding="utf-8")
    monkeypatch.delenv("FE_TEST_OFF", raising=False)
    monkeypatch.setenv("FALCON_EYE_NO_DOTENV", "1")
    config._load_dotenv(str(env))
    assert "FE_TEST_OFF" not in os.environ


def test_missing_file_is_fine(tmp_path):
    config._load_dotenv(str(tmp_path / "nope.env"))


def test_database_urls_from_hosts_are_normalised():
    from config import normalize_database_url as n
    assert n("postgres://u:p@h:5432/db") == "postgresql+psycopg://u:p@h:5432/db"
    assert n(" postgresql://u:p@h/db ") == "postgresql+psycopg://u:p@h/db"
    assert n("postgresql+psycopg://x") == "postgresql+psycopg://x"
    assert n("sqlite://") == "sqlite://" and n(None) is None
