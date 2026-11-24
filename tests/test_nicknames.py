import random

import pytest

from steam_nick_changer.nicknames import (
    name_bytes,
    pick_from_queue,
    pick_random,
    replace_lookalikes,
)

NAMES = ["a", "b", "c", "d", "e"]


def test_replace_lookalikes_swaps_cyrillic_only():
    assert replace_lookalikes("АВЕЗКМНОРСТХІ") == "ABE3KMHOPCTXI"
    assert replace_lookalikes("аеорсухі") == "aeopcyxi"
    assert replace_lookalikes("Latin 123 Ж") == "Latin 123 Ж"


def test_replacement_saves_bytes():
    assert name_bytes("оо") == 4
    assert name_bytes(replace_lookalikes("оо")) == 2


def test_pick_random_excludes_current():
    for _ in range(50):
        assert pick_random(NAMES, "c") != "c"


def test_pick_random_current_not_in_list():
    assert pick_random(NAMES, "zzz") in NAMES
    assert pick_random(NAMES, None) in NAMES


def test_pick_random_single_and_empty():
    assert pick_random(["x"], "x") == "x"
    with pytest.raises(ValueError):
        pick_random([], None)


def test_queue_walks_every_nickname_once_per_pass():
    queue: list[str] = []
    current = None
    seen = []
    for _ in range(len(NAMES)):
        current, queue = pick_from_queue(NAMES, queue, current)
        seen.append(current)
    assert sorted(seen) == NAMES


def test_queue_never_repeats_current():
    queue: list[str] = []
    current = None
    for seed in range(300):
        random.seed(seed)
        nxt, queue = pick_from_queue(NAMES, queue, current)
        assert nxt != current
        assert nxt in NAMES
        current = nxt


def test_queue_takes_next_after_current():
    assert pick_from_queue(NAMES, ["c", "a", "b", "d", "e"], "a") == (
        "b",
        ["c", "a", "b", "d", "e"],
    )


def test_queue_exhausted_reshuffles_halves_separately():
    queue = ["a", "b", "c", "d", "e", "f"]
    nxt, new = pick_from_queue(list(queue), queue, "f")
    assert sorted(new[:3]) == ["a", "b", "c"]
    assert sorted(new[3:]) == ["d", "e", "f"]
    assert nxt == new[0] and nxt != "f"


def test_queue_syncs_with_config():
    # "b" was removed from the config, "z" was added.
    nxt, new = pick_from_queue(["a", "c", "z"], ["a", "b", "c"], "a")
    assert nxt == "c"
    assert new == ["a", "c", "z"]


def test_queue_keeps_removed_current_then_drops_it():
    # The current nickname is no longer configured: it anchors the position.
    nxt, new = pick_from_queue(["a", "c"], ["a", "gone", "c"], "gone")
    assert nxt == "c"
    assert "gone" in new
    # At the end of the pass it is dropped, so it can never be picked again.
    nxt, new = pick_from_queue(["a", "c"], new, "c")
    assert "gone" not in new
    assert sorted(new) == ["a", "c"]


def test_queue_current_missing_from_queue_rebuilds():
    nxt, new = pick_from_queue(NAMES, ["a", "b"], "zzz")
    assert sorted(new) == NAMES
    assert nxt == new[0]


def test_queue_fresh_shuffle_skips_current():
    for seed in range(100):
        random.seed(seed)
        nxt, new = pick_from_queue(NAMES, [], "a")
        assert nxt != "a"
        assert sorted(new) == NAMES


def test_queue_single_and_empty():
    assert pick_from_queue(["x"], [], "x") == ("x", ["x"])
    assert pick_from_queue(["x"], ["x"], "x") == ("x", ["x"])
    with pytest.raises(ValueError):
        pick_from_queue([], [], None)
