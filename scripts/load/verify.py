"""壓測後的資料正確性核對：在 backend 容器內執行，直接查資料庫，結束碼 0 代表全部符合。

用法（由 run.sh 呼叫；預期隊數由 run.sh 從 manifest 讀出：報名是 teams 的筆數，報到是 captains 的筆數）：

    docker compose -p flow-load ... exec -T backend python - <registration|checkin> <tournament_id> <預期隊數> < scripts/load/verify.py

- registration：該賽事的報名筆數、正取數不超過名額（也不少於可正取的上限）、每隊一筆報名。
- checkin：該賽事的報到筆數等於預期隊數，每個（場次, 隊伍）恰好一筆。
5xx 數量由 run.sh 從 Locust 的狀態碼統計與 backend log 核對，不在這裡。
"""

import sys
import uuid
from collections import Counter

from sqlmodel import Session, col, func, select

from app.core.db import engine
from app.modules.competition.models import CheckIn, Match
from app.modules.registration.models import Registration, RegistrationStatus
from app.modules.tournaments.models import Tournament

failures: list[str] = []


def check(ok: bool, text: str) -> None:
    print(("OK   " if ok else "FAIL ") + text)
    if not ok:
        failures.append(text)


def verify_registration(session: Session, tournament_id: uuid.UUID, teams: int) -> None:
    tournament = session.get(Tournament, tournament_id)
    assert tournament is not None
    rows = list(
        session.exec(
            select(Registration).where(Registration.tournament_id == tournament_id)
        )
    )
    status = Counter(r.status for r in rows)
    accepted = status[RegistrationStatus.ACCEPTED]
    print(f"報名狀態分佈：{dict(status)}")
    check(len(rows) == teams, f"報名筆數 = {len(rows)}（預期 {teams}，每隊一筆）")
    check(len({r.team_id for r in rows}) == len(rows), "沒有重複的隊伍報名")
    check(
        accepted <= tournament.capacity,
        f"正取 = {accepted} ≤ 名額 {tournament.capacity}",
    )
    check(
        accepted == tournament.capacity,
        f"正取填滿名額（{accepted} = {tournament.capacity}）",
    )
    check(
        status[RegistrationStatus.PENDING] == 0,
        f"沒有停在待分配的報名（pending = {status[RegistrationStatus.PENDING]}）",
    )
    check(
        accepted + status[RegistrationStatus.WAITLISTED] == len(rows),
        f"其餘全部是候補（候補 = {status[RegistrationStatus.WAITLISTED]}）",
    )


def verify_checkin(session: Session, tournament_id: uuid.UUID, expected: int) -> None:
    match_ids = list(
        session.exec(select(Match.id).where(Match.tournament_id == tournament_id))
    )
    rows = list(
        session.exec(select(CheckIn).where(col(CheckIn.match_id).in_(match_ids)))
    )
    pairs = Counter((r.match_id, r.team_id) for r in rows)
    print(f"報到筆數 = {len(rows)}")
    check(len(rows) == expected, f"報到筆數 = {len(rows)}（預期 {expected}）")
    check(
        all(n == 1 for n in pairs.values()) and len(pairs) == len(rows),
        f"每個（場次, 隊伍）恰好一筆（不重複組合 {len(pairs)} 組）",
    )
    teams = {r.team_id for r in rows}
    check(len(teams) == expected, f"報到的隊伍數 = {len(teams)}（預期 {expected}）")
    total = session.exec(select(func.count()).select_from(CheckIn)).one()
    print(f"（全庫報到紀錄 {total} 筆，含先前各次報到尖峰）")


def main() -> None:
    if len(sys.argv) < 4:
        raise SystemExit("用法：verify.py <registration|checkin> <tournament_id> <預期隊數>")
    kind, tournament_id, expected = sys.argv[1], uuid.UUID(sys.argv[2]), int(sys.argv[3])
    with Session(engine) as session:
        if kind == "registration":
            verify_registration(session, tournament_id, teams=expected)
        elif kind == "checkin":
            verify_checkin(session, tournament_id, expected=expected)
        else:
            raise SystemExit(f"未知的核對類型：{kind}")
    if failures:
        print(f"核對失敗 {len(failures)} 項")
        raise SystemExit(1)
    print("核對通過")


main()
