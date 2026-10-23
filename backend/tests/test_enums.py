"""列舉一律為英文 StrEnum，放在擁有它的模組的 models.py（AD-11）。"""

from enum import StrEnum

import pytest

from app.modules.competition.models import MatchOutcome, MatchStatus
from app.modules.disputes.models import AppealDecision, AppealStatus, ReportStatus
from app.modules.identity.models import ApplicationStatus, TokenPurpose
from app.modules.notifications.models import DeliveryStatus
from app.modules.registration.models import MemberRole, RegistrationStatus
from app.modules.tournaments.models import ScoreType, TournamentMode, TournamentStatus


@pytest.mark.parametrize(
    ("enum", "values"),
    [
        (TokenPurpose, ["verify_email", "reset_password"]),
        (ApplicationStatus, ["pending", "approved", "rejected"]),
        (ScoreType, ["win_loss", "rounds"]),
        (TournamentMode, ["campus", "custom"]),
        (
            TournamentStatus,
            [
                "upcoming",
                "open",
                "closed",
                "published",
                "ongoing",
                "finished",
                "cancelled",
            ],
        ),
        (MemberRole, ["captain", "player"]),
        (
            RegistrationStatus,
            [
                "forming",
                "pending",
                "accepted",
                "waitlisted",
                "rejected",
                "withdrawn",
                "drawn",
                "retired",
                "disqualified",
            ],
        ),
        (
            MatchStatus,
            ["scheduled", "live", "appeal_window", "appealed", "confirmed", "voided"],
        ),
        (
            MatchOutcome,
            ["played", "forfeit", "double_forfeit", "walkover", "disqualified"],
        ),
        (AppealStatus, ["open", "closed"]),
        (AppealDecision, ["upheld", "corrected", "rematch"]),
        (ReportStatus, ["open", "dismissed", "substantiated"]),
        (DeliveryStatus, ["pending", "sent", "failed"]),
    ],
)
def test_enum_values(enum: type[StrEnum], values: list[str]) -> None:
    assert issubclass(enum, StrEnum)
    assert [member.value for member in enum] == values
