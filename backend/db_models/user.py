from sqlalchemy import Column,Integer,String,DateTime
from database.mysql import Base
from datetime import datetime


class User(Base):

    __tablename__="users"


    id = Column(
        Integer,
        primary_key=True,
        index=True
    )


    username = Column(
        String(50),
        unique=True,
        nullable=False
    )


    password_hash = Column(
        String(255),
        nullable=False
    )


    department = Column(
        String(50),
        nullable=True
    )


    role = Column(
        String(50),
        default="employee"
    )


    status = Column(
        String(50),
        default="pending"
    )


    created_time = Column(
        DateTime,
        default=datetime.utcnow
    )