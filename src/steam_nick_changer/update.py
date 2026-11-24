"""Self-update of the frozen exe from the latest GitHub release."""

import logging
import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

REPO = "mrbean27123/steam-nick-changer"
ASSET = "steam-nick-changer.exe"
TIMEOUT = 10.0
DOWNLOAD_TIMEOUT = 120.0


def remove_old_exe() -> None:
    """Delete the exe renamed by the previous update, which could not be removed while running."""
    exe = Path(sys.executable)
    exe.with_name(exe.name + ".old").unlink(missing_ok=True)


def parse_version(text: str) -> tuple[int, ...]:
    """Turn 'v1.2.3' or '1.2.3' into (1, 2, 3)."""
    return tuple(int(part) for part in text.removeprefix("v").split("."))


def update_and_restart() -> None:
    """Replace the running exe with a newer release and start it; return if there is none.

    The running exe is renamed to <exe>.old (Windows allows it) and the download is moved to
    its place. If anything fails after the rename, the rename is rolled back. On success this
    process exits.
    """
    release = httpx.get(
        f"https://api.github.com/repos/{REPO}/releases/latest",
        headers={"Accept": "application/vnd.github+json"},
        timeout=TIMEOUT,
    )
    release.raise_for_status()
    data = release.json()
    if parse_version(data["tag_name"]) <= parse_version(version("steam-nick-changer")):
        return

    asset = next(a for a in data["assets"] if a["name"] == ASSET)
    exe = Path(sys.executable)
    new, old = exe.with_name(exe.name + ".new"), exe.with_name(exe.name + ".old")
    log.info("Updating to %s.", data["tag_name"])

    try:
        with httpx.stream(
            "GET", asset["browser_download_url"], follow_redirects=True, timeout=DOWNLOAD_TIMEOUT
        ) as response:
            response.raise_for_status()
            with new.open("wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
        if new.stat().st_size != asset["size"]:
            raise RuntimeError("The downloaded update has a wrong size.")

        os.replace(exe, old)
        try:
            os.replace(new, exe)
        except OSError:
            os.replace(old, exe)
            raise
    except BaseException:
        new.unlink(missing_ok=True)
        raise

    # Without the reset the child would reuse the temp files of this process, which are
    # deleted when it exits (https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html).
    subprocess.Popen([exe, *sys.argv[1:]], env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})
    sys.exit(0)
