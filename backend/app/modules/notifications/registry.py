"""事件類型 → 收件規則的登錄機制（Story 1.6，AD-8）。

事件不帶收件人；notifications 為每種要發站內通知的事件登錄一個 resolver：
收到事件 payload 後，只經各模組 `service.py` 的公開函式查出收件人，
回傳每位收件人一份 `NotificationDraft`（標題、說明、連結可以因人而異）。

resolver 查不到實體時拋 `BusinessError` 或 `LookupError`，分派端記錄後略過該事件。
"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import cast

from sqlmodel import Session

from app.core.events import Event


@dataclass(frozen=True)
class NotificationDraft:
    """發給一位收件人的通知內容。`link` 是站內路徑（以 `/` 開頭）。"""

    account_id: uuid.UUID
    title: str
    body: str
    link: str


Resolver = Callable[[Session, Event], Sequence[NotificationDraft]]


@dataclass(frozen=True)
class Rule:
    event_class: type[Event]
    resolver: Resolver


_rules: dict[str, Rule] = {}


def register[E: Event](
    event_class: type[E],
    resolver: Callable[[Session, E], Sequence[NotificationDraft]],
) -> None:
    """登錄一種事件的收件規則；同一事件類型重複登錄時，後登錄的取代先前的。"""
    # resolver 只會收到 `event_class.model_validate` 的結果，型別一定是 E
    _rules[event_class.event_type] = Rule(
        event_class=event_class,
        resolver=cast(Resolver, resolver),
    )


def unregister(event_class: type[Event]) -> None:
    """移除一種事件的收件規則（測試用）；沒登錄過時不做任何事。"""
    _rules.pop(event_class.event_type, None)


def get_rule(event_type: str) -> Rule | None:
    return _rules.get(event_type)


def registered_event_types() -> frozenset[str]:
    return frozenset(_rules)
