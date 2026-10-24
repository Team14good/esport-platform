"""事件 outbox（AD-6）：publish 與業務資料同一個交易；worker 逐則取用並標記。"""

import uuid
from collections.abc import Callable
from datetime import timedelta

import pytest
from sqlmodel import Session, select

from app.core import events
from app.core.events import Event, OutboxEvent
from tests.conftest import FrozenClock


class SampleThingHappened(Event):
    thing_id: uuid.UUID
    note: str


def _rows(session: Session) -> list[OutboxEvent]:
    return list(session.exec(select(OutboxEvent)))


def test_publish_writes_type_and_json_payload(
    session: Session, frozen_clock: FrozenClock
) -> None:
    thing_id = uuid.uuid4()

    row = events.publish(session, SampleThingHappened(thing_id=thing_id, note="一"))

    assert row.type == "SampleThingHappened"
    assert row.payload == {"thing_id": str(thing_id), "note": "一"}
    assert row.created_at == frozen_clock.now()
    assert row.processed_at is None


def test_published_event_disappears_when_transaction_rolls_back(
    session_factory: Callable[[], Session], session: Session
) -> None:
    thing_id = uuid.uuid4()
    with session_factory() as tx:
        events.publish(tx, SampleThingHappened(thing_id=thing_id, note="x"))
        tx.rollback()

    assert not [r for r in _rows(session) if r.payload.get("thing_id") == str(thing_id)]


@pytest.mark.parametrize("name", ["Happened", "sampleHappened", "Sample_Happened"])
def test_event_names_must_be_pascal_case_with_two_words(name: str) -> None:
    with pytest.raises(ValueError):
        type(name, (Event,), {"__annotations__": {}})


def test_next_unprocessed_returns_oldest_then_none_after_marking(
    session: Session, frozen_clock: FrozenClock
) -> None:
    first = events.publish(
        session, SampleThingHappened(thing_id=uuid.uuid4(), note="1")
    )
    frozen_clock.advance(timedelta(seconds=1))
    second = events.publish(
        session, SampleThingHappened(thing_id=uuid.uuid4(), note="2")
    )

    assert events.next_unprocessed(session) == first
    events.mark_processed(session, first)
    assert first.processed_at == frozen_clock.now()
    assert events.next_unprocessed(session) == second
    events.mark_processed(session, second)
    assert events.next_unprocessed(session) is None
