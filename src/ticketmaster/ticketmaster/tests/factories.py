from decimal import Decimal

import factory
from libs.datetime_ext.utils import utc_now
from ticketmaster.enums import CurrencyEnum, EventTypeEnum, S3BucketEnum, TicketStatusEnum
from ticketmaster.models import Event, Ticket, User


class EventFactory(factory.Factory):
    class Meta:
        model = Event

    logical_identity = factory.Faker("uuid4", cast_to=None)
    name = factory.Sequence(lambda n: f"Event {n}")
    description = "A test event"
    type = EventTypeEnum.SPORT
    start_at = factory.LazyFunction(utc_now)
    price = Decimal("10.00")
    currency = CurrencyEnum.EUR
    trailer_bucket = S3BucketEnum.MEDIA_PUBLIC.value
    trailer_key = "event-trailer/3fa85f64-5717-4562-b3fc-2c963f66afa6.mp4"


class UserFactory(factory.Factory):
    class Meta:
        model = User

    uuid = factory.Faker("uuid4", cast_to=None)
    pool_id = "eu-central-1_aB12cDEFg"
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    cognito_username = factory.Sequence(lambda n: f"cognito-username-{n}")


class TicketFactory(factory.Factory):
    class Meta:
        model = Ticket

    event_id: int
    user_id = None
    status = TicketStatusEnum.AVAILABLE
    reserved_at = None
    booked_at = None
