import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import declarative_base


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:123456@localhost/enterprise_rag"
)



engine = create_engine(
    DATABASE_URL,
    echo=True
)



SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)



Base = declarative_base()
def get_db():

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()