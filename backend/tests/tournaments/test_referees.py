"""Story 2.7（第一階段）：邀請裁判的後端（I/O 矩陣、7 天邊界、跨賽事、排序與併發）。"""

import threading
import time
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, text
from sqlmodel import Session, col, select

from app.core import clock
from app.core.audit import AuditLog
from app.core.db import engine
from app.core.errors import BusinessError
from app.modules.identity.models import Account
from app.modules.tournaments import service
from app.modules.tournaments.models import (
    RefereeInvitation,
    TournamentRead,
    TournamentReferee,
    TournamentStatus,
)
from tests.conftest import FrozenClock
from tests.helpers import (
    API,
    bearer,
    make_account,
    make_game,
    make_tournament,
    token_for,
)


def _invitation_url(tournament_id: uuid.UUID) -> str:
    return f"{API}/organizer/tournaments/{tournament_id}/referee-invitation"


def _referees_url(tournament_id: uuid.UUID) -> str:
    return f"{API}/organizer/tournaments/{tournament_id}/referees"


def _preview_url(token: str) -> str:
    return f"{API}/referee-invites/{token}"


def _accept_url(token: str) -> str:
    return f"{API}/referee-invites/{token}/accept"


def _error_code(response: Any) -> str:
    return str(response.json()["detail"]["code"])


@pytest.fixture
def organizer(session: Session) -> Account:
    return make_account(session, organizer=True)


@pytest.fixture
def tournament(session: Session, organizer: Account) -> TournamentRead:
    return make_tournament(session, organizer=organizer)


