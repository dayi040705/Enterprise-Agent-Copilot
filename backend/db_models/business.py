"""企业业务数据表 — Agent query_database 工具查询的 MySQL 表"""
from sqlalchemy import Column, Integer, String, Date, DateTime
from database.mysql import Base


class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    dept = Column(String(50), nullable=False)
    role = Column(String(100), nullable=False)
    status = Column(String(20), default="在职")
    hire_date = Column(String(20))
    phone = Column(String(20))
    email = Column(String(100))


class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True, index=True)
    ticket_no = Column(String(20), nullable=False, unique=True)
    title = Column(String(200), nullable=False)
    status = Column(String(20), default="处理中")
    priority = Column(String(10))
    assignee = Column(String(50))
    created = Column(String(20))
    resolved = Column(String(20), nullable=True)
    solution = Column(String(500), nullable=True)


class LeaveRecord(Base):
    __tablename__ = "leave_records"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    dept = Column(String(50), nullable=False)
    type = Column(String(20))
    start_date = Column(String(20))
    end_date = Column(String(20))
    days = Column(Integer)
    status = Column(String(20), default="待审批")
    approver = Column(String(50))
