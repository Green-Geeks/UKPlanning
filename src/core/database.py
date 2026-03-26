import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ukplanning:devpassword@localhost:5432/ukplanning",
)


def get_engine(url=None):
    return create_engine(url or DATABASE_URL)


def get_session_factory(engine=None):
    if engine is None:
        engine = get_engine()
    return sessionmaker(bind=engine)
