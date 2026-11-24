"""App directory, the user-edited config.toml and the app-written state.json."""

import json
import sys
import tomllib
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from importlib import resources
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
# Next to the exe when frozen (portable, the user edits config.toml there), else the cwd.
APP_DIR = Path(sys.executable).parent if FROZEN else Path.cwd()

CONFIG_PATH = APP_DIR / "config.toml"
STATE_PATH = APP_DIR / "state.json"
AUTH_STATE_PATH = APP_DIR / "auth_state.json"

MODES = ("random", "queue")


class ConfigError(Exception):
    """config.toml or state.json is missing a value or holds a wrong one."""


@dataclass(frozen=True)
class Config:
    """Settings from config.toml. The app never writes this file."""

    mode: str
    latin_lookalikes: bool
    once_a_day: bool
    warn_long_nicknames: bool
    nicknames: tuple[str, ...]


@dataclass
class State:
    """What the app remembers between runs, stored in state.json."""

    current_nickname: str | None = None
    queue: list[str] = field(default_factory=list)
    last_change: str | None = None

    def changed_today(self) -> bool:
        """Whether the last change happened on today's local date."""
        return (
            self.last_change is not None
            and datetime.fromisoformat(self.last_change).date() == date.today()
        )


def write_example_config(path: Path = CONFIG_PATH) -> None:
    """Copy the bundled config.example.toml to the given path."""
    example = resources.files("steam_nick_changer") / "config.example.toml"
    path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")


def load_config(path: Path = CONFIG_PATH) -> Config:
    """Read and validate config.toml.

    Raises:
        ConfigError: if the file is not valid TOML or a value is missing or has a wrong type.
    """
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path.name} is not valid TOML: {e}") from e

    for key in ("latin_lookalikes", "once_a_day", "warn_long_nicknames"):
        if not isinstance(raw.get(key), bool):
            raise ConfigError(f'{path.name}: "{key}" must be true or false.')

    mode = raw.get("mode")
    if mode not in MODES:
        raise ConfigError(f'{path.name}: "mode" must be one of {", ".join(MODES)}.')

    nicknames = raw.get("nicknames")
    if (
        not isinstance(nicknames, list)
        or not nicknames
        or not all(isinstance(n, str) and n.strip() for n in nicknames)
    ):
        raise ConfigError(
            f'{path.name}: "nicknames" must be a non-empty list of non-empty strings.'
        )
    if len(set(nicknames)) != len(nicknames):
        raise ConfigError(f'{path.name}: "nicknames" must not contain duplicates.')

    return Config(
        mode=mode,
        latin_lookalikes=raw["latin_lookalikes"],
        once_a_day=raw["once_a_day"],
        warn_long_nicknames=raw["warn_long_nicknames"],
        nicknames=tuple(nicknames),
    )


def load_state(path: Path = STATE_PATH) -> State:
    """Read state.json; a missing file gives an empty state.

    Raises:
        ConfigError: if the file is unreadable or has wrong types. It is not reset silently,
            so the queue is not lost by accident.
    """
    if not path.exists():
        return State()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        state = State(raw["current_nickname"], raw["queue"], raw["last_change"])
        if state.last_change is not None:
            datetime.fromisoformat(state.last_change)
    except (ValueError, KeyError, TypeError) as e:
        raise ConfigError(f"{path.name} is damaged ({e!r}). Fix or delete it.") from e
    if not (
        (state.current_nickname is None or isinstance(state.current_nickname, str))
        and isinstance(state.queue, list)
        and all(isinstance(n, str) for n in state.queue)
    ):
        raise ConfigError(f"{path.name} is damaged: wrong value types. Fix or delete it.")
    return state


def save_state(state: State, path: Path = STATE_PATH) -> None:
    """Write state.json."""
    path.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8")