def _invite(
    client: TestClient, account: Account, tournament_id: uuid.UUID
) -> dict[str, Any]:
    response = client.post(
        _invitation_url(tournament_id), headers=bearer(token_for(client, account))
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def _accept(client: TestClient, account: Account, token: str) -> Any:
    return client.post(_accept_url(token), headers=bearer(token_for(client, account)))


def _move_to(
    session: Session, tournament_id: uuid.UUID, path: list[TournamentStatus]
) -> None:
    for status in path:
        service.transition_tournament(
            session, tournament_id=tournament_id, to=status, actor_id=None
        )


FINISH_PATH = [
    TournamentStatus.PUBLISHED,
    TournamentStatus.ONGOING,
    TournamentStatus.FINISHED,
]


# ---------------------------------------------------------------- 產生與查看邀請


def test_organizer_creates_invitation_valid_for_7_days(
    client: TestClient,
    session: Session,
    organizer: Account,
    tournament: TournamentRead,
    frozen_clock: FrozenClock,
) -> None:
    now = frozen_clock.now()

    body = _invite(client, organizer, tournament.id)

    assert set(body) == {
        "tournament_id",
        "token",
        "created_at",
        "expires_at",
        "expired",
    }
    assert body["tournament_id"] == str(tournament.id)
    assert len(body["token"]) >= 43
    assert body["expired"] is False
    stored = session.exec(
        select(RefereeInvitation).where(RefereeInvitation.token == body["token"])
    ).one()
    assert stored.created_at == now
    assert stored.expires_at == now + timedelta(days=7)
    assert stored.created_by == organizer.id


def test_regenerating_expires_previous_invitation_without_deleting(
    client: TestClient,
    session: Session,
    organizer: Account,
    tournament: TournamentRead,
) -> None:
    first = _invite(client, organizer, tournament.id)
    second = _invite(client, organizer, tournament.id)

    assert first["token"] != second["token"]
    rows = {
        row.token: row
        for row in session.exec(
            select(RefereeInvitation).where(
                RefereeInvitation.tournament_id == tournament.id
            )
        )
    }
    assert set(rows) == {first["token"], second["token"]}
    session.refresh(rows[first["token"]])
    # 舊的被設為產生新邀請的當下
    assert rows[first["token"]].expires_at == rows[second["token"]].created_at


def test_regenerating_does_not_touch_other_tournaments(
    client: TestClient, session: Session, organizer: Account
) -> None:
    tournament_a = make_tournament(session, organizer=organizer)
    tournament_b = make_tournament(session, organizer=organizer)
    invite_a = _invite(client, organizer, tournament_a.id)

    _invite(client, organizer, tournament_b.id)

    preview = client.get(_preview_url(invite_a["token"]))
    assert preview.json()["expired"] is False


def test_get_current_invitation_returns_latest_or_null(
    client: TestClient,
    organizer: Account,
    tournament: TournamentRead,
    frozen_clock: FrozenClock,
) -> None:
    headers = bearer(token_for(client, organizer))

    empty = client.get(_invitation_url(tournament.id), headers=headers)
    assert empty.status_code == 200
    assert empty.json() is None

    _invite(client, organizer, tournament.id)
    # 凍結時鐘：兩次產生在同一時間點，仍要回傳新的那筆
    second = _invite(client, organizer, tournament.id)
    current = client.get(_invitation_url(tournament.id), headers=headers)
    assert current.status_code == 200
    assert current.json() == second

    frozen_clock.advance(timedelta(days=7))
    # 時鐘推進後原本的 access token 可能過期，重新登入
    expired = client.get(
        _invitation_url(tournament.id), headers=bearer(token_for(client, organizer))
    )
    assert expired.status_code == 200, expired.text
    assert expired.json()["token"] == second["token"]
    assert expired.json()["expired"] is True


@pytest.mark.parametrize("method", ["post", "get"])
def test_invitation_of_others_tournament_is_403(
    client: TestClient, session: Session, tournament: TournamentRead, method: str
) -> None:
    other = make_account(session, organizer=True)

    response = client.request(
        method, _invitation_url(tournament.id), headers=bearer(token_for(client, other))
    )

    assert response.status_code == 403
    assert _error_code(response) == "TOURNAMENT_OWNER_REQUIRED"
    assert (
        session.exec(
            select(RefereeInvitation).where(
                RefereeInvitation.tournament_id == tournament.id
            )
        ).first()
        is None
    )


@pytest.mark.parametrize("method", ["post", "get"])
def test_invitation_of_missing_tournament_is_404(
    client: TestClient, organizer: Account, method: str
) -> None:
    response = client.request(
        method,
        _invitation_url(uuid.uuid4()),
        headers=bearer(token_for(client, organizer)),
    )

    assert response.status_code == 404
    assert _error_code(response) == "TOURNAMENT_NOT_FOUND"


def test_non_organizer_cannot_read_invitation(
    client: TestClient, session: Session, tournament: TournamentRead
) -> None:
    member = make_account(session)

    response = client.get(
        _invitation_url(tournament.id), headers=bearer(token_for(client, member))
    )

    assert response.status_code == 403
    assert _error_code(response) == "ORGANIZER_REQUIRED"


def test_list_referees_of_missing_tournament_is_404(
    client: TestClient, organizer: Account
) -> None:
    response = client.get(
        _referees_url(uuid.uuid4()), headers=bearer(token_for(client, organizer))
    )

    assert response.status_code == 404
    assert _error_code(response) == "TOURNAMENT_NOT_FOUND"


def test_token_longer_than_column_is_422(client: TestClient, session: Session) -> None:
    token = "a" * 65

    assert client.get(_preview_url(token)).status_code == 422
    assert _accept(client, make_account(session), token).status_code == 422


def test_non_organizer_cannot_create_invitation(
    client: TestClient, session: Session, tournament: TournamentRead
) -> None:
    member = make_account(session)

    response = client.post(
        _invitation_url(tournament.id), headers=bearer(token_for(client, member))
    )

    assert response.status_code == 403
    assert _error_code(response) == "ORGANIZER_REQUIRED"


@pytest.mark.parametrize(
    "path",
    [FINISH_PATH, [TournamentStatus.CANCELLED]],
    ids=["finished", "cancelled"],
)
def test_cannot_create_invitation_for_finished_or_cancelled(
    client: TestClient,
    session: Session,
    organizer: Account,
    tournament: TournamentRead,
    path: list[TournamentStatus],
) -> None:
    _move_to(session, tournament.id, path)

    response = client.post(
        _invitation_url(tournament.id), headers=bearer(token_for(client, organizer))
    )

    assert response.status_code == 409
    assert _error_code(response) == "TOURNAMENT_NOT_ACCEPTING_REFEREES"
    assert service.get_current_invitation(session, tournament_id=tournament.id) is None


def test_can_create_invitation_for_upcoming_tournament(
    client: TestClient, session: Session, organizer: Account
) -> None:
    upcoming = make_tournament(
        session,
        organizer=organizer,
        registration_start=(clock.now() + timedelta(days=1)).isoformat(),
    )
    assert upcoming.status == TournamentStatus.UPCOMING

    _invite(client, organizer, upcoming.id)


def test_create_invitation_writes_audit_without_token(
    client: TestClient,
    session: Session,
    organizer: Account,
    tournament: TournamentRead,
) -> None:
    body = _invite(client, organizer, tournament.id)

    [log] = session.exec(
        select(AuditLog)
        .where(AuditLog.action == "referee_invitation.created")
        .where(AuditLog.tournament_id == tournament.id)
    ).all()
    assert log.actor_id == organizer.id
    assert log.entity_type == "referee_invitation"
    assert body["token"] not in str(log.before) + str(log.after)


# ---------------------------------------------------------------- 預覽


def test_preview_is_public_and_only_has_public_fields(
    client: TestClient, organizer: Account, tournament: TournamentRead
) -> None:
    body = _invite(client, organizer, tournament.id)

    response = client.get(_preview_url(body["token"]))

    assert response.status_code == 200
    assert response.json() == {
        "tournament_name": tournament.name,
        "expires_at": body["expires_at"],
        "expired": False,
    }


def test_preview_expired_and_invalidated_invitations(
    client: TestClient,
    organizer: Account,
    tournament: TournamentRead,
    frozen_clock: FrozenClock,
) -> None:
    first = _invite(client, organizer, tournament.id)
    frozen_clock.advance(timedelta(minutes=1))
    second = _invite(client, organizer, tournament.id)

    assert client.get(_preview_url(first["token"])).json()["expired"] is True
    assert client.get(_preview_url(second["token"])).json()["expired"] is False


def test_preview_unknown_token_is_404(client: TestClient) -> None:
    response = client.get(_preview_url("no-such-token"))

    assert response.status_code == 404
    assert _error_code(response) == "REFEREE_INVITATION_NOT_FOUND"


# ---------------------------------------------------------------- 接受


def test_accept_creates_referee(
    client: TestClient,
    session: Session,
    organizer: Account,
    tournament: TournamentRead,
    frozen_clock: FrozenClock,
) -> None:
    body = _invite(client, organizer, tournament.id)
    referee = make_account(session)
    frozen_clock.advance(timedelta(hours=1))

    response = _accept(client, referee, body["token"])

    assert response.status_code == 200, response.text
    assert response.json() == {
        "account_id": str(referee.id),
        "display_name": referee.display_name,
        "accepted_at": frozen_clock.now().isoformat().replace("+00:00", "Z"),
    }
    row = session.get(TournamentReferee, (tournament.id, referee.id))
    assert row is not None
    assert row.accepted_at == frozen_clock.now()
    assert service.is_referee(
        session, tournament_id=tournament.id, account_id=referee.id
    )


def test_accept_twice_is_idempotent(
    client: TestClient,
    session: Session,
    organizer: Account,
    tournament: TournamentRead,
    frozen_clock: FrozenClock,
) -> None:
    body = _invite(client, organizer, tournament.id)
    referee = make_account(session)
    first = _accept(client, referee, body["token"])
    frozen_clock.advance(timedelta(hours=1))

    second = _accept(client, referee, body["token"])

    assert second.status_code == 200
    assert second.json() == first.json()
    rows = session.exec(
        select(TournamentReferee).where(
            TournamentReferee.tournament_id == tournament.id
        )
    ).all()
    assert len(rows) == 1
    logs = session.exec(
        select(AuditLog)
        .where(AuditLog.action == "referee.accepted")
        .where(AuditLog.tournament_id == tournament.id)
    ).all()
    assert len(logs) == 1
    assert logs[0].actor_id == referee.id
    assert body["token"] not in str(logs[0].before) + str(logs[0].after)


@pytest.mark.parametrize("how", ["regenerated", "seven_days"])
def test_existing_referee_with_expired_token_is_409(
    client: TestClient,
    session: Session,
    organizer: Account,
    tournament: TournamentRead,
    frozen_clock: FrozenClock,
    how: str,
) -> None:
    """使用者決定：已是裁判的人用過期或已作廢的連結再接受，一樣 409。"""
    body = _invite(client, organizer, tournament.id)
    referee = make_account(session)
    assert _accept(client, referee, body["token"]).status_code == 200
    before = session.get(TournamentReferee, (tournament.id, referee.id))
    assert before is not None
    snapshot = before.model_dump()
    if how == "regenerated":
        _invite(client, organizer, tournament.id)
    else:
        frozen_clock.advance(timedelta(days=7))

    response = _accept(client, referee, body["token"])

    assert response.status_code == 409
    assert _error_code(response) == "REFEREE_INVITATION_EXPIRED"
    session.expire_all()
    rows = session.exec(
        select(TournamentReferee).where(
            TournamentReferee.tournament_id == tournament.id
        )
    ).all()
    assert [row.model_dump() for row in rows] == [snapshot]


def test_accept_with_new_invitation_after_already_referee(
    client: TestClient,
    session: Session,
    organizer: Account,
    tournament: TournamentRead,
) -> None:
    first = _invite(client, organizer, tournament.id)
    referee = make_account(session)
    original = _accept(client, referee, first["token"]).json()
    second = _invite(client, organizer, tournament.id)

    response = _accept(client, referee, second["token"])

    assert response.status_code == 200
    assert response.json() == original


def test_old_token_is_rejected_after_regenerating(
    client: TestClient,
    session: Session,
    organizer: Account,
    tournament: TournamentRead,
) -> None:
    """AC：產生過兩次邀請，第一次的 token 409，第二次的可以接受。"""
    first = _invite(client, organizer, tournament.id)
    second = _invite(client, organizer, tournament.id)
    referee = make_account(session)

    old = _accept(client, referee, first["token"])
    assert old.status_code == 409
    assert _error_code(old) == "REFEREE_INVITATION_EXPIRED"
    assert not service.is_referee(
        session, tournament_id=tournament.id, account_id=referee.id
    )

    new = _accept(client, referee, second["token"])
    assert new.status_code == 200


def test_invitation_expires_exactly_after_7_days(
    client: TestClient,
    session: Session,
    organizer: Account,
    tournament: TournamentRead,
    frozen_clock: FrozenClock,
) -> None:
    body = _invite(client, organizer, tournament.id)
    early, late = make_account(session), make_account(session)

    frozen_clock.advance(timedelta(days=7) - timedelta(microseconds=1))
    assert client.get(_preview_url(body["token"])).json()["expired"] is False
    assert _accept(client, early, body["token"]).status_code == 200

    frozen_clock.advance(timedelta(microseconds=1))
    assert client.get(_preview_url(body["token"])).json()["expired"] is True
    response = _accept(client, late, body["token"])
    assert response.status_code == 409
    assert _error_code(response) == "REFEREE_INVITATION_EXPIRED"


def test_accept_unknown_token_is_404(client: TestClient, session: Session) -> None:
    response = _accept(client, make_account(session), "no-such-token")

    assert response.status_code == 404
    assert _error_code(response) == "REFEREE_INVITATION_NOT_FOUND"


def test_accept_requires_login(
    client: TestClient, organizer: Account, tournament: TournamentRead
) -> None:
    body = _invite(client, organizer, tournament.id)

    response = client.post(_accept_url(body["token"]))

    assert response.status_code == 401
    assert _error_code(response) == "AUTHENTICATION_REQUIRED"


def test_accept_requires_verified_email(
    client: TestClient,
    session: Session,
    organizer: Account,
    tournament: TournamentRead,
) -> None:
    body = _invite(client, organizer, tournament.id)
    unverified = make_account(session, verified=False)

    response = _accept(client, unverified, body["token"])

    assert response.status_code == 403
    assert _error_code(response) == "EMAIL_NOT_VERIFIED"
    assert session.get(TournamentReferee, (tournament.id, unverified.id)) is None


def test_organizer_cannot_accept_own_invitation(
    client: TestClient,
    session: Session,
    organizer: Account,
    tournament: TournamentRead,
) -> None:
    body = _invite(client, organizer, tournament.id)

    response = _accept(client, organizer, body["token"])

    assert response.status_code == 409
    assert _error_code(response) == "ORGANIZER_CANNOT_BE_REFEREE"
    assert session.get(TournamentReferee, (tournament.id, organizer.id)) is None


def test_other_organizer_can_be_referee(
    client: TestClient,
    session: Session,
    organizer: Account,
    tournament: TournamentRead,
) -> None:
    body = _invite(client, organizer, tournament.id)

    response = _accept(client, make_account(session, organizer=True), body["token"])

    assert response.status_code == 200


@pytest.mark.parametrize(
    "path",
    [FINISH_PATH, [TournamentStatus.CANCELLED]],
    ids=["finished", "cancelled"],
)
def test_cannot_accept_for_finished_or_cancelled(
    client: TestClient,
    session: Session,
    organizer: Account,
    tournament: TournamentRead,
    path: list[TournamentStatus],
) -> None:
    body = _invite(client, organizer, tournament.id)
    _move_to(session, tournament.id, path)
    referee = make_account(session)

    response = _accept(client, referee, body["token"])

    assert response.status_code == 409
    assert _error_code(response) == "TOURNAMENT_NOT_ACCEPTING_REFEREES"
    assert "無法接受裁判邀請" in response.json()["detail"]["message"]
    assert session.get(TournamentReferee, (tournament.id, referee.id)) is None


# ---------------------------------------------------------------- is_referee、list_referees


def test_is_referee_only_for_that_tournament(
    session: Session, organizer: Account
) -> None:
    """AC：接受 A 賽事邀請，is_referee 查 A、B 分別為 true、false。"""
    tournament_a = make_tournament(session, organizer=organizer)
    tournament_b = make_tournament(session, organizer=organizer)
    invitation = service.invite_referee(
        session, tournament_id=tournament_a.id, actor_id=organizer.id
    )
    referee = make_account(session)
    service.accept_invitation(session, token=invitation.token, account_id=referee.id)

    assert service.is_referee(
        session, tournament_id=tournament_a.id, account_id=referee.id
    )
    assert not service.is_referee(
        session, tournament_id=tournament_b.id, account_id=referee.id
    )
    assert not service.is_referee(
        session, tournament_id=tournament_a.id, account_id=organizer.id
    )


def test_list_referees_sorted_by_acceptance_with_display_names(
    client: TestClient,
    session: Session,
    organizer: Account,
    tournament: TournamentRead,
    frozen_clock: FrozenClock,
) -> None:
    """AC：三個帳號先後接受，依接受時間排序且帶顯示名稱。"""
    invitation = service.invite_referee(
        session, tournament_id=tournament.id, actor_id=organizer.id
    )
    accounts = []
    for name in ["丙裁判", "甲裁判", "乙裁判"]:
        account = make_account(session)
        account.display_name = name
        session.add(account)
        session.flush()
        accounts.append(account)
    for account in accounts:
        frozen_clock.advance(timedelta(minutes=5))
        service.accept_invitation(
            session, token=invitation.token, account_id=account.id
        )

    referees = service.list_referees(session, tournament_id=tournament.id)

    assert [r.account_id for r in referees] == [a.id for a in accounts]
    assert [r.display_name for r in referees] == ["丙裁判", "甲裁判", "乙裁判"]
    assert referees[0].accepted_at < referees[1].accepted_at < referees[2].accepted_at

    response = client.get(
        _referees_url(tournament.id), headers=bearer(token_for(client, organizer))
    )
    assert response.status_code == 200
    assert [r["display_name"] for r in response.json()] == [
        "丙裁判",
        "甲裁判",
        "乙裁判",
    ]


def test_list_referees_empty(
    client: TestClient, organizer: Account, tournament: TournamentRead
) -> None:
    response = client.get(
        _referees_url(tournament.id), headers=bearer(token_for(client, organizer))
    )

    assert response.status_code == 200
    assert response.json() == []


def test_list_referees_of_others_tournament_is_403(
    client: TestClient, session: Session, tournament: TournamentRead
) -> None:
    other = make_account(session, organizer=True)

    response = client.get(
        _referees_url(tournament.id), headers=bearer(token_for(client, other))
    )

    assert response.status_code == 403
    assert _error_code(response) == "TOURNAMENT_OWNER_REQUIRED"


def test_accept_invitation_service_rejects_expired(
    session: Session, organizer: Account, tournament: TournamentRead
) -> None:
    first = service.invite_referee(
        session, tournament_id=tournament.id, actor_id=organizer.id
    )
    service.invite_referee(session, tournament_id=tournament.id, actor_id=organizer.id)

    with pytest.raises(BusinessError) as exc_info:
        service.accept_invitation(
            session, token=first.token, account_id=make_account(session).id
        )
    assert exc_info.value.code == "REFEREE_INVITATION_EXPIRED"


# ---------------------------------------------------------------- 與重新產生同時


def _demote_game_creator(session: Session, game_id: uuid.UUID) -> None:
    """make_game 以新建的平台管理員建立遊戲；提交前取消他的管理員身分（比照 3.1）。"""
    log = session.exec(
        select(AuditLog).where(
            AuditLog.entity_id == game_id, AuditLog.action == "game.created"
        )
    ).one()
    assert log.actor_id is not None
    admin = session.get(Account, log.actor_id)
    assert admin is not None
    admin.is_platform_admin = False
    session.add(admin)
    session.flush()


LOCK_WAIT_TIMEOUT = 10.0


def _backend_pid(db: Session) -> int:
    return int(db.connection().execute(text("SELECT pg_backend_pid()")).scalar_one())


def _wait_until_blocked_on_lock(pids: list[int], thread: threading.Thread) -> None:
    """等到另一條連線（pid 由執行緒寫入 `pids`）在 pg_stat_activity 顯示正在等鎖。"""
    deadline = time.monotonic() + LOCK_WAIT_TIMEOUT
    with engine.connect() as monitor:
        while time.monotonic() < deadline:
            assert thread.is_alive(), "另一條連線沒有等鎖就結束了"
            if pids:
                waiting = monitor.execute(
                    text(
                        "SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"
                    ),
                    {"pid": pids[0]},
                ).scalar_one_or_none()
                if waiting == "Lock":
                    return
            monitor.rollback()
            time.sleep(0.02)
    raise AssertionError("另一條連線沒有在時限內卡在鎖上")


def _setup_committed_invitation() -> tuple[TournamentRead, str, uuid.UUID, uuid.UUID]:
    """提交一場賽事、一筆邀請與一個受邀帳號；回傳（賽事、token、受邀者、主辦方）。"""
    with Session(engine) as setup:
        game = make_game(setup)
        _demote_game_creator(setup, game.id)
        organizer = make_account(setup, organizer=True)
        tournament = make_tournament(setup, organizer=organizer, game=game)
        invitation = service.invite_referee(
            setup, tournament_id=tournament.id, actor_id=organizer.id
        )
        referee_id = make_account(setup).id
        organizer_id = organizer.id
        setup.commit()
    return tournament, invitation.token, referee_id, organizer_id


def _cleanup_referee_rows(tournament_id: uuid.UUID) -> None:
    with Session(engine) as cleanup:
        cleanup.connection().execute(
            delete(TournamentReferee).where(
                col(TournamentReferee.tournament_id) == tournament_id
            )
        )
        cleanup.connection().execute(
            delete(RefereeInvitation).where(
                col(RefereeInvitation.tournament_id) == tournament_id
            )
        )
        cleanup.commit()


def _run_in_thread(
    work: Callable[[Session], object], outcome: list[str], pids: list[int]
) -> threading.Thread:
    def _target() -> None:
        with Session(engine) as db:
            try:
                pids.append(_backend_pid(db))
                work(db)
                db.commit()
                outcome.append("ok")
            except BusinessError as exc:
                outcome.append(exc.code)
            except Exception as exc:  # 讓非預期錯誤（例如死結）出現在斷言訊息裡
                outcome.append(repr(exc))

    return threading.Thread(target=_target)


def test_accept_waits_for_concurrent_regeneration_and_is_rejected() -> None:
    """重新產生尚未提交時，用舊 token 接受要等它，提交後判定為已作廢。

    要真正提交才看得到別條連線的變更，所以不使用每個測試回滾的 session；被只增不改的
    操作紀錄參照的賽事、遊戲與帳號留在測試資料庫（比照 3.1 的併發測試），
    邀請與裁判在結束時刪除。
    """
    tournament, old_token, referee_id, organizer_id = _setup_committed_invitation()
    outcome: list[str] = []
    pids: list[int] = []
    thread = _run_in_thread(
        lambda db: service.accept_invitation(
            db, token=old_token, account_id=referee_id
        ),
        outcome,
        pids,
    )
    try:
        with Session(engine) as regenerate:
            service.invite_referee(
                regenerate, tournament_id=tournament.id, actor_id=organizer_id
            )
            thread.start()
            _wait_until_blocked_on_lock(pids, thread)
            regenerate.commit()
        thread.join(timeout=LOCK_WAIT_TIMEOUT)
        assert not thread.is_alive()
        assert outcome == ["REFEREE_INVITATION_EXPIRED"]
        with Session(engine) as check:
            assert not service.is_referee(
                check, tournament_id=tournament.id, account_id=referee_id
            )
    finally:
        thread.join(timeout=LOCK_WAIT_TIMEOUT)
        _cleanup_referee_rows(tournament.id)


def test_regeneration_waits_for_concurrent_accept_without_deadlock() -> None:
    """接受已取得鎖但尚未提交時，重新產生要等它；不會死結，兩邊都成功。"""
    tournament, token, referee_id, organizer_id = _setup_committed_invitation()
    outcome: list[str] = []
    pids: list[int] = []
    thread = _run_in_thread(
        lambda db: service.invite_referee(
            db, tournament_id=tournament.id, actor_id=organizer_id
        ),
        outcome,
        pids,
    )
    try:
        with Session(engine) as accept:
            service.accept_invitation(accept, token=token, account_id=referee_id)
            thread.start()
            _wait_until_blocked_on_lock(pids, thread)
            accept.commit()
        thread.join(timeout=LOCK_WAIT_TIMEOUT)
        assert not thread.is_alive()
        assert outcome == ["ok"]
        with Session(engine) as check:
            assert service.is_referee(
                check, tournament_id=tournament.id, account_id=referee_id
            )
            current = service.get_current_invitation(check, tournament_id=tournament.id)
            assert current is not None
            assert current.token != token
            assert current.expired is False
            old = check.exec(
                select(RefereeInvitation).where(RefereeInvitation.token == token)
            ).one()
            assert old.expires_at == current.created_at
    finally:
        thread.join(timeout=LOCK_WAIT_TIMEOUT)
        _cleanup_referee_rows(tournament.id)
