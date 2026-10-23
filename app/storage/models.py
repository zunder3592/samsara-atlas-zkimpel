from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.storage.database import Base


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default="pending")
    # changed to unique in the database to accomodate the idempotency bug fix that just found the previous null key if none was entered
    idempotency_key = Column(String(255), unique=True, index=True)
    inputs_json = Column(Text)
    artifacts_json = Column(Text)
    outputs_json = Column(Text)

    steps = relationship("Step", back_populates="case")
    case_notes = relationship("CaseNote", back_populates="case")


class Step(Base):
    __tablename__ = "steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("cases.id"))
    name = Column(String(255))
    status = Column(String(50), default="pending")
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    attempts = Column(Integer, default=0)
    output_json = Column(Text)
    error = Column(Text)

    case = relationship("Case", back_populates="steps")


class CaseNote(Base):
    __tablename__ = "case_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("cases.id"))
    employee_id = Column(String(255))
    note = Column(Text)
    # Naive datetime here vs. timezone-aware Step timestamps above - mixed
    # naive/aware audit timestamps (see P015).
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="case_notes")


class EmployeeRecord(Base):
    __tablename__ = "employee_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String(255), unique=True)
    metadata_json = Column(Text)
    last_activities_json = Column(Text)
