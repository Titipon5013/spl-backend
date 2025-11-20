from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

database_url = os.getenv("DATABASE_URL")
if database_url:
    engine = create_engine(database_url, echo=True, future=True)
else:
    username = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    database = os.getenv("POSTGRES_DB")

    url = URL.create(
        drivername="postgresql",
        username=username,
        password=password,
        host="postgres",
        database=database,
        port=5432,
    )

    engine = create_engine(url, echo=True, future=True)
Session = sessionmaker(bind=engine)


def get_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()
