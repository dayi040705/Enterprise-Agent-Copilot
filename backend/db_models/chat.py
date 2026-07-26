from sqlalchemy import Column,Integer,String,Text,DateTime

from database.mysql import Base

from datetime import datetime



class ChatRecord(Base):

    __tablename__="chat_records"



    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    conversation_id = Column(
    String(100),
    nullable=False,
    index=True
    )

    username = Column(
        String(50),
        nullable=False
    )


    department = Column(
        String(50),
        nullable=False
    )


    question = Column(
        Text,
        nullable=False
    )


    answer = Column(
        Text,
        nullable=False
    )


    sources = Column(
        Text,
        nullable=True
    )


    created_time = Column(
        DateTime,
        default=datetime.utcnow
    )