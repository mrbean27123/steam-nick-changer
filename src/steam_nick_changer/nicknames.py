"""Nickname selection and the Cyrillic to Latin look-alike replacement."""

import random

# Steam keeps a persona name in at most this many bytes of UTF-8 and silently truncates the
# rest (measured by a third party, not documented by Valve):
# https://github.com/ImLTHQ/SteamAccountManager
MAX_NAME_BYTES = 32

_LOOKALIKES = str.maketrans(
    {
        "А": "A",
        "В": "B",
        "Е": "E",
        "З": "3",
        "К": "K",
        "М": "M",
        "Н": "H",
        "О": "O",
        "Р": "P",
        "С": "C",
        "Т": "T",
        "Х": "X",
        "І": "I",
        "а": "a",
        "е": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "у": "y",
        "х": "x",
        "і": "i",
    }
)


def replace_lookalikes(name: str) -> str:
    """Replace Cyrillic letters with identical-looking Latin ones to save bytes."""
    return name.translate(_LOOKALIKES)


def name_bytes(name: str) -> int:
    """Length of a name in UTF-8 bytes, the unit of the Steam limit."""
    return len(name.encode("utf-8"))


def pick_random(nicknames: list[str], current: str | None) -> str:
    """Pick a random nickname other than the current one.

    With a single nickname there is nothing else to pick, so it is returned as is.

    Raises:
        ValueError: if the list is empty.
    """
    if not nicknames:
        raise ValueError("The nickname list is empty.")
    candidates = [n for n in nicknames if n != current]
    return random.choice(candidates or nicknames)


def pick_from_queue(
    nicknames: list[str], queue: list[str], current: str | None
) -> tuple[str, list[str]]:
    """Take the nickname after the current one in a shuffled queue.

    The queue is kept in sync with the config list: removed nicknames are dropped (the current
    one stays as an anchor until the queue is exhausted) and new ones are appended in random
    order. When the queue is exhausted, its first and second halves are reshuffled separately,
    so the last nicknames of one pass do not come up first in the next. The current nickname
    is never returned while the list holds another one.

    Returns:
        The next nickname and the updated queue to store in the state.

    Raises:
        ValueError: if the list is empty.
    """
    if not nicknames:
        raise ValueError("The nickname list is empty.")

    if current not in queue:
        queue = random.sample(nicknames, len(nicknames))
        # A fresh shuffle may start with the current nickname, which must not repeat.
        if queue[0] == current and len(queue) > 1:
            return queue[1], queue
        return queue[0], queue

    if sorted(nicknames) != sorted(queue):
        queue = [n for n in queue if n in nicknames or n == current]
        added = [n for n in nicknames if n not in queue]
        random.shuffle(added)
        queue = queue + added

    index = queue.index(current)
    if index + 1 < len(queue):
        return queue[index + 1], queue

    # Exhausted: start a new pass over the config list only, so a removed current nickname
    # does not survive in the queue.
    queue = [n for n in queue if n in nicknames]
    middle = len(queue) // 2
    first, second = queue[:middle], queue[middle:]
    random.shuffle(first)
    random.shuffle(second)
    queue = first + second
    return queue[0], queue
