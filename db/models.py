from sqlalchemy import Integer, String, Column, Enum, DateTime, func, ForeignKey, Float
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column
from enums import RoleEnum
from enums import RequestStatus
from datetime import datetime

class Base(DeclarativeBase):
    pass


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(Enum(RoleEnum, name="roleenum"), nullable=False, default=RoleEnum.operator)


class ParkingSnapshot(Base):
    __tablename__ = "parking_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    lot_id = Column(String, default="CAMT_01", nullable=False)
    timestamp = Column(DateTime(), nullable=False)
    available_spaces = Column(Integer, nullable=False)
    total_spaces = Column(Integer, default=30, nullable=False)
    occupied_spaces = Column(Integer, nullable=False)
    occupacy_rate = Column(Float, nullable=False)
    confidence= Column(Float, nullable=False)
    processing_time_seconds = Column(Float, nullable=False)


class ParkingSnapshot2(Base):
    __tablename__ = "parking_snapshots_camera2"

    id = Column(Integer, primary_key=True, index=True)
    lot_id = Column(String, default="CAMT_02", nullable=False)
    timestamp = Column(DateTime(), nullable=False)
    available_spaces = Column(Integer, nullable=False)
    total_spaces = Column(Integer, default=30, nullable=False)
    occupied_spaces = Column(Integer, nullable=False)
    occupacy_rate = Column(Float, nullable=False)
    confidence= Column(Float, nullable=False)
    processing_time_seconds = Column(Float, nullable=False)


# User table
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)

    license_plates = relationship("LicensePlate", back_populates="user", cascade="all, delete-orphan")
    license_plate_requests = relationship("LicensePlateRequest", back_populates="user", cascade="all, delete-orphan")


# License Plates table
class LicensePlate(Base):
    __tablename__ = "license_plates"

    id = Column(Integer, primary_key=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plate_number = Column(String, nullable=False, unique=True)
    plate_image_url = Column(String, nullable=False)

    user = relationship("User", back_populates="license_plates")


# License Plate Requests table
class LicensePlateRequest(Base):
    __tablename__ = "license_plate_requests"

    id = Column(Integer, primary_key=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plate_number = Column(String, nullable=False)
    plate_image_url = Column(String, nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(Enum(RequestStatus, name="requeststatus"), default=RequestStatus.pending, nullable=False)

    user = relationship("User", back_populates="license_plate_requests")


class EntryRecord(Base):
    __tablename__ = "entry_records"

    id = Column(Integer, primary_key=True, index=True)
    plate_number = Column(String, nullable=False)
    plate_image_url = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
