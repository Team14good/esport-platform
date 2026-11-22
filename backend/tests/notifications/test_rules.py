"""Story 1.6：期中事件的收件規則（收件人與 link）。

資料以真實流程建立（API 建隊與加入、service 送出與審核申請、真的抽籤與檢舉）；
審核、抽籤、檢舉的事件取自 outbox，其餘場次類事件以真實的場次 id 發出。
"""

import random
import uuid
from dataclasses import dataclass
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core import clock, events
from app.core.events import Event, OutboxEvent
from app.modules.competition import service as competition_service
from app.modules.competition.models import (
    AutoDrawSkipped,
    Match,
    MatchOpponentsDecided,
    MatchOutcome,
    MatchRescheduled,
    RefereeAssigned,
    RefereeUnassigned,
)
from app.modules.disputes import service as disputes_service
from app.modules.disputes.models import AppealDecision, AppealFiled, AppealResolved
from app.modules.identity import service as identity_service
from app.modules.identity.models import Account
from app.modules.notifications import service
from app.modules.notifications.models import Notification
from app.modules.competition.forfeit_job import MatchForfeited
from app.modules.notifications import rules
from app.modules.registration import service as registration_service
from app.modules.registration.models import (
    CaptainTransferred,
    RegistrationAllocated,
    RegistrationBackfilled,
    RegistrationRejected,
    RegistrationStatus,
    TeamMemberRemoved,
)
from app.modules.tournaments.models import TournamentRead, TournamentStatus
from tests.disputes.test_reports import _set_registration
from tests.registration.test_teams import (
    _create_ok,
    _join,
    _make_account,
    _set_status,
    _tournament,
)

pytestmark = pytest.mark.usefixtures("frozen_clock")


# ---------------------------------------------------------------- 測試資料


@dataclass
class Team:
    id: uuid.UUID
    captain: Account
    player: Account

    @property
    def members(self) -> set[uuid.UUID]:
        return {self.captain.id, self.player.id}


@dataclass
class World:
    tournament: TournamentRead
    organizer: Account
    teams: list[Team]

    @property
    def tid(self) -> uuid.UUID:
        return self.tournament.id


def _world(client: TestClient, session: Session, count: int = 4) -> World:
    """開放報名中的賽事與 `count` 支正取隊伍（各有隊長與一位選手）。"""
    organizer = _make_account(session)
    organizer.is_organizer = True
    session.add(organizer)
    session.flush()
    tournament = _tournament(session, organizer=organizer)
    teams = []
    for k in range(count):
        captain, player = _make_account(session), _make_account(session)
        body = _create_ok(client, captain, tournament.id, f"隊伍{k}")
        assert _join(client, player, body["invite_token"]).status_code == 200
        _set_registration(session, body["id"], RegistrationStatus.ACCEPTED)
        teams.append(Team(uuid.UUID(body["id"]), captain, player))
    return World(tournament, organizer, teams)


def _drawn(client: TestClient, session: Session) -> World:
    w = _world(client, session)
    _set_status(session, w.tid, TournamentStatus.CLOSED)
    competition_service.draw(
        session, tournament_id=w.tid, actor_id=w.organizer.id, rng=random.Random(7)
    )
    return w


def _first_match(session: Session, w: World) -> Match:
    statement = (
        select(Match)
        .where(Match.tournament_id == w.tid)
        .where(Match.round_no == 1)
        .order_by(Match.slot_no)
    )
    match = session.exec(statement).first()
    assert match is not None
    assert match.team_a_id is not None and match.team_b_id is not None
    return match


def _team(w: World, team_id: uuid.UUID | None) -> Team:
    return next(t for t in w.teams if t.id == team_id)


def _outbox(session: Session, event_type: str) -> list[OutboxEvent]:
    statement = select(OutboxEvent).where(OutboxEvent.type == event_type)
    return list(session.exec(statement))


