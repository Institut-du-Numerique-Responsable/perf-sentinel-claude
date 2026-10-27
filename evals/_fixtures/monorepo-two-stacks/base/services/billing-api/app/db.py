import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

engine = create_engine(os.environ.get("DATABASE_URL", "postgresql+psycopg://localhost/billing"))


def get_session():
    with Session(engine) as session:
        yield session
