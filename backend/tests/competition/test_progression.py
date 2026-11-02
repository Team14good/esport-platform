import ast
import random
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from app.modules.competition import progression
from app.modules.competition.bracket import BracketPlan, assign, plan
from app.modules.competition.models import MatchOutcome, MatchStatus
from app.modules.competition.progression import (
    ConfirmWalkover,
    FillSlot,
    MatchState,
    Podium,
    StartForfeitClock,
    TournamentFinished,
    VoidMatch,
    advance,
    podium,
)

P = MatchOutcome.PLAYED
FF = MatchOutcome.FORFEIT
DF = MatchOutcome.DOUBLE_FORFEIT
DQ = MatchOutcome.DISQUALIFIED

States = dict[str, MatchState[str]]


class _NoShuffle:
    def shuffle(self, x: list[Any], /) -> None:
        pass


def _initial(pl: BracketPlan, rng: Any = None) -> States:
    """依抽籤結果建立初始狀態；不洗牌時隊伍依序為 A、B、C…"""
    teams = [chr(ord("A") + i) if i < 26 else f"T{i}" for i in range(pl.team_count)]
    return {
        am.match.code: MatchState(
            am.team_a_id, am.team_b_id, MatchStatus.SCHEDULED, None, None
        )
        for am in assign(teams, pl, rng or _NoShuffle())
    }


def _apply(states: States, changes: list[Any]) -> States:
    """套用變更，同時檢查不會重複填位、不會改動已確認或已取消的場次。"""
    out = dict(states)
    for ch in changes:
        if isinstance(ch, (StartForfeitClock, TournamentFinished)):
            continue
        st = out[ch.code]
        assert st.status not in (MatchStatus.CONFIRMED, MatchStatus.VOIDED), ch
        if isinstance(ch, FillSlot):
            assert st.team(ch.side) is None, f"{ch.code} 的 {ch.side} 被填兩次"
            out[ch.code] = (
                replace(st, team_a=ch.team)
                if ch.side == "a"
                else replace(st, team_b=ch.team)
            )
        elif isinstance(ch, ConfirmWalkover):
            assert st.team_a is None or st.team_b is None
            assert ch.winner in (st.team_a, st.team_b)
            out[ch.code] = replace(
                st,
                status=MatchStatus.CONFIRMED,
                outcome=MatchOutcome.WALKOVER,
                winner=ch.winner,
            )
        else:
            assert isinstance(ch, VoidMatch)
            out[ch.code] = replace(
                st, status=MatchStatus.VOIDED, outcome=None, winner=None
            )
    return out


def _confirm(
    states: States, code: str, outcome: MatchOutcome, winner: str | None
) -> States:
    out = dict(states)
    out[code] = replace(
        states[code], status=MatchStatus.CONFIRMED, outcome=outcome, winner=winner
    )
    return out


class _Run:
    """依序確認場次並套用變更，保留每次 advance 的回傳。"""

    def __init__(self, n: int) -> None:
        self.pl = plan(n)
        self.states = _initial(self.pl)

    def confirm(
        self, code: str, outcome: MatchOutcome, winner: str | None = None
    ) -> list[Any]:
        self.states = _confirm(self.states, code, outcome, winner)
        changes = advance(self.pl, self.states, code)
        self.states = _apply(self.states, changes)
        return changes


# 8 隊：M1(A,B) M2(C,D) M3(E,F) M4(G,H)；M5=M1/M2 勝者、M6=M3/M4 勝者；M7 決賽、M8 季軍賽
# 4 隊：M1(A,B) M2(C,D)；M3 決賽、M4 季軍賽
# 3 隊：M1(A,B)；M2 決賽，a 方由輪空的 C 直接入座


def test_layout_assumed_by_matrix() -> None:
    r = _Run(8)
    assert (r.states["M1"].team_a, r.states["M4"].team_b) == ("A", "H")
    assert r.pl.match("M8").is_third_place
    r3 = _Run(3)
    assert r3.states["M2"].team_a == "C"
    assert r3.pl.match("M2").next_code is None


