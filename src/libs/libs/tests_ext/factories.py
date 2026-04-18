from libs.sqlmodel_ext import BaseSqlModel, Session


async def insert(*models: BaseSqlModel) -> None:
    """Persist all *models* in a single transaction via the global async ``Session``.

    Each instance is refreshed in place so server-assigned columns (``id``,
    timestamps) are populated, then expunged so attributes stay accessible
    after the session closes::

        event_1 = EventFactory(name="Hamlet")
        event_2 = EventFactory(name="Macbeth")
        await insert(event_1, event_2)
    """
    async with Session() as session, session.begin():
        for model in models:
            session.add(model)

        await session.flush()

        for model in models:
            await session.refresh(model)
            session.expunge(model)
