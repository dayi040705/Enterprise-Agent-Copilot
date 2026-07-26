from sqlalchemy import Column,Integer,String,DateTime
from database.mysql import Base
from datetime import datetime


class Document(Base):

    __tablename__="documents"


    id = Column(
        Integer,
        primary_key=True,
        index=True
    )


    filename = Column(
        String(255),
        nullable=False
    )


    department = Column(
        String(50),
        nullable=False
    )


    uploader = Column(
        String(50),
        nullable=False
    )


    chunk_count = Column(
        Integer,
        nullable=False
    )


    # 新增版本号
    version = Column(
        Integer,
        default=1
    )


    status = Column(
        String(50),
        default="active"
    )


    created_time = Column(
        DateTime,
        default=datetime.utcnow
    )