def test_normal_advance_waits_for_other_side() -> None:
    r = _Run(8)
    assert r.confirm("M1", P, "A") == [FillSlot("M5", "a", "A")]


def test_next_match_complete_starts_clock() -> None:
    r = _Run(8)
    r.confirm("M1", P, "A")
    assert r.confirm("M2", P, "C") == [
        FillSlot("M5", "b", "C"),
        StartForfeitClock("M5"),
    ]


def test_semifinal_sends_loser_to_third_place() -> None:
    r = _Run(8)
    r.confirm("M1", P, "A")
    r.confirm("M2", P, "C")
    assert r.confirm("M5", P, "A") == [
        FillSlot("M7", "a", "A"),
        FillSlot("M8", "a", "C"),
    ]


def test_forfeit_loser_goes_to_third_place() -> None:
    r = _Run(4)
    assert r.confirm("M1", FF, "B") == [
        FillSlot("M3", "a", "B"),
        FillSlot("M4", "a", "A"),
    ]


def test_double_forfeit_gives_walkover_and_keeps_going() -> None:
    r = _Run(8)
    assert r.confirm("M1", DF) == []
    assert r.confirm("M2", P, "C") == [
        FillSlot("M5", "b", "C"),
        ConfirmWalkover("M5", "C"),
        FillSlot("M7", "a", "C"),
    ]


def test_both_empty_chain() -> None:
    r = _Run(8)
    r.confirm("M1", DF)
    assert r.confirm("M2", DF) == [ConfirmWalkover("M5", None), VoidMatch("M8")]
    assert r.states["M7"].team_a is None
    r.confirm("M3", P, "E")
    r.confirm("M4", P, "G")
    # M7 的 a 確定沒有隊伍，M6 一確認就輪空晉級；亞軍是冠軍那一側準決賽（M6）的敗隊
    assert r.confirm("M6", P, "E") == [
        FillSlot("M7", "b", "E"),
        ConfirmWalkover("M7", "E"),
        TournamentFinished(Podium("E", "G", None)),
    ]


def test_semifinal_double_forfeit_ends_tournament() -> None:
    r = _Run(4)
    assert r.confirm("M1", DF) == [VoidMatch("M4")]
    assert r.confirm("M2", P, "C") == [
        FillSlot("M3", "b", "C"),
        ConfirmWalkover("M3", "C"),
        TournamentFinished(Podium("C", "D", None)),
    ]
    assert r.states["M4"].status == MatchStatus.VOIDED
    assert (r.states["M4"].outcome, r.states["M4"].winner) == (None, None)


def test_normal_finish_final_first() -> None:
    r = _Run(4)
    r.confirm("M1", P, "A")
    r.confirm("M2", P, "C")
    assert r.confirm("M3", P, "C") == []
    assert r.confirm("M4", P, "B") == [TournamentFinished(Podium("C", "A", "B"))]


def test_normal_finish_third_place_first() -> None:
    r = _Run(4)
    r.confirm("M1", P, "A")
    r.confirm("M2", P, "C")
    assert r.confirm("M4", FF, "D") == []
    assert r.confirm("M3", FF, "A") == [TournamentFinished(Podium("A", "C", "D"))]


def test_no_third_place_with_three_teams() -> None:
    r = _Run(3)
    assert r.confirm("M1", P, "B") == [
        FillSlot("M2", "b", "B"),
        StartForfeitClock("M2"),
    ]
    assert r.confirm("M2", P, "C") == [TournamentFinished(Podium("C", "B", None))]


def test_final_disqualified_has_no_runner_up() -> None:
    r = _Run(4)
    r.confirm("M1", P, "A")
    r.confirm("M2", P, "C")
    r.confirm("M4", P, "D")
    assert r.confirm("M3", DQ, "A") == [TournamentFinished(Podium("A", None, "D"))]


