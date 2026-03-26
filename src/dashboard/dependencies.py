from src.core.database import get_engine
from sqlalchemy.orm import sessionmaker


def get_db():
    engine = get_engine()
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
