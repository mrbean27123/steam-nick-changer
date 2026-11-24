# Steam Nick Changer

Changes your Steam profile name to the next nickname from your list and clears the profile
name history. One run changes the name once; schedule it (Task Scheduler) or start it by hand.

Windows only. Needs Microsoft Edge for the first login (it is preinstalled on Windows 11); no
browser is downloaded.

## Install

Download `steam-nick-changer.exe` from the
[Releases](https://github.com/mrbean27123/steam-nick-changer/releases/latest) page and put it
in a folder of its own. The program keeps its files next to the exe.

The exe updates itself: on start it checks the latest release and replaces itself when a newer
one exists. A failed check is written to the log and ignored.

## Configure

Run the exe once. It creates `config.toml` next to itself and asks you to edit it
([the template](src/steam_nick_changer/config.example.toml) explains every option):

| Option | Meaning |
| --- | --- |
| `mode` | `"queue"`: go through a shuffled list; `"random"`: any nickname except the current one |
| `latin_lookalikes` | replace Cyrillic letters with identical-looking Latin ones to fit the byte limit |
| `once_a_day` | change the name at most once per calendar day |
| `warn_long_nicknames` | warn about nicknames over the 32-byte Steam limit (UTF-8) |
| `nicknames` | the list to pick from, unique entries |

`state.json` (current nickname, queue, time of the last change) is written by the program.
Delete it to start the queue over.

## First login

On the first run, or when the saved session expires, an Edge window opens on the Steam login
page. Log in there; the window closes by itself and the session cookies are saved to
`auth_state.json`. The password is never stored. Treat `auth_state.json` like a password and
do not share it.

## Command line

`steam-nick-changer.exe --dry-run` does everything except the two requests that change data
(saving the name and clearing the history) and writes the request it would send to the log (the session id is hidden).

Errors are shown in a message box; details are in `steam-nick-changer.log`.

## Development

Needs [uv](https://docs.astral.sh/uv/getting-started/installation/).

```
uv sync
uv run poe dev     # run the app (config.toml and state.json go to the current directory)
uv run poe dry     # run with --dry-run
uv run poe lint    # ruff check and format check
uv run poe fmt     # ruff format and autofix
uv run poe test    # pytest
uv run poe build   # dist/steam-nick-changer.exe
```

## Release

With a clean working tree on `main`:

```
uv run poe release          # 1.0.0 -> 1.0.1
uv run poe release minor    # 1.0.1 -> 1.1.0
```

It bumps the version in `pyproject.toml` and `uv.lock`, commits `chore(release): v<version>`,
creates the annotated tag `v<version>` and pushes both.

The `release` workflow builds the exe on a `v*` tag, checks that the tag equals the version in
`pyproject.toml`, and publishes the release with `steam-nick-changer.exe` attached. The asset
name is what the updater looks for.
