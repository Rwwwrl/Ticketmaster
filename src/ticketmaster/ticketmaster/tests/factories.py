import factory
from libs.datetime_ext.utils import utc_now
from ticketmaster.enums import EventTypeEnum, TicketStatusEnum
from ticketmaster.models import Event, Ticket, User


class EventFactory(factory.Factory):
    class Meta:
        model = Event

    name = factory.Sequence(lambda n: f"Event {n}")
    description = "A test event"
    type = EventTypeEnum.SPORT
    start_at = factory.LazyFunction(utc_now)


class UserFactory(factory.Factory):
    class Meta:
        model = User

    uuid = factory.Faker("uuid4", cast_to=None)
    pool_id = "eu-central-1_aB12cDEFg"
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    external_id = factory.Sequence(lambda n: f"external-sub-{n}")


class TicketFactory(factory.Factory):
    class Meta:
        model = Ticket

    event_id: int
    user_id = None
    status = TicketStatusEnum.AVAILABLE
    reserved_at = None
    booked_at = None