def test_semifinal_disqualified_team_skips_third_place() -> None:
    r = _Run(4)
    assert r.confirm("M1", DQ, "A") == [FillSlot("M3", "a", "A")]
    assert r.confirm("M2", P, "C") == [
        FillSlot("M3", "b", "C"),
        StartForfeitClock("M3"),
        FillSlot("M4", "b", "D"),
        ConfirmWalkover("M4", "D"),
    ]
    assert r.confirm("M3", P, "C") == [TournamentFinished(Podium("C", "A", "D"))]


def test_final_walkover_without_loser_on_champion_side() -> None:
    r = _Run(8)
    r.confirm("M1", DF)
    r.confirm("M2", P, "C")  # M5 輪空，C 勝但沒有敗隊
    r.confirm("M3", DF)
    assert r.confirm("M4", DF) == [
        ConfirmWalkover("M6", None),
        ConfirmWalkover("M7", "C"),
        VoidMatch("M8"),
        TournamentFinished(Podium("C", None, None)),
    ]


def test_two_team_double_forfeit_final() -> None:
    r = _Run(2)
    assert r.confirm("M1", DF) == [TournamentFinished(Podium(None, None, None))]


def test_chain_completed_match_starts_clock() -> None:
    r = _Run(8)
    r.confirm("M3", P, "E")
    assert r.confirm("M4", P, "G") == [
        FillSlot("M6", "b", "G"),
        StartForfeitClock("M6"),
    ]
    assert r.confirm("M6", P, "E") == [
        FillSlot("M7", "b", "E"),
        FillSlot("M8", "b", "G"),
    ]
    assert r.confirm("M1", DF) == []
    assert r.confirm("M2", P, "C") == [
        FillSlot("M5", "b", "C"),
        ConfirmWalkover("M5", "C"),
        FillSlot("M7", "a", "C"),
        StartForfeitClock("M7"),
        ConfirmWalkover("M8", "G"),
    ]


def test_repeat_call_returns_no_duplicate_fill() -> None:
    r = _Run(8)
    r.confirm("M1", P, "A")
    r.confirm("M2", P, "C")
    assert advance(r.pl, r.states, "M2") == []
    assert advance(r.pl, r.states, "M1") == []
    r.confirm("M5", P, "A")
    assert advance(r.pl, r.states, "M5") == []


def test_repeat_call_on_final_only_finishes_again() -> None:
    r = _Run(4)
    r.confirm("M1", P, "A")
    r.confirm("M2", P, "C")
    r.confirm("M4", P, "B")
    r.confirm("M3", P, "A")
    assert advance(r.pl, r.states, "M3") == [TournamentFinished(Podium("A", "C", "B"))]
    assert advance(r.pl, r.states, "M1") == []


def test_unconfirmed_match_raises_value_error() -> None:
    r = _Run(8)
    with pytest.raises(ValueError):
        advance(r.pl, r.states, "M1")
    r.states = _confirm(r.states, "M1", P, "A")
    r.states["M1"] = replace(r.states["M1"], status=MatchStatus.APPEAL_WINDOW)
    with pytest.raises(ValueError):
        advance(r.pl, r.states, "M1")


def test_unknown_match_raises_key_error() -> None:
    r = _Run(8)
    with pytest.raises(KeyError):
        advance(r.pl, r.states, "M99")


def test_missing_state_raises_value_error() -> None:
    r = _Run(8)
    r.states = _confirm(r.states, "M1", P, "A")
    del r.states["M6"]
    with pytest.raises(ValueError, match="M6"):
        advance(r.pl, r.states, "M1")


@pytest.mark.parametrize(
    ("outcome", "winner"),
    [
        (P, None),
        (FF, None),
        (DQ, None),
        (P, "Z"),
        (DF, "A"),
        (MatchOutcome.WALKOVER, "Z"),
        (None, None),
    ],
)
def test_inconsistent_confirmed_state_raises(outcome, winner) -> None:
    r = _Run(8)
    r.states = _confirm(r.states, "M1", P, "A")
    r.states["M2"] = replace(
        r.states["M2"], status=MatchStatus.CONFIRMED, outcome=outcome, winner=winner
    )
    with pytest.raises(ValueError):
        advance(r.pl, r.states, "M1")


