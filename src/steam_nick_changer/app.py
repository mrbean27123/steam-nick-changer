"""Entry point: one run picks the next nickname and applies it to the Steam profile."""

import argparse
import ctypes
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

from steam_nick_changer import config, nicknames, steam
from steam_nick_changer.config import APP_DIR, AUTH_STATE_PATH, FROZEN, Config, State

TITLE = "Steam Nick Changer"
LOG_PATH = APP_DIR / "steam-nick-changer.log"
MB_ICONERROR = 0x10

log = logging.getLogger("steam_nick_changer")


def show_message(text: str) -> None:
    """Show a modal error box; the frozen exe has no console to print to."""
    ctypes.windll.user32.MessageBoxW(0, text, TITLE, MB_ICONERROR)


def setup_logging() -> None:
    """Log to a small rotating file, and to stderr when running from source."""
    handlers: list[logging.Handler] = [
        RotatingFileHandler(LOG_PATH, maxBytes=200_000, backupCount=1, encoding="utf-8")
    ]
    if not FROZEN:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def warn_long_nicknames(cfg: Config) -> None:
    """Show a box listing the nicknames that exceed the Steam byte limit."""
    too_long = []
    for name in cfg.nicknames:
        shown = nicknames.replace_lookalikes(name) if cfg.latin_lookalikes else name
        size = nicknames.name_bytes(shown)
        if size > nicknames.MAX_NAME_BYTES:
            too_long.append(f"{shown} {size}")
    if too_long:
        log.warning("Nicknames over the byte limit: %s", too_long)
        show_message(
            f"Nicknames over {nicknames.MAX_NAME_BYTES} bytes: "
            f"{len(too_long)}/{len(cfg.nicknames)}\n\n" + "\n".join(too_long)
        )


def pick_nickname(cfg: Config, state: State) -> tuple[str, list[str]]:
    """Choose the next nickname by the configured mode; returns it and the new queue."""
    names = list(cfg.nicknames)
    if cfg.mode == "random":
        return nicknames.pick_random(names, state.current_nickname), state.queue
    return nicknames.pick_from_queue(names, state.queue, state.current_nickname)


def apply_to_steam(name: str, *, dry_run: bool) -> None:
    """Change the name on Steam, logging in first when the saved session is not valid."""
    try:
        with steam.open_client(AUTH_STATE_PATH) as client:
            steam.change_name(client, name, dry_run=dry_run)
            steam.save_cookies(client, AUTH_STATE_PATH)
        return
    except steam.NotLoggedIn as e:
        log.info("Login required: %s", e)

    # Imported here so a run with a valid session does not load Playwright.
    from steam_nick_changer.login import login

    login(AUTH_STATE_PATH)
    with steam.open_client(AUTH_STATE_PATH) as client:
        steam.change_name(client, name, dry_run=dry_run)
        steam.save_cookies(client, AUTH_STATE_PATH)


def run(dry_run: bool) -> None:
    """One full run: config, nickname choice, Steam change, state save."""
    if not config.CONFIG_PATH.exists():
        config.write_example_config()
        show_message(f"Created {config.CONFIG_PATH}.\nEdit it, then run the program again.")
        return

    cfg = config.load_config()
    state = config.load_state()

    if cfg.once_a_day and state.changed_today():
        log.info("The name was already changed today.")
        return
    if cfg.warn_long_nicknames:
        warn_long_nicknames(cfg)

    picked, queue = pick_nickname(cfg, state)
    name = nicknames.replace_lookalikes(picked) if cfg.latin_lookalikes else picked
    log.info("Next nickname: %r (sent as %r)", picked, name)

    apply_to_steam(name, dry_run=dry_run)
    if dry_run:
        return

    # The state moves on only after Steam accepted the change.
    state.current_nickname = picked
    state.queue = queue
    state.last_change = datetime.now().isoformat(timespec="seconds")
    config.save_state(state)


def main() -> None:
    """Parse arguments, update the exe, run, and report errors in a message box."""
    parser = argparse.ArgumentParser(description="Change the Steam profile name.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="do everything except the requests that change data, and log the payload",
    )
    args = parser.parse_args()
    setup_logging()

    if FROZEN:
        from steam_nick_changer import update

        try:
            update.remove_old_exe()
            update.update_and_restart()
        except Exception:
            log.exception("Update check failed, continuing with the current version.")

    try:
        run(args.dry_run)
    except (config.ConfigError, steam.SteamError) as e:
        # These messages are written for the user, so the class name would only add noise.
        log.exception("Run failed.")
        show_message(f"{e}\n\nDetails: {LOG_PATH}")
        sys.exit(1)
    except Exception as e:
        log.exception("Run failed.")
        show_message(f"Unexpected error. {type(e).__name__}: {e}\n\nDetails: {LOG_PATH}")
        sys.exit(1)


if __name__ == "__main__":
    main()
