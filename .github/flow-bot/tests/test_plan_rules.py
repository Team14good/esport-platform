from dataclasses import replace

from plan_rules import (
    StoryEntry,
    all_done,
    next_story,
    parse_batch_order,
    parse_dependencies,
    parse_members,
    parse_sprint_status,
    started_stories,
)


def with_status(entries, changes):
    return [replace(e, status=changes[e.story_id]) if e.story_id in changes else e for e in entries]


def test_parse_real_sprint_status(sprint_text):
    entries = {e.story_id: e for e in parse_sprint_status(sprint_text)}
    assert entries["1.6"] == StoryEntry("1-6-通知中心", "1.6", "backlog", "A")
    assert entries["1.7"].status == "done" and entries["1.7"].owner == "A"
    assert entries["2.6"].owner == "B"
    mine = [e.story_id for e in entries.values() if e.owner == "A" and e.status == "backlog"]
    assert sorted(mine) == ["1.6", "2.8", "3.9", "4.7"]


def test_parse_members(contributing_text):
    members = parse_members(contributing_text)
    assert members["max930000"] == "A"
    assert members["OG-Matcha"] == "D"


def test_parse_dependencies(contributing_text):
    deps = parse_dependencies(contributing_text)
    assert deps["3.9"] == {"1.6", "2.6"}
    assert deps["4.5"] == {"3.7", "3.8"}


def test_batch_order(contributing_text):
    assert parse_batch_order(contributing_text, "A") == ["1.6", "4.7", "3.9", "2.8"]
    assert parse_batch_order(contributing_text, "D") == ["4.2", "5.7", "4.5"]


def test_first_story_is_1_6(entries, deps, order_a):
    assert next_story(entries, "A", deps, order_a, started=set()) == "1.6"


def test_started_story_not_picked(entries, deps, order_a):
    assert next_story(entries, "A", deps, order_a, started={"1.6"}) == "4.7"


def test_blocked_3_9_skipped_for_2_8(entries, deps, order_a):
    e = with_status(entries, {"1.6": "done"})
    assert next_story(e, "A", deps, order_a, started={"4.7"}) == "2.8"


def test_3_9_after_deps_done(entries, deps, order_a):
    e = with_status(entries, {"1.6": "done", "2.6": "done"})
    assert next_story(e, "A", deps, order_a, started={"4.7"}) == "3.9"


def test_all_done(entries):
    e = with_status(entries, {s: "done" for s in ["1.6", "4.7", "3.9", "2.8"]})
    assert all_done(e, "A")
    assert next_story(e, "A", {}, [], set()) is None


def test_not_all_done(entries):
    assert not all_done(entries, "A")


def test_started_stories():
    assert started_stories(["story/1-6-notification-center", "main", "story/4-7"]) == {"1.6", "4.7"}
