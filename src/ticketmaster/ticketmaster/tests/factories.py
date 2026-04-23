import factory
from libs.datetime_ext.utils import utc_now
from ticketmaster.enums import EventTypeEnum
from ticketmaster.models import Event


class EventFactory(factory.Factory):
    class Meta:
        model = Event

    name = factory.Sequence(lambda n: f"Event {n}")
    description = "A test event"
    type = EventTypeEnum.SPORT
    start_at = factory.LazyFunction(utc_now)