_BAD_STATES = {
    "played_missing_team": ("M6", MatchState("A", None, MatchStatus.CONFIRMED, P, "A")),
    "forfeit_missing_team": (
        "M6",
        MatchState(None, "B", MatchStatus.CONFIRMED, FF, "B"),
    ),
    "walkover_both_teams": (
        "M6",
        MatchState("E", "F", MatchStatus.CONFIRMED, MatchOutcome.WALKOVER, "E"),
    ),
    "walkover_winner_missing": (
        "M6",
        MatchState("E", None, MatchStatus.CONFIRMED, MatchOutcome.WALKOVER, None),
    ),
    "walkover_empty_with_winner": (
        "M6",
        MatchState(None, None, MatchStatus.CONFIRMED, MatchOutcome.WALKOVER, "E"),
    ),
    "voided_with_outcome": (
        "M8",
        MatchState(None, None, MatchStatus.VOIDED, MatchOutcome.WALKOVER, None),
    ),
    "voided_with_winner": ("M8", MatchState("C", None, MatchStatus.VOIDED, None, "C")),
    "voided_not_third_place": (
        "M6",
        MatchState(None, None, MatchStatus.VOIDED, None, None),
    ),
    "same_team_twice": ("M6", MatchState("E", "E", MatchStatus.SCHEDULED, None, None)),
}


@pytest.mark.parametrize("case", sorted(_BAD_STATES))
def test_bad_state_rejected_by_advance_and_podium(case) -> None:
    r = _Run(8)
    r.states = _confirm(r.states, "M1", P, "A")
    advance(r.pl, r.states, "M1")  # 正常狀態不拋例外
    code, bad = _BAD_STATES[case]
    r.states[code] = bad
    with pytest.raises(ValueError):
        advance(r.pl, r.states, "M1")
    with pytest.raises(ValueError):
        podium(r.pl, r.states)


def test_podium_missing_state_raises_value_error() -> None:
    r = _Run(4)
    del r.states["M4"]
    with pytest.raises(ValueError, match="M4"):
        podium(r.pl, r.states)


def test_third_place_decided_by_disqualification() -> None:
    r = _Run(4)
    r.confirm("M1", P, "A")
    r.confirm("M2", P, "C")
    r.confirm("M3", P, "A")
    assert r.confirm("M4", DQ, "B") == [TournamentFinished(Podium("A", "C", "B"))]


def test_three_teams_first_round_double_forfeit() -> None:
    r = _Run(3)
    assert r.confirm("M1", DF) == [
        ConfirmWalkover("M2", "C"),
        TournamentFinished(Podium("C", None, None)),
    ]


def test_final_walkover_champion_semifinal_disqualified() -> None:
    r = _Run(8)
    r.confirm("M1", P, "A")
    r.confirm("M2", P, "C")
    assert r.confirm("M5", DQ, "A") == [FillSlot("M7", "a", "A")]
    r.confirm("M3", DF)
    assert r.confirm("M4", DF) == [
        ConfirmWalkover("M6", None),
        ConfirmWalkover("M7", "A"),
        VoidMatch("M8"),
        TournamentFinished(Podium("A", None, None)),
    ]


def test_voided_third_place_keeps_seated_team() -> None:
    r = _Run(8)
    r.confirm("M3", P, "E")
    r.confirm("M4", P, "G")
    r.confirm("M6", P, "E")
    assert r.states["M8"].team_b == "G"
    assert r.confirm("M1", DF) == []
    assert r.confirm("M2", DF) == [
        ConfirmWalkover("M5", None),
        ConfirmWalkover("M7", "E"),
        VoidMatch("M8"),
        TournamentFinished(Podium("E", "G", None)),
    ]
    assert r.states["M8"] == MatchState(None, "G", MatchStatus.VOIDED, None, None)


def test_states_not_mutated() -> None:
    r = _Run(8)
    r.confirm("M1", DF)
    r.states = _confirm(r.states, "M2", P, "C")
    before = dict(r.states)
    advance(r.pl, r.states, "M2")
    assert r.states == before


