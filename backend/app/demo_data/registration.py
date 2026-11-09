"""示範資料 registration 步驟：替示範賽事建立 32 支已送出報名的隊伍。

每校一隊、每隊 5 人（《特戰英豪》先發人數），第一隊由 `國立中央大學` 的示範隊長與
示範選手組成，其餘隊員是 `team01-m3@<網域>` 這類產生的帳號，密碼同 `DEMO_PASSWORD`。
報名在優先期內送出，狀態停在待審；後面的 competition 步驟抽籤時由
`finalize_for_draw` 結算成 32 支正取。

每隊在各自的 savepoint 裡建立：被業務規則拒絕時只略過那一隊（連同它的帳號），不讓
整段示範資料回滾。隊長已有這場賽事的隊伍就略過，再次啟動不重算密碼雜湊。
"""

import base64
import io
import logging
import uuid

from sqlmodel import Session

from app.core.errors import BusinessError
from app.demo_data.accounts import DEMO_SCHOOL_NAME
from app.demo_data.context import DemoContext
from app.modules.identity import service as identity_service
from app.modules.registration import service as registration_service

logger = logging.getLogger(__name__)

DEMO_TEAM_COUNT = 32
DEMO_TEAM_SIZE = 5
DEMO_TEAM_NAME_SUFFIX = "電競隊"
# 依序循環，讓各隊積分有高有低；都不是積分 0 的「無排位」
DEMO_RANK_TIERS = ("銀牌", "金牌", "白金", "鑽石", "超凡入聖")
# 1×1 的透明 PNG，當作段位截圖
DEMO_SCREENSHOT = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAA"
    "AABJRU5ErkJggg=="
)


def _demo_schools(session: Session) -> list[str]:
    """示範學校排最前面，其餘依名稱排序；學校不足 32 所時回傳現有的全部。"""
    names = [school.name for school in identity_service.list_schools(session)]
    others = [name for name in names if name != DEMO_SCHOOL_NAME]
    return [DEMO_SCHOOL_NAME, *others][:DEMO_TEAM_COUNT]


def _member_email(team_no: int, member_no: int, domain: str) -> str:
    return f"team{team_no:02d}-m{member_no}@{domain}"


def _team_already_seeded(
    session: Session, context: DemoContext, team_no: int, tournament_id: uuid.UUID
) -> bool:
    captain_id = (
        context.accounts["captain"]
        if team_no == 1
        else identity_service.find_account_id_by_email(
            session, _member_email(team_no, 1, context.email_domain)
        )
    )
    if captain_id is None:
        return False
    return any(
        card.tournament_id == tournament_id
        for card in registration_service.list_my_teams(session, account_id=captain_id)
    )


def _ensure_member(
    session: Session,
    context: DemoContext,
    *,
    team_no: int,
    member_no: int,
    school_name: str,
) -> uuid.UUID:
    if team_no == 1 and member_no == 1:
        return context.accounts["captain"]
    if team_no == 1 and member_no == 2:
        return context.accounts["player"]
    email = _member_email(team_no, member_no, context.email_domain)
    identity_service.ensure_demo_account(
        session,
        email=email,
        password=context.password,
        display_name=f"第 {team_no} 隊選手 {member_no}",
        school_name=school_name,
    )
    account_id = identity_service.find_account_id_by_email(session, email)
    assert account_id is not None  # 上一行已確保帳號存在
    return account_id


def _seed_team(
    session: Session,
    context: DemoContext,
    *,
    team_no: int,
    school_name: str,
    tournament_id: uuid.UUID,
) -> None:
    member_ids = [
        _ensure_member(
            session,
            context,
            team_no=team_no,
            member_no=member_no,
            school_name=school_name,
        )
        for member_no in range(1, DEMO_TEAM_SIZE + 1)
    ]
    captain_id = member_ids[0]
    team = registration_service.create_team(
        session,
        tournament_id=tournament_id,
        account_id=captain_id,
        name=f"{school_name}{DEMO_TEAM_NAME_SUFFIX}",
    )
    for member_id in member_ids[1:]:
        registration_service.join_team(
            session, token=team.invite_token, account_id=member_id
        )
    for index, member_id in enumerate(member_ids):
        registration_service.update_player_profile(
            session,
            team_id=team.id,
            account_id=member_id,
            game_account_id=f"FLOW{team_no:02d}P{index + 1}#TW1",
            rank_tier=DEMO_RANK_TIERS[(team_no + index) % len(DEMO_RANK_TIERS)],
            screenshot=io.BytesIO(DEMO_SCREENSHOT),
            content_type="image/png",
            file_name="rank.png",
        )
    registration_service.submit_registration(
        session, team_id=team.id, account_id=captain_id
    )


def seed(session: Session, context: DemoContext) -> None:
    tournament_id = context.tournament_to_draw
    if tournament_id is None:
        logger.info("No demo tournament, registration demo data skipped")
        return
    created = 0
    for team_no, school_name in enumerate(_demo_schools(session), start=1):
        if _team_already_seeded(session, context, team_no, tournament_id):
            continue
        try:
            with session.begin_nested():
                _seed_team(
                    session,
                    context,
                    team_no=team_no,
                    school_name=school_name,
                    tournament_id=tournament_id,
                )
        except BusinessError as exc:
            logger.warning(
                "Demo team %d (%s) not created (%s: %s)",
                team_no,
                school_name,
                exc.code,
                exc.message,
            )
            continue
        created += 1
    logger.info("Demo teams created: %d", created)
