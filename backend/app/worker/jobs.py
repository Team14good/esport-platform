"""worker 每一輪要執行的工作清單（依序執行）。

每個工作接收一個 session、一次只處理一筆，回傳是否處理了一筆；只呼叫 core 與
各模組 service，不得 commit 或 rollback（交易由 `app.worker.run_once` 負責）。
"""

from sqlmodel import Session

from app.core import events
from app.modules.competition import service as competition_service
from app.modules.competition.forfeit_adapter import SERVICE_FORFEIT_PORTS
from app.modules.competition.forfeit_job import make_forfeit_job
from app.modules.notifications import service as notifications_service
from app.modules.notifications.email import EmailSender, SmtpEmailSender
from app.modules.registration import service as registration_service
from app.modules.tournaments import service as tournaments_service
from app.worker import Job


def dispatch_outbox(session: Session) -> bool:
    """取一則未處理的事件交給 notifications 分派，再標為已處理。"""
    event = events.next_unprocessed(session)
    if event is None:
        return False
    notifications_service.dispatch_event(session, event)
    events.mark_processed(session, event)
    return True


def make_send_email_job(sender: EmailSender) -> Job:
    def send_pending_email(session: Session) -> bool:
        """寄出一封待寄的 Email。"""
        return notifications_service.send_next_email(session, sender=sender)

    return send_pending_email


def open_registrations(session: Session) -> bool:
    """把一筆報名開始已到的「尚未開放」賽事轉為開放報名（操作者為系統）。"""
    return tournaments_service.open_due_registration(session)


def start_due_tournaments(session: Session) -> bool:
    """把一場報到開放已到的「賽程已公布」賽事轉為進行中（操作者為系統）。"""
    return competition_service.start_due_tournament(session)


def allocate_priority_windows(session: Session) -> bool:
    """結算一場優先期已結束的校園賽：分配正取與候補（Story 3.4，操作者為系統）。"""
    return registration_service.allocate_due_priority_window(session)


def close_registrations(session: Session) -> bool:
    """把一場報名截止已到的開放報名賽事轉為報名截止，校園賽先做截止補位（Story 3.6，操作者為系統）。"""
    return registration_service.close_due_registration(session)


# 判一場逾時未報到的棄權（Story 5.2；函式名稱為 `judge_forfeits`）
judge_forfeits = make_forfeit_job(SERVICE_FORFEIT_PORTS)


def confirm_expired_appeals(session: Session) -> bool:
    """確認一場申訴期滿的場次並推進晉級（操作者為系統）。"""
    return competition_service.auto_confirm_expired(session)


JOBS: list[Job] = [
    open_registrations,
    allocate_priority_windows,
    close_registrations,
    start_due_tournaments,
    judge_forfeits,
    confirm_expired_appeals,
    dispatch_outbox,
    make_send_email_job(SmtpEmailSender()),
]