def _dispatch(session: Session, event: OutboxEvent) -> dict[uuid.UUID, Notification]:
    service.dispatch_event(session, event)
    statement = select(Notification).where(Notification.event_id == event.id)
    return {n.account_id: n for n in session.exec(statement)}


def _publish(session: Session, event: Event) -> dict[uuid.UUID, Notification]:
    return _dispatch(session, events.publish(session, event))


def _links(notifications: dict[uuid.UUID, Notification]) -> set[str]:
    return {n.link for n in notifications.values()}


# ---------------------------------------------------------------- 主辦方申請


def _application(session: Session) -> tuple[Account, uuid.UUID]:
    admin = _make_account(session)
    admin.is_platform_admin = True
    session.add(admin)
    school = identity_service.create_school(
        session, actor_id=admin.id, name=f"測試大學-{uuid.uuid4().hex[:6]}"
    )
    applicant = _make_account(session)
    application = identity_service.submit_organizer_application(
        session, account_id=applicant.id, club_name="電競社", school_id=school.id
    )
    return applicant, application.id


def _application_event(
    session: Session, event_type: str, application_id: uuid.UUID
) -> OutboxEvent:
    [event] = [
        e
        for e in _outbox(session, event_type)
        if e.payload["application_id"] == str(application_id)
    ]
    return event


def test_submitted_application_notifies_every_platform_admin(
    session: Session,
) -> None:
    applicant, application_id = _application(session)
    admin_ids = set(identity_service.list_platform_admin_ids(session))

    notifications = _dispatch(
        session,
        _application_event(session, "OrganizerApplicationSubmitted", application_id),
    )

    assert admin_ids and set(notifications) == admin_ids
    assert applicant.id not in notifications
    assert _links(notifications) == {"/admin/applications"}


def test_approved_application_notifies_applicant(session: Session) -> None:
    applicant, application_id = _application(session)
    admin = _make_account(session)
    admin.is_platform_admin = True
    session.add(admin)
    session.flush()
    identity_service.approve_organizer_application(
        session, admin_id=admin.id, application_id=application_id
    )

    notifications = _dispatch(
        session,
        _application_event(session, "OrganizerApplicationApproved", application_id),
    )

    [notification] = notifications.values()
    assert notification.account_id == applicant.id
    assert notification.title == "主辦方申請已核准"
    assert notification.link == "/organizer"


def test_rejected_application_notifies_applicant(session: Session) -> None:
    applicant, application_id = _application(session)
    admin = _make_account(session)
    admin.is_platform_admin = True
    session.add(admin)
    session.flush()
    identity_service.reject_organizer_application(
        session, admin_id=admin.id, application_id=application_id, reason="資料不全"
    )

    notifications = _dispatch(
        session,
        _application_event(session, "OrganizerApplicationRejected", application_id),
    )

    assert set(notifications) == {applicant.id}
    assert _links(notifications) == {"/organizer/apply"}


def test_unknown_application_is_skipped(session: Session) -> None:
    from app.modules.identity.models import OrganizerApplicationApproved

    notifications = _publish(
        session, OrganizerApplicationApproved(application_id=uuid.uuid4())
    )

    assert notifications == {}


# ---------------------------------------------------------------- 報名、抽籤


def test_registration_allocated_notifies_all_team_members(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session, count=2)
    team = w.teams[0]

    notifications = _publish(
        session,
        RegistrationAllocated(
            registration_id=uuid.uuid4(),
            team_id=team.id,
            tournament_id=w.tid,
            status=RegistrationStatus.WAITLISTED,
        ),
    )

    assert set(notifications) == team.members
    assert _links(notifications) == {f"/teams/{team.id}"}
    assert {n.title for n in notifications.values()} == {"報名結果：候補"}


def test_registration_backfilled_notifies_all_team_members(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session, count=2)
    team = w.teams[1]

    notifications = _publish(
        session,
        RegistrationBackfilled(
            registration_id=uuid.uuid4(), team_id=team.id, tournament_id=w.tid
        ),
    )

    assert set(notifications) == team.members
    assert _links(notifications) == {f"/teams/{team.id}"}
    assert {(n.title, n.body) for n in notifications.values()} == {
        (
            "報名結果：已遞補為正取",
            f"「隊伍1」在「{w.tournament.name}」已由候補遞補為正取。",
        )
    }


