"""Idempotent local-dev seed data for the Ticketmaster service.

Creates a handful of events (across every type) with available tickets so the
frontend can browse, open, and interact with real data. Safe to run repeatedly:
it does nothing when events already exist.

Run from the repo root with the workspace virtualenv:

    poetry -C /workspace run python scripts/seed_dev_data.py
"""

import asyncio
from datetime import timedelta
from decimal import Decimal

from libs.datetime_ext.utils import utc_now
from libs.redis_ext import redis_proxy
from libs.sqlmodel_ext import Session
from redis.asyncio import Redis
from sqlmodel import func, select
from ticketmaster.admin.services.create_event import create_event
from ticketmaster.enums import CurrencyEnum, EventTypeEnum, TicketStatusEnum
from ticketmaster.models import Event, Ticket
from ticketmaster.settings import settings
from ticketmaster.utils import init_sqlmodel_engine

_SEED_EVENTS = [
    {
        "name": "Champions League Final",
        "description": "The season's decisive football match under the lights.",
        "type": EventTypeEnum.SPORT,
        "days_from_now": 21,
        "price": Decimal("149.00"),
        "currency": CurrencyEnum.EUR,
        "tickets": 8,
    },
    {
        "name": "Hamlet",
        "description": "Shakespeare's tragedy staged at the national theater.",
        "type": EventTypeEnum.THEATER,
        "days_from_now": 10,
        "price": Decimal("59.50"),
        "currency": CurrencyEnum.EUR,
        "tickets": 6,
    },
    {
        "name": "Symphony No. 9",
        "description": "A full orchestra performs Beethoven's ninth symphony.",
        "type": EventTypeEnum.CONCERT,
        "days_from_now": 35,
        "price": Decimal("89.00"),
        "currency": CurrencyEnum.EUR,
        "tickets": 10,
    },
    {
        "name": "Grand Slam Tennis",
        "description": "Quarter-final showdown between the top two seeds.",
        "type": EventTypeEnum.SPORT,
        "days_from_now": 5,
        "price": Decimal("120.00"),
        "currency": CurrencyEnum.USD,
        "tickets": 5,
    },
    {
        "name": "The Nutcracker",
        "description": "A festive ballet the whole family will enjoy.",
        "type": EventTypeEnum.THEATER,
        "days_from_now": 48,
        "price": Decimal("45.00"),
        "currency": CurrencyEnum.EUR,
        "tickets": 12,
    },
    {
        "name": "Jazz Night Live",
        "description": "An intimate evening of contemporary jazz.",
        "type": EventTypeEnum.CONCERT,
        "days_from_now": 14,
        "price": Decimal("35.00"),
        "currency": CurrencyEnum.USD,
        "tickets": 7,
    },
]


async def _count_events(session: Session) -> int:
    result = await session.exec(select(func.count()).select_from(Event))
    return int(result.one())


async def main() -> None:
    engine = init_sqlmodel_engine(db_url=settings.postgres_db_url)
    Session.configure(bind=engine)
    redis_proxy.configure_with_client(client=Redis.from_url(url=settings.redis_url, decode_responses=False))

    try:
        async with Session() as session, session.begin():
            existing = await _count_events(session=session)

        if existing:
            print(f"Seed skipped: {existing} event(s) already present.")
            return

        now = utc_now()
        created = 0
        for spec in _SEED_EVENTS:
            async with Session() as session, session.begin():
                dto = await create_event(
                    session=session,
                    name=spec["name"],
                    description=spec["description"],
                    type=spec["type"],
                    start_at=now + timedelta(days=spec["days_from_now"]),
                    price=spec["price"],
                    currency=spec["currency"],
                )
                for _ in range(spec["tickets"]):
                    session.add(
                        Ticket(
                            event_id=dto.id,
                            user_id=None,
                            status=TicketStatusEnum.AVAILABLE,
                            reserved_at=None,
                            booked_at=None,
                        )
                    )
            created += 1

        print(f"Seeded {created} events with available tickets.")
    finally:
        await redis_proxy.redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
