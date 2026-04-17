from sqlalchemy.ext.asyncio import async_sessionmaker

Session = async_sessionmaker(autobegin=False)