@pytest.mark.parametrize(
    ("can_resubmit", "next_step"),
    [
        (True, "請在報名截止前修正後重新送出。"),
        (False, "報名已截止，無法重新送出。"),
    ],
)
def test_registration_rejected_notifies_all_team_members(
    client: TestClient, session: Session, can_resubmit: bool, next_step: str
) -> None:
    """Story 3.8：退回通知發給全隊，內文依退回當下能否重送分兩種。"""
    w = _world(client, session, count=2)
    team = w.teams[0]

    notifications = _publish(
        session,
        RegistrationRejected(
            registration_id=uuid.uuid4(),
            team_id=team.id,
            tournament_id=w.tid,
            reason="段位截圖與申報段位不符",
            can_resubmit=can_resubmit,
        ),
    )

    assert set(notifications) == team.members
    assert _links(notifications) == {f"/teams/{team.id}"}
    assert {(n.title, n.body) for n in notifications.values()} == {
        (
            "報名結果：退回",
            f"「隊伍0」在「{w.tournament.name}」的報名被主辦方退回，"
            f"原因：段位截圖與申報段位不符。{next_step}",
        )
    }


def test_registration_rejected_reason_ending_with_period_is_not_doubled(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session, count=1)
    team = w.teams[0]

    notifications = _publish(
        session,
        RegistrationRejected(
            registration_id=uuid.uuid4(),
            team_id=team.id,
            tournament_id=w.tid,
            reason="段位截圖與申報段位不符。",
            can_resubmit=True,
        ),
    )

    assert {n.body for n in notifications.values()} == {
        f"「隊伍0」在「{w.tournament.name}」的報名被主辦方退回，"
        "原因：段位截圖與申報段位不符。請在報名截止前修正後重新送出。"
    }


def test_registration_rejected_reason_of_only_punctuation_is_kept(
    client: TestClient, session: Session
) -> None:
    """原因只有句末標點時沿用原字串，不會變成「原因：。」（PR #107 審查）。"""
    w = _world(client, session, count=1)
    team = w.teams[0]

    notifications = _publish(
        session,
        RegistrationRejected(
            registration_id=uuid.uuid4(),
            team_id=team.id,
            tournament_id=w.tid,
            reason="？",
            can_resubmit=False,
        ),
    )

    assert {n.body for n in notifications.values()} == {
        f"「隊伍0」在「{w.tournament.name}」的報名被主辦方退回，"
        "原因：？。報名已截止，無法重新送出。"
    }


def test_bracket_drawn_notifies_members_of_every_team_on_the_bracket(
    client: TestClient, session: Session
) -> None:
    w = _drawn(client, session)
    [event] = [
        e
        for e in _outbox(session, "BracketDrawn")
        if e.payload["tournament_id"] == str(w.tid)
    ]

    notifications = _dispatch(session, event)

    expected = set().union(*(t.members for t in w.teams))
    assert set(notifications) == expected
    assert _links(notifications) == {f"/tournaments/{w.tid}/bracket"}


def test_auto_draw_skipped_notifies_organizer(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session, count=1)

    notifications = _publish(
        session, AutoDrawSkipped(tournament_id=w.tid, accepted_teams=1)
    )

    assert set(notifications) == {w.organizer.id}
    assert _links(notifications) == {f"/organizer/tournaments/{w.tid}"}


# ---------------------------------------------------------------- 場次、裁判


def test_rescheduled_match_notifies_both_teams_and_referee(
    client: TestClient, session: Session
) -> None:
    w = _drawn(client, session)
    match = _first_match(session, w)
    referee = _make_account(session)
    match.referee_account_id = referee.id
    session.add(match)
    session.flush()
    new_time = clock.now() + timedelta(days=9)

    notifications = _publish(
        session, MatchRescheduled(match_id=match.id, scheduled_at=new_time)
    )

    a, b = _team(w, match.team_a_id), _team(w, match.team_b_id)
    assert set(notifications) == a.members | b.members | {referee.id}
    assert _links(notifications) == {f"/tournaments/{w.tid}/matches/{match.id}"}


