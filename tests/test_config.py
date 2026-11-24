import json

import pytest

from steam_nick_changer.config import ConfigError, State, load_config, load_state, save_state
from steam_nick_changer.update import parse_version

VALID = """
mode = "queue"
latin_lookalikes = true
once_a_day = false
warn_long_nicknames = true
nicknames = ["a", "b"]
"""


def write(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_config(tmp_path):
    cfg = load_config(write(tmp_path, VALID))
    assert cfg.mode == "queue"
    assert cfg.nicknames == ("a", "b")


@pytest.mark.parametrize(
    "old, new",
    [
        ('mode = "queue"', 'mode = "other"'),
        ("once_a_day = false", 'once_a_day = "no"'),
        ('nicknames = ["a", "b"]', "nicknames = []"),
        ('nicknames = ["a", "b"]', 'nicknames = ["a", "a"]'),
        ('nicknames = ["a", "b"]', "nicknames = [1]"),
        ("latin_lookalikes = true\n", ""),
        ("mode = ", "mode "),
    ],
)
def test_invalid_config(tmp_path, old, new):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, VALID.replace(old, new)))


def test_state_roundtrip_and_missing(tmp_path):
    path = tmp_path / "state.json"
    assert load_state(path) == State()
    state = State("a", ["a", "b"], "2026-11-24T10:00:00")
    save_state(state, path)
    assert load_state(path) == state


def test_damaged_state(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"current_nickname": 5}), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_state(path)


def test_changed_today():
    assert not State().changed_today()
    assert not State(last_change="2000-01-01T00:00:00").changed_today()


def test_parse_version():
    assert parse_version("v2.0.1") > parse_version("2.0.0")
    assert parse_version("v2.10.0") > parse_version("v2.9.9")