def test_podium_none_until_finished() -> None:
    r = _Run(4)
    assert podium(r.pl, r.states) is None
    r.confirm("M1", P, "A")
    r.confirm("M2", P, "C")
    r.confirm("M3", P, "A")
    assert podium(r.pl, r.states) is None
    r.confirm("M4", P, "D")
    assert podium(r.pl, r.states) == Podium("A", "C", "D")


_RANDOM_OUTCOMES = [P, P, P, FF, DF, DQ]


def _simulate(n: int, seed: int) -> MatchOutcome | None:
    rng = random.Random(seed)
    pl = plan(n)
    states = _initial(pl, rng)
    final = next(m for m in pl.matches if m.next_code is None and not m.is_third_place)
    third = next((m for m in pl.matches if m.is_third_place), None)
    end_codes = {final.code} | ({third.code} if third else set())
    finished: list[Podium[str]] = []
    dq_losers: set[str] = set()

    while True:
        ready = [
            c
            for c, st in states.items()
            if st.status == MatchStatus.SCHEDULED and st.team_a and st.team_b
        ]
        if not ready:
            break
        code = rng.choice(ready)
        st = states[code]
        outcome = rng.choice(_RANDOM_OUTCOMES)
        winner = None if outcome == DF else rng.choice([st.team_a, st.team_b])
        if outcome == DQ:
            dq_losers.add(st.team_b if winner == st.team_a else st.team_a)
        states = _confirm(states, code, outcome, winner)

        full_before = {c for c, s in states.items() if s.team_a and s.team_b}
        changes = advance(pl, states, code)
        for ch in changes:
            if isinstance(ch, FillSlot):
                assert ch.team not in dq_losers
        states = _apply(states, changes)
        full_after = {c for c, s in states.items() if s.team_a and s.team_b}

        clocks = [ch.code for ch in changes if isinstance(ch, StartForfeitClock)]
        assert len(clocks) == len(set(clocks))
        assert set(clocks) == full_after - full_before
        for c in clocks:
            assert states[c].status == MatchStatus.SCHEDULED
        finished += [ch.podium for ch in changes if isinstance(ch, TournamentFinished)]

        again = advance(pl, states, code)
        if code in end_codes and finished:
            assert again == [TournamentFinished(finished[-1])]
        else:
            assert again == []

    assert all(
        s.status in (MatchStatus.CONFIRMED, MatchStatus.VOIDED) for s in states.values()
    )
    assert states[final.code].status == MatchStatus.CONFIRMED
    assert len(finished) == 1
    result = finished[0]
    assert result == podium(pl, states)
    assert result.champion == states[final.code].winner
    placed = [t for t in (result.champion, result.runner_up, result.third_place) if t]
    assert len(placed) == len(set(placed))
    assert not set(placed) & dq_losers
    if third is None:
        assert result.third_place is None
    else:
        assert result.third_place == states[third.code].winner
        semis = [m.code for m in pl.matches if m.loser_next_code == third.code]
        assert (states[third.code].status == MatchStatus.VOIDED) == any(
            states[c].winner is None for c in semis
        )
    if result.runner_up is not None:
        semis = [m.code for m in pl.matches if m.next_code == final.code]
        assert any(
            result.runner_up in (states[c].team_a, states[c].team_b)
            for c in [final.code, *semis]
        )
    return states[final.code].outcome


@pytest.mark.parametrize("n", range(2, 33))
def test_random_progression_invariants(n) -> None:
    for seed in range(12):
        _simulate(n, seed * 1000 + n)


def test_random_finals_cover_every_outcome() -> None:
    """確認隨機測試真的走過決賽的各種結果，不變式才有意義。"""
    seen = {_simulate(n, seed) for n in (2, 4, 5, 8) for seed in range(40)}
    assert seen == set(MatchOutcome)


def test_module_imports_only_allowed() -> None:
    tree = ast.parse(Path(progression.__file__).read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            modules.add(node.module)
    assert modules <= {
        "collections.abc",
        "dataclasses",
        "app.modules.competition.bracket",
        "app.modules.competition.models",
    }