def test_forfeited_match_notifies_both_teams_and_referee(
    client: TestClient, session: Session
) -> None:
    w = _drawn(client, session)
    match = _first_match(session, w)
    referee = _make_account(session)
    match.referee_account_id = referee.id
    session.add(match)
    session.flush()
    # 用 competition 判棄權時發的事件類別本身：改名或改欄位時這個測試會失敗
    event = events.publish(
        session,
        MatchForfeited(
            match_id=match.id,
            tournament_id=w.tid,
            outcome=MatchOutcome.FORFEIT,
            winner_id=match.team_a_id,
            forfeited_team_ids=(match.team_b_id,),
            appeal_deadline=clock.now(),
        ),
    )

    notifications = _dispatch(session, event)

    a, b = _team(w, match.team_a_id), _team(w, match.team_b_id)
    assert set(notifications) == a.members | b.members | {referee.id}


def test_forfeit_rule_is_registered_under_competitions_event_name() -> None:
    # notifications 依 AD-2 另定義同名類別讀 payload；兩邊名稱不同時判棄權通知會默默停掉
    assert rules.MatchForfeited.event_type == MatchForfeited.event_type
    assert set(rules.MatchForfeited.model_fields) <= set(MatchForfeited.model_fields)


def test_opponents_decided_notifies_only_both_captains(
    client: TestClient, session: Session
) -> None:
    w = _drawn(client, session)
    match = _first_match(session, w)

    notifications = _publish(session, MatchOpponentsDecided(match_id=match.id))

    a, b = _team(w, match.team_a_id), _team(w, match.team_b_id)
    assert set(notifications) == {a.captain.id, b.captain.id}
    assert _links(notifications) == {f"/tournaments/{w.tid}/matches/{match.id}"}


@pytest.mark.parametrize("event_class", [RefereeAssigned, RefereeUnassigned])
def test_referee_events_notify_the_referee_in_the_event(
    client: TestClient,
    session: Session,
    event_class: type[RefereeAssigned] | type[RefereeUnassigned],
) -> None:
    w = _drawn(client, session)
    match = _first_match(session, w)
    referee = _make_account(session)

    notifications = _publish(
        session, event_class(match_id=match.id, referee_account_id=referee.id)
    )

    assert set(notifications) == {referee.id}
    assert _links(notifications) == {"/me/referee"}


def test_unknown_match_is_skipped(session: Session) -> None:
    notifications = _publish(
        session,
        RefereeAssigned(match_id=uuid.uuid4(), referee_account_id=uuid.uuid4()),
    )

    assert notifications == {}


# ---------------------------------------------------------------- 申訴、檢舉


def test_appeal_filed_notifies_organizer(client: TestClient, session: Session) -> None:
    w = _drawn(client, session)
    match = _first_match(session, w)
    assert match.team_a_id is not None

    notifications = _publish(
        session,
        AppealFiled(appeal_id=uuid.uuid4(), match_id=match.id, team_id=match.team_a_id),
    )

    assert set(notifications) == {w.organizer.id}
    assert _links(notifications) == {f"/organizer/tournaments/{w.tid}/appeals"}


def test_appeal_resolved_notifies_both_teams(
    client: TestClient, session: Session
) -> None:
    w = _drawn(client, session)
    match = _first_match(session, w)

    notifications = _publish(
        session, AppealResolved(match_id=match.id, decision=AppealDecision.UPHELD)
    )

    a, b = _team(w, match.team_a_id), _team(w, match.team_b_id)
    assert set(notifications) == a.members | b.members
    assert _links(notifications) == {f"/tournaments/{w.tid}/matches/{match.id}"}


def test_report_filed_and_resolved_notify_organizer_then_both_teams(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session, count=2)
    reporter, reported = w.teams
    filed = disputes_service.file_report(
        session,
        tournament_id=w.tid,
        account_id=reporter.captain.id,
        reported_team_id=reported.id,
        description="隊員不是本校學生。",
        attachment=None,
        content_type=None,
    )
    [filed_event] = [
        e
        for e in _outbox(session, "ReportFiled")
        if e.payload["report_id"] == str(filed.report.id)
    ]

    to_organizer = _dispatch(session, filed_event)

    assert set(to_organizer) == {w.organizer.id}
    assert _links(to_organizer) == {f"/organizer/tournaments/{w.tid}/reports"}

    disputes_service.resolve_report(
        session,
        tournament_id=w.tid,
        report_id=filed.report.id,
        actor_id=w.organizer.id,
        substantiated=False,
        reason="查無實據。",
    )
    [resolved_event] = [
        e
        for e in _outbox(session, "ReportResolved")
        if e.payload["report_id"] == str(filed.report.id)
    ]

    to_teams = _dispatch(session, resolved_event)

    assert set(to_teams) == reporter.members | reported.members
    for account_id in reporter.members:
        assert to_teams[account_id].link == f"/teams/{reporter.id}"
    for account_id in reported.members:
        assert to_teams[account_id].link == f"/teams/{reported.id}"


# ---------------------------------------------------------------- 隊員異動與解散（3.11）


def test_team_member_removed_notifies_only_the_removed_account(
    client: TestClient, session: Session
) -> None:
    """被移除者在 worker 處理時已不在隊上：收件人取自事件，連結賽事頁。"""
    w = _world(client, session, count=1)
    team = w.teams[0]

    notifications = _publish(
        session,
        TeamMemberRemoved(
            team_id=team.id, tournament_id=w.tid, account_id=team.player.id
        ),
    )

    assert set(notifications) == {team.player.id}
    assert {(n.title, n.body, n.link) for n in notifications.values()} == {
        (
            "已被移出隊伍",
            f"你已被隊長移出「隊伍0」（{w.tournament.name}）。",
            f"/tournaments/{w.tid}",
        )
    }


def test_captain_transferred_notifies_the_new_captain(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session, count=1)
    team = w.teams[0]

    notifications = _publish(
        session,
        CaptainTransferred(
            team_id=team.id,
            tournament_id=w.tid,
            from_account_id=team.captain.id,
            to_account_id=team.player.id,
        ),
    )

    assert set(notifications) == {team.player.id}
    assert {(n.title, n.body, n.link) for n in notifications.values()} == {
        (
            "你成為隊長",
            f"「隊伍0」（{w.tournament.name}）的隊長已轉讓給你。",
            f"/teams/{team.id}",
        )
    }


def test_team_disbanded_notifies_every_former_member_including_captain(
    client: TestClient, session: Session
) -> None:
    """解散後隊伍沒有隊員；收件人取自解散名單（含隊長本人，FR-37）。"""
    w = _world(client, session, count=1)
    team = w.teams[0]
    _set_registration(session, str(team.id), RegistrationStatus.FORMING)
    registration_service.disband_team(
        session, team_id=team.id, account_id=team.captain.id
    )
    [event] = [
        e
        for e in _outbox(session, "TeamDisbanded")
        if e.payload["team_id"] == str(team.id)
    ]

    notifications = _dispatch(session, event)

    assert set(notifications) == team.members
    assert {(n.title, n.body, n.link) for n in notifications.values()} == {
        (
            "隊伍已解散",
            f"「隊伍0」（{w.tournament.name}）已被隊長解散，報名已撤回。",
            f"/teams/{team.id}",
        )
    }


def test_roster_events_of_unknown_team_are_skipped(session: Session) -> None:
    missing = uuid.uuid4()

    notifications = _publish(
        session,
        TeamMemberRemoved(
            team_id=missing, tournament_id=uuid.uuid4(), account_id=missing
        ),
    )

    assert notifications == {}
